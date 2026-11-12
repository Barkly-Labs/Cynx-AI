
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
import math
import re
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
from benchmark.telemetry import generation_metrics
from benchmark.watchdog import BenchmarkWatchdog
from benchmark.personality.diagnostics import PersonalityDiagnosticsService
from ai.personality_studio import PersonalityStudioStore, TRAITS, TRAIT_INFO, STARTER_TRAITS, validate_traits
from ai.personality import configure_personality_studio_store



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
personality_studio = PersonalityStudioStore(get_config().db_path)
configure_personality_studio_store(personality_studio)



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


PERSONALITY_EVALUATION_PROMPT = """You are an evaluator of observable conversational style, not a hidden-reasoning reader.
Compare the target tendencies and scenario against the assistant's actual response.
Return JSON only with keys: dimensions (array), overall_consistency (object or null), limitations (array).
For every supplied trait, return trait, score (integer 0-4 or null), confidence (0-1 or null),
evidence (an exact short substring from the response or empty string), explanation (one concise sentence),
potential_contradictions (array of concise observable concerns), missing_evidence (array of evidence needed),
and status ('observed' or 'insufficient_evidence'). Do not require every trait to appear in one response.
Use null when context does not provide fair evidence. Scores are evaluator interpretations, not objective facts.
Do not include chain-of-thought, private reasoning, or invented quotes. For one response overall consistency must be null.
For a multi-turn transcript, assess recognizable voice across turns only when evidence supports it."""

_STUDIO_HIDDEN_TEXT = re.compile(r"(?is)<think>.*?(?:</think>|$)|<analysis>.*?(?:</analysis>|$)")
_STUDIO_SECRET = re.compile(r"(?i)\b(?:api[_ -]?key|access[_ -]?token|password|secret)\s*[:=]\s*[^\s,;]+|\bsk-[A-Za-z0-9_-]{16,}")
_STUDIO_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_STUDIO_PHONE = re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\w)")


def _studio_safe_text(value: str) -> str:
    text = _STUDIO_HIDDEN_TEXT.sub("[hidden reasoning removed]", str(value or ""))
    text = _STUDIO_SECRET.sub("[credential redacted]", text)
    text = _STUDIO_EMAIL.sub("[email redacted]", text)
    return _STUDIO_PHONE.sub("[phone redacted]", text)


def _studio_generate(prompt: str, traits: dict[str, int], model: str | None = None) -> dict:
    """Generate a draft-only answer through the production prompt and local Ollama client."""
    from ai.prompt_builder import PromptBuilder as IsolatedPromptBuilder
    architecture = (os.getenv("CYNX_PERSONALITY_ARCH", "v1") or "v1").strip().lower()
    builder = IsolatedPromptBuilder(personality_arch=architecture)
    system_prompt = builder.build_prompt(user_input=prompt, personality_matrix=traits)
    result = ollama_client.chat(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        tools=None, stream=False, **({"model": model} if model else {}),
    )
    message = result.get("message") or {}
    response_text = _studio_safe_text(str(message.get("content") or result.get("response") or "").strip())
    if result.get("done") is False or not response_text:
        raise RuntimeError("The local model did not return a complete response.")
    return {"response": response_text, "model": result.get("model") or getattr(ollama_client, "model", "unknown"),
            "metrics": {"prompt_tokens": result.get("prompt_eval_count"), "completion_tokens": result.get("eval_count"),
                        "total_duration_ns": result.get("total_duration"), "generation_duration_ns": result.get("eval_duration")},
            "generation_parameters": {"temperature": 0.7, "context_tokens": 8192, "streaming": False}}


def _studio_generate_conversation(prompts: list[str], traits: dict[str, int], model: str) -> dict:
    """Run isolated multi-turn context without touching chat history or memory."""
    from ai.prompt_builder import PromptBuilder as IsolatedPromptBuilder
    architecture = (os.getenv("CYNX_PERSONALITY_ARCH", "v1") or "v1").strip().lower()
    builder = IsolatedPromptBuilder(personality_arch=architecture)
    system_prompt = builder.build_prompt(user_input=prompts[0], personality_matrix=traits)
    messages = [{"role": "system", "content": system_prompt}]
    turns, metrics = [], []
    result = {}
    for index, user_text in enumerate(prompts, 1):
        messages.append({"role": "user", "content": user_text})
        result = ollama_client.chat(messages=messages, tools=None, stream=False, model=model)
        raw = str((result.get("message") or {}).get("content") or result.get("response") or "").strip()
        answer = _studio_safe_text(raw)
        if result.get("done") is False or not answer:
            raise RuntimeError(f"Local generation did not complete turn {index}.")
        messages.append({"role": "assistant", "content": answer})
        turn_metrics = {"prompt_tokens": result.get("prompt_eval_count"), "completion_tokens": result.get("eval_count"),
                        "total_duration_ns": result.get("total_duration"), "generation_duration_ns": result.get("eval_duration")}
        turns.append({"turn_index": index, "user_message": _studio_safe_text(user_text), "response": answer, "metrics": turn_metrics})
        metrics.append(turn_metrics)
    transcript = "\n\n".join(f"Turn {item['turn_index']} user: {item['user_message']}\nTurn {item['turn_index']} CYN-X: {item['response']}" for item in turns)
    return {"response": transcript, "turns": turns, "metrics": metrics, "model": result.get("model") or model,
            "generation_parameters": {"temperature": 0.7, "context_tokens": 8192, "streaming": False}}


def _studio_evaluate(prompt: str, response_text: str, traits: dict[str, int], model: str) -> dict:
    """Score only evidence present in the actual response; reject invented quotations."""
    request = {
        "target_tendencies_percent": traits,
        "trait_definitions": TRAIT_INFO,
        "scenario": _studio_safe_text(prompt),
        "actual_response": _studio_safe_text(response_text),
    }
    result = ollama_client.chat(
        messages=[{"role": "system", "content": PERSONALITY_EVALUATION_PROMPT},
                  {"role": "user", "content": json.dumps(request, ensure_ascii=False)}],
        tools=None, stream=False, format="json", temperature=0.1, num_ctx=8192,
    )
    raw = (result.get("message") or {}).get("content") or result.get("response") or ""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("The local evaluator returned invalid structured results.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("dimensions"), list):
        raise RuntimeError("The local evaluator response did not include dimension results.")
    by_trait = {item.get("trait"): item for item in data["dimensions"] if isinstance(item, dict)}
    dimensions = []
    for trait in TRAITS:
        item = by_trait.get(trait, {})
        score = item.get("score")
        confidence = item.get("confidence")
        evidence = item.get("evidence") if isinstance(item.get("evidence"), str) else ""
        if evidence and evidence not in response_text:
            score, confidence, evidence = None, None, ""
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 4:
            score = None
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            confidence = None
        status = "observed" if score is not None and evidence else "insufficient_evidence"
        predicted = round(traits[trait] / 25, 2)
        dimensions.append({"trait": trait, "target": traits[trait], "predicted_score": predicted,
                           "prediction_method": "heuristic linear mapping from target percent to 0–4; not calibrated",
                           "observed_score": score, "deviation": round(score - predicted, 2) if score is not None else None,
                           "confidence": confidence, "evidence": evidence,
                           "explanation": _studio_safe_text(str(item.get("explanation") or "Not assessed by the evaluator."))[:500],
                           "potential_contradictions": [_studio_safe_text(value)[:300] for value in (item.get("potential_contradictions") or []) if isinstance(value, str)][:5],
                           "missing_evidence": [_studio_safe_text(value)[:300] for value in (item.get("missing_evidence") or []) if isinstance(value, str)][:5],
                           "status": status})
    consistency = data.get("overall_consistency")
    if not isinstance(consistency, dict) or "Turn 2 user:" not in response_text:
        consistency = None
    else:
        score = consistency.get("score")
        confidence_value = consistency.get("confidence")
        consistency = ({"score": float(score), "confidence": confidence_value if isinstance(confidence_value, (int, float)) and not isinstance(confidence_value, bool) and 0 <= confidence_value <= 1 else None,
                        "explanation": _studio_safe_text(str(consistency.get("explanation") or ""))[:500]}
                       if isinstance(score, (int, float)) and not isinstance(score, bool) and 0 <= score <= 4 else None)
    return {"method": "local-model-evaluator", "evaluator_model": model,
            "score_scale": "0–4; null means insufficient evidence; not objective truth",
            "confidence_note": "Evaluator-reported confidence; not a calibrated probability.",
            "dimensions": dimensions, "prediction_status": "heuristic",
            "prediction_method": "Target percentage is mapped linearly to a 0–4 expected-expression score; this mapping is uncalibrated.",
            "overall_consistency": consistency,
            "limitations": ["A single response cannot establish consistency across conversations.",
                            "Scores are interpretations of visible output and require human review."]}


def _studio_validate_model(model: str | None) -> str:
    current = str(getattr(ollama_client, "model", ""))
    if not model or model == current:
        return current
    try:
        response = requests.get(f"{ollama_client.base_url}/api/tags", timeout=3)
        response.raise_for_status()
        installed = {str(item.get("name", "")) for item in response.json().get("models", [])}
    except Exception as exc:
        raise RuntimeError("Ollama model catalog is unavailable.") from exc
    if model not in installed:
        raise ValueError("Choose a model installed in the local Ollama instance.")
    return model


@app.get("/api/dx/personality/studio")
def dx_personality_studio():
    active = personality_studio.active()
    return {"active": active, "versions": personality_studio.history(),
            "presets": personality_studio.presets(), "traits": [{"id": key, "name": key.replace("_", " ").title(),
            "description": TRAIT_INFO[key]} for key in TRAITS], "starter_draft": dict(STARTER_TRAITS),
            "evaluation_history": personality_studio.evaluations(), "runtime_source": "active persisted configuration after explicit activation; legacy prompt before first activation"}


@app.post("/api/dx/personality/preview")
async def dx_personality_preview(data: dict):
    from fastapi import HTTPException
    prompt = str(data.get("prompt") or "").strip()
    try:
        traits = validate_traits(data.get("traits"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not prompt or len(prompt) > 6000:
        raise HTTPException(status_code=422, detail="Enter a test message up to 6,000 characters.")
    try:
        model = _studio_validate_model(data.get("model"))
        result = await run_in_threadpool(_studio_generate, prompt, traits, model)
    except Exception as exc:
        web_logger.exception("Personality Studio preview failed")
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=f"Local preview failed: {type(exc).__name__}")
    return {**result, "experimental": True, "persistence": "not saved to conversation history or memory", "active_configuration_unchanged": True}


@app.post("/api/dx/personality/evaluate")
async def dx_personality_evaluate(data: dict):
    from fastapi import HTTPException
    prompt = str(data.get("prompt") or "").strip()
    try:
        traits = validate_traits(data.get("traits"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not prompt or len(prompt) > 6000:
        raise HTTPException(status_code=422, detail="Enter a test message up to 6,000 characters.")
    try:
        model = _studio_validate_model(data.get("model"))
        generated = await run_in_threadpool(_studio_generate, prompt, traits, model)
        report = await run_in_threadpool(_studio_evaluate, prompt, generated["response"], traits, generated["model"])
        report["generation"] = {"model": generated["model"], "parameters": generated["generation_parameters"], "metrics": generated["metrics"]}
        active = personality_studio.active()
        config = active if active.get("activated") and active.get("traits") == traits else None
        saved = personality_studio.record_evaluation(traits=traits, prompt=_studio_safe_text(prompt), response=generated["response"],
            model=generated["model"], evaluation=report, config=config, evaluator_model=report["evaluator_model"])
    except Exception as exc:
        web_logger.exception("Personality Studio evaluation failed")
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=f"Local evaluation failed: {type(exc).__name__}")
    return {**saved, "metrics": generated.get("metrics"), "active_configuration_unchanged": True}


@app.post("/api/dx/personality/compare")
async def dx_personality_compare(data: dict):
    from fastapi import HTTPException
    prompt = str(data.get("prompt") or "").strip()
    try:
        left, right = validate_traits(data.get("left")), validate_traits(data.get("right"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not prompt or len(prompt) > 6000:
        raise HTTPException(status_code=422, detail="Enter a test message up to 6,000 characters.")
    try:
        models = (_studio_validate_model(data.get("left_model")), _studio_validate_model(data.get("right_model")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    results = []
    try:
        for traits, selected_model in zip((left, right), models):
            generated = await run_in_threadpool(_studio_generate, prompt, traits, selected_model)
            evaluation = await run_in_threadpool(_studio_evaluate, prompt, generated["response"], traits, generated["model"])
            evaluation["generation"] = {"model": generated["model"], "parameters": generated["generation_parameters"], "metrics": generated["metrics"]}
            saved = personality_studio.record_evaluation(traits=traits, prompt=_studio_safe_text(prompt), response=generated["response"],
                model=generated["model"], evaluation=evaluation, evaluator_model=evaluation["evaluator_model"])
            results.append({**saved, "metrics": generated.get("metrics")})
    except Exception as exc:
        web_logger.exception("Personality Studio comparison failed")
        raise HTTPException(status_code=502, detail=f"Local comparison failed: {type(exc).__name__}")
    return {"results": results, "controlled_input": prompt, "note": "Same prompt and selected local models; generation variability remains.", "active_configuration_unchanged": True}


@app.post("/api/dx/personality/evaluate-batch")
async def dx_personality_evaluate_batch(data: dict):
    from fastapi import HTTPException
    prompts = data.get("prompts")
    try:
        traits = validate_traits(data.get("traits"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 20 or any(not isinstance(item, str) or not item.strip() or len(item) > 6000 for item in prompts):
        raise HTTPException(status_code=422, detail="Provide 1–20 non-empty test messages, each up to 6,000 characters.")
    try:
        model = _studio_validate_model(data.get("model"))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 503, detail=str(exc))
    results, errors = [], []
    for index, prompt in enumerate(prompts, 1):
        try:
            generated = await run_in_threadpool(_studio_generate, prompt.strip(), traits, model)
            evaluation = await run_in_threadpool(_studio_evaluate, prompt.strip(), generated["response"], traits, generated["model"])
            evaluation["generation"] = {"model": generated["model"], "parameters": generated["generation_parameters"], "metrics": generated["metrics"]}
            record = personality_studio.record_evaluation(traits=traits, prompt=_studio_safe_text(prompt.strip()),
                response=generated["response"], model=generated["model"], evaluation=evaluation,
                evaluator_model=evaluation["evaluator_model"])
            results.append({**record, "metrics": generated.get("metrics")})
        except Exception as exc:
            web_logger.exception("Personality Studio batch item failed; item=%s", index)
            errors.append({"index": index, "message": f"Evaluation failed: {type(exc).__name__}"})
    return {"results": results, "errors": errors, "status": "completed" if not errors else "partial" if results else "failed",
            "active_configuration_unchanged": True}


@app.post("/api/dx/personality/conversation")
async def dx_personality_conversation(data: dict):
    from fastapi import HTTPException
    turns = data.get("turns")
    try:
        traits = validate_traits(data.get("traits"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not isinstance(turns, list) or not 2 <= len(turns) <= 10 or any(not isinstance(item, str) or not item.strip() or len(item) > 4000 for item in turns):
        raise HTTPException(status_code=422, detail="Provide 2–10 non-empty conversation turns, each up to 4,000 characters.")
    try:
        model = _studio_validate_model(data.get("model"))
        generated = await run_in_threadpool(_studio_generate_conversation, [item.strip() for item in turns], traits, model)
        evaluation = await run_in_threadpool(_studio_evaluate, "\n".join(f"User turn {i}: {item}" for i, item in enumerate(turns, 1)),
                                             generated["response"], traits, generated["model"])
        evaluation["conversation_turns"] = generated["turns"]
        evaluation["overall_consistency_status"] = "model_based_observation" if evaluation.get("overall_consistency") else "insufficient_evidence"
        evaluation["generation"] = {"model": generated["model"], "parameters": generated["generation_parameters"], "per_turn_metrics": generated["metrics"]}
        record = personality_studio.record_evaluation(traits=traits,
            prompt=_studio_safe_text("\n".join(f"User turn {i}: {item}" for i, item in enumerate(turns, 1))),
            response=generated["response"], model=generated["model"], evaluation=evaluation,
            evaluator_model=evaluation["evaluator_model"])
    except Exception as exc:
        web_logger.exception("Personality Studio conversation evaluation failed")
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=502, detail=f"Local conversation evaluation failed: {type(exc).__name__}")
    return {**record, "metrics": generated["metrics"], "active_configuration_unchanged": True}


@app.post("/api/dx/personality/activate")
def dx_personality_activate(data: dict):
    from fastapi import HTTPException
    try:
        active = personality_studio.activate(data.get("traits"), int(data.get("expected_version")), str(data.get("description") or "Studio configuration"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"active": active, "activated": True}


@app.post("/api/dx/personality/restore")
def dx_personality_restore(data: dict):
    from fastapi import HTTPException
    try:
        active = personality_studio.restore(str(data.get("config_id", "")), int(data.get("expected_version")))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="A saved version and current version are required.")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"active": active, "activated": active["activated"], "restored": True}


@app.post("/api/dx/personality/presets")
def dx_personality_save_preset(data: dict):
    from fastapi import HTTPException
    try:
        preset = personality_studio.save_preset(data.get("name", ""), data.get("traits"), data.get("description", ""), data.get("preset_id"))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A preset with that name already exists.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"preset": preset, "active_configuration_unchanged": True}


@app.delete("/api/dx/personality/presets/{preset_id}")
def dx_personality_delete_preset(preset_id: str):
    personality_studio.delete_preset(preset_id)
    return {"ok": True}


@app.get("/api/dx/personality/evaluations")
def dx_personality_evaluation_history():
    return {"evaluations": personality_studio.evaluations()}


@app.get("/api/dx/personality/export/{preset_id}")
def dx_personality_export_preset(preset_id: str):
    from fastapi import HTTPException
    preset = next((item for item in personality_studio.presets() if item["preset_id"] == preset_id), None)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"schema": "cynx-personality-studio-preset-v1", "name": preset["name"],
            "description": preset["description"], "traits": preset["traits"]}


@app.post("/api/dx/personality/import")
def dx_personality_import_preset(data: dict):
    from fastapi import HTTPException
    if data.get("schema") != "cynx-personality-studio-preset-v1":
        raise HTTPException(status_code=422, detail="Unsupported preset file schema.")
    try:
        preset = personality_studio.save_preset(data.get("name", "Imported draft"), data.get("traits"), data.get("description", "Imported draft"))
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=422, detail="Preset is invalid or its name is already used.")
    return {"preset": preset, "active_configuration_unchanged": True}


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
            suite_data = json.loads(path.read_text(encoding="utf-8"))
            cases = suite_data if isinstance(suite_data, list) else suite_data.get("scenarios", suite_data.get("questions", [])) if isinstance(suite_data, dict) else None
            if isinstance(cases, list):
                suites.append({"id": path.name, "name": path.stem.replace("_", " ").replace("-", " "), "count": len(cases),
                               "personality_contract_version": suite_data.get("contract_version") if isinstance(suite_data, dict) else None,
                               "scenario_library_version": suite_data.get("version") if isinstance(suite_data, dict) else None})
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
        suite_data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Benchmark suite could not be read")
    if isinstance(suite_data, dict):
        cases = suite_data.get("scenarios", suite_data.get("questions", []))
    else:
        cases = suite_data
    if not isinstance(cases, list):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Benchmark suite format is invalid")
    return {"id": suite_id, "cases": cases,
            "personality_contract_version": suite_data.get("contract_version") if isinstance(suite_data, dict) else None,
            "scenario_library_version": suite_data.get("version") if isinstance(suite_data, dict) else None}


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
        raw_response_time = item.get("response_time")
        try:
            response_time = float(raw_response_time) if raw_response_time is not None else None
            if response_time is not None and (not math.isfinite(response_time) or response_time < 0):
                response_time = None
        except (TypeError, ValueError):
            response_time = None
        scored.append({
            "test_id": str(item.get("test_id", ""))[:200],
            "category": category,
            "question": question,
            "response": response_text,
            # Missing timing is unavailable, not a measured zero-second response.
            "response_time": response_time,
            "failed": bool(item.get("failed", False)),
            "error": "Request failed" if item.get("failed") else None,
            "tools": item.get("tools", []) if isinstance(item.get("tools", []), list) else [],
            "analysis": analysis,
            "scores": scores,
        })
    timings = [row["response_time"] for row in scored if row["response_time"] is not None]
    score_values = [
        row["scores"]["overall"] for row in scored
        if not row["failed"] and isinstance(row.get("scores"), dict)
        and isinstance(row["scores"].get("overall"), (int, float))
        and not isinstance(row["scores"].get("overall"), bool)
    ]
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
        "average_response_time": round(statistics.mean(timings), 3) if timings else None,
        "median_response_time": round(statistics.median(timings), 3) if timings else None,
        "average_score": round(statistics.mean(score_values), 2) if score_values else None,
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


@app.get("/api/dx/benchmark/watchdog")
def dx_benchmark_watchdog(run_id: str | None = None, baseline_id: str | None = None):
    """Return read-only watchdog findings for persisted benchmark runs."""
    from fastapi import HTTPException
    report = BenchmarkWatchdog(benchmark_runs.results_dir).report(run_id, baseline_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return report


@app.get("/api/dx/benchmark/personality/history")
def dx_personality_history(run_id: str | None = None, baseline_id: str | None = None, limit: int = 50):
    from fastapi import HTTPException
    try:
        if run_id:
            personality_diagnostics._run_path(run_id)
        if baseline_id:
            personality_diagnostics._run_path(baseline_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return personality_diagnostics.history(run_id=run_id, baseline_id=baseline_id, limit=limit)


@app.post("/api/dx/benchmark/personality/{run_id}/evaluate")
async def dx_evaluate_personality(run_id: str, refresh: bool = False):
    from fastapi import HTTPException
    try:
        return await run_in_threadpool(personality_diagnostics.evaluate_run, run_id, refresh=refresh)
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/dx/benchmark/personality/{run_id}/review-baseline")
def dx_review_personality_baseline(run_id: str):
    from fastapi import HTTPException
    try:
        return personality_diagnostics.mark_reviewed_baseline(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/dx/benchmark/personality/{run_id}")
def dx_personality_run(run_id: str):
    from fastapi import HTTPException
    try:
        personality_diagnostics._run_path(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return personality_diagnostics.history(run_id=run_id)


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
    captured_trace_events = []
    if stored_trace_callback:
        def personality_trace_callback(details):
            try:
                if details.get("stage"):
                    observed_trace_stages.add(details["stage"])
                captured_trace_events.append({
                    "stage": details.get("stage"),
                    "status": details.get("status", "observed"),
                    "details": {key: value for key, value in details.items()
                                if key not in {"stage", "status"}},
                })
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
                    "metrics": {
                        **generation_metrics({"personality_trace": {"events": captured_trace_events}}),
                        "response_time_seconds": elapsed,
                    },
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


async def _dispatch_benchmark_scenario(data: dict):
    """Run scenario turns as separate ordinary chat requests in one conversation."""
    run_id = data.get("_benchmark_run_id")
    question_id = data.get("_benchmark_question_id")
    conversation_id = data.get("conversation_id")
    turns = data.get("turns") or []
    turn_records = []
    pipeline_history = []
    started = time.perf_counter()
    for index, message in enumerate(turns):
        request_id = data.get("request_id") if index == 0 else str(uuid.uuid4())
        if run_id and question_id:
            benchmark_runs.register_question_request(run_id, question_id, request_id, index + 1)
        try:
            result = await _dispatch_chat({"message": message, "request_id": request_id, "conversation_id": conversation_id})
        except Exception:
            web_logger.exception("Personality scenario turn failed; run_id=%s question_id=%s request_id=%s", run_id, question_id, request_id)
            events = pipeline_events.read(request_id).get("events", [])
            pipeline_history.extend({**event, "request_id": request_id, "turn_index": index + 1} for event in events)
            return {
                "response": turn_records[-1]["response"] if turn_records else "",
                "response_time": round(time.perf_counter() - started, 3),
                "conversation_turns": turn_records,
                "pipeline_events": pipeline_history,
                "terminal_request_id": request_id,
                "failed": True,
                "error": "A scenario turn failed. Inspect its request ID in the benchmark diagnostics.",
            }
        events = pipeline_events.read(request_id).get("events", [])
        pipeline_history.extend({**event, "request_id": request_id, "turn_index": index + 1} for event in events)
        turn_expectations = data.get("turn_expectations") or []
        expected_tools = turn_expectations[index].get("expected_tools") if index < len(turn_expectations) and isinstance(turn_expectations[index], dict) else None
        actual_tools = sorted({str(event.get("name")) for event in events if event.get("type") == "tool" and event.get("name")})
        turn_records.append({
            "turn_index": index + 1,
            "user_message": message,
            "response": result.get("response", ""),
            "request_id": request_id,
            "response_time_seconds": result.get("response_time"),
            "metrics": result.get("metrics") or {},
            "cancelled": bool(result.get("cancelled")),
            "tools": actual_tools,
            "expected_tools": expected_tools,
        })
        if result.get("cancelled"):
            return {
                "response": turn_records[-1]["response"],
                "response_time": round(time.perf_counter() - started, 3),
                "conversation_turns": turn_records,
                "pipeline_events": pipeline_history,
                "terminal_request_id": request_id,
                "cancelled": True,
            }
    return {
        "response": turn_records[-1]["response"] if turn_records else "",
        "response_time": round(time.perf_counter() - started, 3),
        "conversation_turns": turn_records,
        "pipeline_events": pipeline_history,
        "terminal_request_id": turn_records[-1]["request_id"] if turn_records else None,
    }


def _dispatch_benchmark_question(data: dict):
    """Use the application chat request pathway for every benchmark turn."""
    if data.get("turns"):
        return asyncio.run(_dispatch_benchmark_scenario(data))
    return asyncio.run(_dispatch_chat(data))


personality_diagnostics = PersonalityDiagnosticsService(DX_BENCHMARK_RUNS, ollama_client=ollama_client)

benchmark_runs = BenchmarkRunManager(
    BENCHMARK_SUITES,
    DX_BENCHMARK_RUNS,
    pipeline_events,
    _dispatch_benchmark_question,
    on_finished=personality_diagnostics.queue_evaluate,
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
