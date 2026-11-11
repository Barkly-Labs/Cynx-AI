
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sys
import os
import sqlite3
import time
import logging
import threading
import uuid

from starlette.concurrency import run_in_threadpool

from ai.knowledge.store import KnowledgeStore
from memory.sqlite import connect



sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "../../"
        )
    )
)



from ai.context_manager import ContextManager
from ai.memory_system.extractor import MemoryExtractor
from ai.memory_system.manager import MemoryManager
from ai.ollama_client import OllamaClient
from ai.prompt_builder import PromptBuilder
from ai.mode_manager import ModeManager
from ai.chat_engine import ChatEngine, ChatRequestCancelled

from tools.tool_router import ToolRouter
from tools.web_search import WebSearchTool
from tools.calculator import CalculatorTool
from tools.SmokeCounterTool import smoke_counter
from tools.ChartTool import chart_tool
from tools.filesystem import FilesystemTool
from interfaces.web.pipeline import PipelineEventStore



app = FastAPI(
    title="CYN-X"
)



app.mount(
    "/static",
    StaticFiles(
        directory="interfaces/web/static"
    ),
    name="static"
)



templates = Jinja2Templates(
    directory="interfaces/web/templates"
)



# ======================
# AI CORE
# ======================


ollama_client = OllamaClient()

prompt_builder = PromptBuilder()


conn = connect()



# ======================
# MEMORY
# ======================

# MemoryManager is now the single
# memory system used by CYN-X.

memory_manager = MemoryManager(
    conn
)


memory_extractor = MemoryExtractor(
    memory_manager
)



# ======================
# TOOLS
# ======================


tool_router = ToolRouter()

from hardware.lepro.integration import register_selected
try:
    register_selected(tool_router)
except Exception as exc:
    print(f"[LEPRO] Optional registration unavailable: {exc}")


tool_router.register_tool(
    WebSearchTool()
)


tool_router.register_tool(
    CalculatorTool()
)

tool_router.register_tool(
    FilesystemTool()
)


# Register the smoke_counter tool so Cyn
# can call it from the web interface
tool_router.register_tool(
    smoke_counter
)


# Register the chart tool for structured visualizations.
tool_router.register_tool(
    chart_tool
)



# ======================
# MODE / KNOWLEDGE
# ======================


mode_manager = ModeManager()


knowledge_store = KnowledgeStore(
    conn
)



# ======================
# CONTEXT
# ======================

# ContextManager and MemoryExtractor now
# use the exact same MemoryManager.

context_manager = ContextManager(
    memory_manager,
    knowledge_store,
)



# ======================
# CHAT ENGINE
# ======================


chat_engine = ChatEngine(
    ollama_client,
    prompt_builder,
    memory_manager,
    tool_router,
    mode_manager,
    memory_manager,
    memory_extractor=memory_extractor,
    context_manager=context_manager

)

pipeline_events = PipelineEventStore()
chat_engine_lock = threading.Lock()
web_logger = logging.getLogger("cynx.web")


# ======================
# WEB
# ======================


@app.get("/", response_class=HTMLResponse)
async def home(request:Request):

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={}
    )



@app.get("/dashboard")
def dashboard(request:Request):

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={}
    )




chat_request_count = 0



@app.post("/chat")
async def chat(data:dict):

    global chat_request_count

    chat_request_count += 1

    requested_id = data.get("request_id")
    try:
        request_id = str(uuid.UUID(str(requested_id)))
    except (ValueError, TypeError, AttributeError):
        request_id = str(uuid.uuid4())

    pipeline_events.create(request_id)

    start=time.perf_counter()


    message=data.get(
        "message",
        ""
    )


    prompt_preset = data.get(
        "prompt_preset",
        None
    )

    prompt_layers = data.get(
        "prompt_layers",
        None
    )


    print(
        f"[CHAT REQUEST] id={request_id} "
        f"count={chat_request_count} "
        f"message_preview={message[:120]}"
    )


    def process_request():
        with chat_engine_lock:
            try:
                if prompt_preset:
                    try:
                        prompt_builder.apply_prompt_preset(prompt_preset)
                    except ValueError as exc:
                        print(f"[PROMPT LAYERS] {exc}")
                elif prompt_layers is not None:
                    prompt_builder.set_prompt_layers(prompt_layers)

                print(f"[PROMPT LAYERS] {prompt_builder.get_prompt_layers()}")

                response = chat_engine.handle_user_message(
                    user_id="web_user",
                    text=message,
                    request_id=request_id,
                    pipeline_callback=lambda event: pipeline_events.publish(
                        request_id,
                        event.pop("type"),
                        **event,
                    ),
                    cancellation_check=lambda: pipeline_events.is_cancelled(
                        request_id
                    ),
                )
                elapsed = round(time.perf_counter() - start, 3)
                pipeline_events.publish(request_id, "request_completed")
                print(f"[CHAT COMPLETE] id={request_id} elapsed={elapsed}s")
                return {
                    "response": response,
                    "response_time": elapsed,
                    "prompt_layers": prompt_builder.get_prompt_layers(),
                    "request_id": request_id,
                }
            except ChatRequestCancelled:
                elapsed = round(time.perf_counter() - start, 3)
                pipeline_events.publish(
                    request_id,
                    "request_cancelled",
                    message="Request cancelled before a response was ready.",
                )
                return {
                    "response": "",
                    "response_time": elapsed,
                    "prompt_layers": prompt_builder.get_prompt_layers(),
                    "request_id": request_id,
                    "cancelled": True,
                }
            except Exception:
                web_logger.exception("[CHAT FAILED] id=%s", request_id)
                pipeline_events.publish(
                    request_id,
                    "request_failed",
                    message="CYN-X Core could not complete this request.",
                )
                raise

    return await run_in_threadpool(process_request)


@app.get("/chat/events/{request_id}")
async def chat_events(request_id: str, after: int = 0):
    return pipeline_events.read(request_id, max(0, after))


@app.post("/chat/cancel/{request_id}")
async def cancel_chat(request_id: str):
    return {"requested": pipeline_events.request_cancel(request_id)}


@app.get("/api/lepro/devices")
async def lepro_devices():
    from hardware.lepro.discovery import discover
    try:
        return {"devices": await discover(), "error": None}
    except Exception as exc:
        return {"devices": [], "error": str(exc)}

@app.get("/api/lepro/selection")
async def lepro_selection():
    from hardware.lepro.integration import CONFIG
    devices = CONFIG.list_devices()
    return {"selected": ({"name":devices[0]["name"],"mac":devices[0]["mac"]} if devices else None),
            "registered": "lepro_lights" in tool_router.tools}

@app.post("/api/lepro/select")
async def lepro_select(data: dict):
    from hardware.lepro.integration import select_device
    from hardware.lepro.discovery import discover
    try:
        candidates = await discover()
        selected = next((d for d in candidates if d["mac"] == data.get("mac")), None)
        if selected is None:
            return {"ok": False, "error":"Device not found in current BLE discovery"}
        select_device(tool_router, selected["mac"], selected["name"])
        return {"ok":True, "name":selected["name"]}
    except Exception as exc:
        return {"ok":False,"error":str(exc)}
