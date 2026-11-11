
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
import asyncio
import json
from pathlib import Path

import requests

from starlette.concurrency import run_in_threadpool

from ai.knowledge.store import KnowledgeStore
from memory.sqlite import connect
from config import get_config



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
from interfaces.web.benchmark_runs import BenchmarkRunManager



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


@app.get("/dx")
def dx_home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dx.html",
        context={},
    )


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_SUITES = PROJECT_ROOT / "benchmark" / "suites"
DX_BENCHMARK_RUNS = PROJECT_ROOT / "benchmark" / "results" / "dx_runs"


@app.get("/api/dx/health")
def dx_health():
    """Report live local service state without returning URLs or secrets."""
    config = get_config()
    try:
        response = requests.get(
            f"{ollama_client.base_url}/api/tags", timeout=2
        )
        response.raise_for_status()
        ollama_ok = True
        models = [m.get("name", "") for m in response.json().get("models", [])]
    except Exception:
        ollama_ok = False
        models = []
    try:
        conn.execute("SELECT 1").fetchone()
        database_ok = True
    except Exception:
        database_ok = False
    active = getattr(ollama_client, "model", config.model_name)
    return {
        "backend": "online",
        "ollama": "online" if ollama_ok else "offline",
        "model": active,
        "model_available": active in models if models else None,
        "models": models,
        "database": "online" if database_ok else "offline",
        "tools": tool_router.describe_tools(),
        "tool_count": len(tool_router.list_tools()),
        "environment": "local",
        "hardware": {"available": False, "reason": "No supported telemetry provider is configured."},
    }


@app.get("/api/dx/benchmark/suites")
def dx_benchmark_suites():
    suites = []
    for path in sorted(BENCHMARK_SUITES.glob("*.json")):
        try:
            cases = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cases, list):
                suites.append({"id": path.name, "name": path.stem.replace("_", " ").replace("-", " "), "count": len(cases)})
        except (OSError, ValueError):
            continue
    return {"suites": suites}


@app.get("/api/dx/benchmark/suites/{suite_id}")
def dx_benchmark_suite(suite_id: str):
    # Accept only a filename present in the benchmark suite directory.
    path = (BENCHMARK_SUITES / suite_id).resolve()
    if path.parent != BENCHMARK_SUITES.resolve() or path.suffix.lower() != ".json" or not path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Benchmark suite not found")
    try:
        cases = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Benchmark suite could not be read")
    if not isinstance(cases, list):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Benchmark suite format is invalid")
    return {"id": suite_id, "cases": cases}


@app.post("/api/dx/benchmark/runs")
def dx_save_benchmark_run(data: dict):
    """Score results using existing benchmark code and persist a DX run."""
    from benchmark.analyzer import analyze_response
    from benchmark.scoring import score_response
    import statistics
    run_id = str(uuid.uuid4())
    cases = data.get("results", [])
    if not isinstance(cases, list) or len(cases) > 500:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid benchmark results")
    scored = []
    for item in cases:
        if not isinstance(item, dict):
            continue
        response_text = str(item.get("response", ""))[:50000]
        question = str(item.get("question", ""))[:10000]
        category = str(item.get("category", ""))[:200]
        analysis = analyze_response(response_text)
        scores = score_response(response_text, category, test=item.get("test"))
        scored.append({
            "test_id": str(item.get("test_id", ""))[:200],
            "category": category,
            "question": question,
            "response": response_text,
            "response_time": max(0, float(item.get("response_time", 0) or 0)),
            "failed": bool(item.get("failed", False)),
            "error": "Request failed" if item.get("failed") else None,
            "tools": item.get("tools", []) if isinstance(item.get("tools", []), list) else [],
            "analysis": analysis,
            "scores": scores,
        })
    timings = [row["response_time"] for row in scored]
    tool_failures = sum(
        1 for row in scored
        for tool_event in row["tools"]
        if isinstance(tool_event, dict) and tool_event.get("status") == "failed"
    )
    summary = {
        "run_id": run_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "suite": str(data.get("suite", ""))[:200],
        "mode": "manual" if data.get("mode") == "manual" else "automatic",
        "attempted": len(scored),
        "successful": sum(not row["failed"] for row in scored),
        "failed": sum(row["failed"] for row in scored),
        "tool_failures": tool_failures,
        "partial_tool_failures": sum(
            not row["failed"] and any(
                isinstance(event, dict) and event.get("status") == "failed"
                for event in row["tools"]
            ) for row in scored
        ),
        "average_response_time": round(statistics.mean(timings), 3) if timings else 0,
        "median_response_time": round(statistics.median(timings), 3) if timings else 0,
        "average_score": round(statistics.mean([r["scores"].get("overall", 0) for r in scored]), 2) if scored else 0,
        "results": scored,
    }
    DX_BENCHMARK_RUNS.mkdir(parents=True, exist_ok=True)
    (DX_BENCHMARK_RUNS / f"{run_id}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


@app.get("/api/dx/benchmark/runs")
def dx_benchmark_runs():
    return {"runs": benchmark_runs.list_runs()}


@app.post("/api/dx/benchmark/start")
def dx_start_benchmark(data: dict):
    from fastapi import HTTPException
    try:
        run = benchmark_runs.start(
            str(data.get("suite", "")),
            str(data.get("mode", "automatic")),
            str(data.get("idempotency_key", "")),
        )
        return run
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=f"A benchmark is already active ({exc}).")


@app.get("/api/dx/benchmark/active")
def dx_active_benchmark():
    return {"run": benchmark_runs.active()}


@app.get("/api/dx/benchmark/latest")
def dx_latest_benchmark():
    return {"run": benchmark_runs.latest()}


@app.get("/api/dx/benchmark/runs/{run_id}")
def dx_benchmark_run(run_id: str, after_event: int = 0):
    from fastapi import HTTPException
    try:
        return benchmark_runs.get(run_id, after_event=max(0, after_event))
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")


@app.get("/api/dx/benchmark/runs/{run_id}/updates")
def dx_benchmark_run_updates(run_id: str, after_event: int = 0):
    from fastapi import HTTPException
    try:
        return benchmark_runs.updates(run_id, after_event=max(0, after_event))
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")


@app.post("/api/dx/benchmark/runs/{run_id}/pause")
def dx_pause_benchmark(run_id: str):
    from fastapi import HTTPException
    try:
        return benchmark_runs.pause(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/dx/benchmark/runs/{run_id}/resume")
def dx_resume_benchmark(run_id: str):
    from fastapi import HTTPException
    try:
        return benchmark_runs.resume(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/dx/benchmark/runs/{run_id}/next")
def dx_next_benchmark_question(run_id: str):
    from fastapi import HTTPException
    try:
        return benchmark_runs.resume(run_id, next_question=True)
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/dx/benchmark/runs/{run_id}/stop")
def dx_stop_benchmark(run_id: str):
    from fastapi import HTTPException
    try:
        return benchmark_runs.stop(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")


@app.delete("/api/dx/benchmark/runs")
def dx_clear_benchmark_results():
    return {"deleted": benchmark_runs.delete_completed()}


@app.get("/api/dx/tools")
def dx_tools():
    schemas = tool_router.as_ollama_tools()
    by_name = {x.get("function", {}).get("name"): x.get("function", {}) for x in schemas}
    return {"tools": [{**tool, "schema": by_name.get(tool["name"], {})} for tool in tool_router.describe_tools()]}


@app.get("/api/dx/requests")
def dx_requests():
    return {"requests": pipeline_events.list_recent()}


@app.get("/api/dx/requests/{request_id}")
def dx_request(request_id: str):
    return pipeline_events.read(request_id)


@app.post("/api/dx/model")
def dx_select_model(data: dict):
    model = str(data.get("model", ""))
    if not model or len(model) > 200 or any(c in model for c in "\r\n\\"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Choose a valid installed model")
    try:
        response = requests.get(f"{ollama_client.base_url}/api/tags", timeout=2)
        response.raise_for_status()
        installed = {m.get("name") for m in response.json().get("models", [])}
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Ollama is unavailable")
    if model not in installed:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="That model is not installed in Ollama")
    ollama_client.model = model
    return {"ok": True, "model": model, "persistence": "runtime"}




chat_request_count = 0



@app.post("/chat")
async def chat(data:dict):

    return await _dispatch_chat(data)


async def _dispatch_chat(data: dict):

    global chat_request_count

    chat_request_count += 1

    requested_id = data.get("request_id")
    try:
        request_id = str(uuid.UUID(str(requested_id)))
    except (ValueError, TypeError, AttributeError):
        request_id = str(uuid.uuid4())
    stored_trace_callback = benchmark_runs.trace_callback(request_id)
    observed_trace_stages = set()
    if stored_trace_callback:
        def personality_trace_callback(details):
            try:
                if details.get("stage"):
                    observed_trace_stages.add(details["stage"])
                stored_trace_callback(details)
            except Exception as exc:
                web_logger.warning("[PERSONALITY TRACE STORE ERROR] request_id=%s error=%s", request_id, exc)
    else:
        personality_trace_callback = None

    pipeline_events.create(request_id)

    start=time.perf_counter()


    message=data.get(
        "message",
        ""
    )

    try:
        conversation_id = str(uuid.UUID(str(data.get("conversation_id"))))
        conversation_key = f"web_user:{conversation_id}"
    except (ValueError, TypeError, AttributeError):
        conversation_key = "web_user"


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

                if personality_trace_callback:
                    personality_trace_callback({
                        "stage": "configuration_loaded", "status": "completed",
                        "architecture": getattr(prompt_builder, "personality_arch", None),
                        "prompt_layers": prompt_builder.get_prompt_layers(),
                        "preset": prompt_preset or "not specified",
                        "configuration_overrides": prompt_layers or {},
                        "model": getattr(ollama_client, "model", None),
                        "generation_parameters": "not exposed by the active Ollama client",
                    })

                def publish_pipeline(event):
                    event_type = event.pop("type")
                    if event_type == "decision" and personality_trace_callback and "routing_decision" not in observed_trace_stages:
                        personality_trace_callback({
                            "stage": "routing_decision", "status": "completed",
                            "action": event.get("action"), "tools": event.get("tools", []),
                            "policy_classification": "not instrumented in this request path",
                        })
                    pipeline_events.publish(request_id, event_type, **event)

                response = chat_engine.handle_user_message(
                    user_id="web_user",
                    text=message,
                    request_id=request_id,
                    pipeline_callback=publish_pipeline,
                    cancellation_check=lambda: pipeline_events.is_cancelled(
                        request_id
                    ),
                    trace_callback=personality_trace_callback,
                    conversation_key=conversation_key,
                )
                elapsed = round(time.perf_counter() - start, 3)
                pipeline_events.publish(request_id, "request_completed")
                if personality_trace_callback:
                    personality_trace_callback({"stage": "response_returned", "status": "completed",
                                                "final_response": response,
                                                "transformation": "No separate response normalization stage is instrumented."})
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
                if personality_trace_callback:
                    personality_trace_callback({"stage": "request_cancelled", "status": "cancelled"})
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
                if personality_trace_callback:
                    personality_trace_callback({"stage": "request_failed", "status": "failed",
                                                "error": "See sanitized request diagnostics; raw stack traces are not stored in Personality Trace."})
                raise

    return await run_in_threadpool(process_request)


def _dispatch_benchmark_question(data: dict):
    """Run through the exact dispatcher shared by the ordinary /chat route."""
    return asyncio.run(_dispatch_chat(data))


benchmark_runs = BenchmarkRunManager(
    BENCHMARK_SUITES,
    DX_BENCHMARK_RUNS,
    pipeline_events,
    _dispatch_benchmark_question,
)


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
