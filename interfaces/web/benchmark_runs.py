"""Persistent background manager for DX benchmark runs.

The manager owns execution and JSON snapshots independently of browser state.
Each answer is dispatched through the same application chat dispatcher used by
POST /chat; this module does not call Ollama or construct a second ChatEngine.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from benchmark.analyzer import analyze_response
from benchmark.scoring import score_response
from benchmark.telemetry import generation_metrics, question_metrics


logger = logging.getLogger("cynx.web.benchmark")

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret|authorization)\s*([:=])\s*([^\s,;]+)"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{24,})\b"),
)
_HIDDEN_REASONING = re.compile(r"(?is)<think>.*?</think>|<analysis>.*?</analysis>")
_STACK_TRACE = re.compile(r"(?s)Traceback \(most recent call last\):.*$")


def _redact_trace(value):
    """Keep trace content useful while removing common credential forms."""
    if isinstance(value, dict):
        return {
            str(key): ("[REDACTED]" if re.search(r"(?i)(^|[_-])(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|credential)([_-]|$)", str(key))
                       else _redact_trace(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_trace(item) for item in value[:500]]
    if isinstance(value, str):
        result = _STACK_TRACE.sub("[RAW STACK TRACE REDACTED]", value[:50000])
        result = _HIDDEN_REASONING.sub("[HIDDEN REASONING REDACTED]", result)
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]" if m.lastindex and m.lastindex >= 3 else "Bearer [REDACTED]", result)
        return result
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_since(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return max(0.0, round((datetime.now(timezone.utc) - datetime.fromisoformat(value)).total_seconds(), 3))
    except (ValueError, TypeError):
        return 0.0


def _run_elapsed(run: dict) -> float:
    # New run snapshots accumulate only time spent executing, excluding time
    # paused between questions. Fall back to wall-clock timestamps for older
    # snapshots that predate elapsed_total_seconds.
    accumulated = run.get("elapsed_total_seconds")
    if isinstance(accumulated, (int, float)) and not isinstance(accumulated, bool) and math.isfinite(accumulated):
        active_segment = _elapsed_since(run.get("started_at")) if run.get("started_at") else 0.0
        return round(max(0.0, float(accumulated)) + active_segment, 3)
    start = run.get("created_at")
    end = run.get("finished_at") if run.get("status") in {"completed", "completed_with_failures", "stopped", "failed", "interrupted"} else None
    if not start:
        return 0.0
    try:
        end_time = datetime.fromisoformat(end) if end else datetime.now(timezone.utc)
        return max(0.0, round((end_time - datetime.fromisoformat(start)).total_seconds(), 3))
    except (ValueError, TypeError):
        return round(run.get("elapsed_total_seconds", 0.0), 3)


class BenchmarkRunManager:
    """Own queued execution, cancellation, reconnectable events and persistence."""

    ACTIVE_STATES = {"running", "pausing", "stopping", "paused"}

    def __init__(self, suites_dir: Path, results_dir: Path, pipeline_events, dispatch: Callable, on_finished: Callable | None = None):
        self.suites_dir = Path(suites_dir).resolve()
        self.results_dir = Path(results_dir).resolve()
        self.pipeline_events = pipeline_events
        self.dispatch = dispatch
        self.on_finished = on_finished
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._trace_callbacks: dict[str, Callable] = {}
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._recover_interrupted_runs()

    def _path(self, run_id: str) -> Path:
        try:
            normalized = str(uuid.UUID(str(run_id)))
        except (ValueError, TypeError, AttributeError):
            raise KeyError("Benchmark run not found")
        return self.results_dir / f"{normalized}.json"

    def _read(self, run_id: str) -> dict:
        path = self._path(run_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise KeyError("Benchmark run not found") from exc
        if data.get("schema") != "cynx-dx-benchmark-run-v1":
            raise KeyError("Benchmark run not found")
        return data

    def _legacy_public(self, run_id: str) -> dict:
        """Expose saved pre-manager benchmark summaries as read-only runs."""
        path = self._path(run_id)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise KeyError("Benchmark run not found") from exc
        if not isinstance(saved, dict) or saved.get("schema") == "cynx-dx-benchmark-run-v1":
            raise KeyError("Benchmark run not found")
        rows = saved.get("results")
        if not isinstance(rows, list):
            raise KeyError("Benchmark run not found")

        questions = []
        namespace = uuid.UUID(run_id)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            score = row.get("scores") if isinstance(row.get("scores"), dict) else row.get("score")
            score = score if isinstance(score, dict) else None
            rubric_total = score.get("rubric_total") if score else None
            rubric_passed = score.get("rubric_passed") if score else None
            quality = "unscored"
            if isinstance(rubric_total, (int, float)) and rubric_total > 0 and isinstance(rubric_passed, (int, float)):
                quality = "passed" if rubric_passed == rubric_total else "failed"
            elif score and isinstance(score.get("overall"), (int, float)):
                quality = "scored"
            response_time = row.get("response_time")
            if not isinstance(response_time, (int, float)) or isinstance(response_time, bool) or not math.isfinite(response_time) or response_time < 0:
                response_time = None
            failed = bool(row.get("failed"))
            test_id = str(row.get("test_id") or f"question-{index + 1}")
            questions.append({
                "question_id": str(uuid.uuid5(namespace, f"{index + 1}:{test_id}")),
                "position": index + 1, "test_id": test_id,
                "category": str(row.get("category") or "unknown"),
                "question": str(row.get("question") or ""),
                "response": str(row.get("response") or ""),
                "status": "failed" if failed else "completed",
                "quality_status": "unscored" if failed else quality,
                "score": score, "analysis": row.get("analysis"),
                "error": str(row.get("error") or "Request failed") if failed else None,
                "tools": row.get("tools") if isinstance(row.get("tools"), list) else [],
                "tool_telemetry_available": row.get("tool_telemetry_available") is True or (
                    isinstance(row.get("tools"), list) and bool(row.get("tools"))
                ),
                "request_events": [], "request_id": None,
                "terminal_request_id": None,
                "started_at": None, "finished_at": None,
                "duration_seconds": response_time,
                "metrics": {"response_time_seconds": response_time, "ttft_seconds": None,
                            "prompt_tokens": None, "completion_tokens": None, "tokens_generated": None,
                            "total_tokens": None, "prompt_evaluation_duration_seconds": None,
                            "generation_duration_seconds": None, "tokens_per_second": None},
            })
        failures = sum(q["status"] == "failed" for q in questions)
        run_status = "incomplete" if not questions else "completed_with_failures" if failures else "completed"
        value = {
            "legacy_record": True, "run_id": run_id,
            "created_at": saved.get("created_at"), "suite": saved.get("suite"),
            "name": saved.get("suite") or "Legacy benchmark run", "mode": saved.get("mode"),
            "status": run_status, "questions": questions, "events": [],
            "current_question_id": None, "current_request_id": None,
            "elapsed_seconds": None,
        }
        value["counts"] = self._counts(value)
        return value

    def _write(self, run: dict) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(run["run_id"])
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _append(run: dict, event_type: str, **details) -> None:
        events = run.setdefault("events", [])
        events.append({
            "id": len(events) + 1,
            "type": event_type,
            "timestamp": _now(),
            **details,
        })

    def record_personality_trace(self, run_id: str, question_id: str, request_id: str, details: dict) -> None:
        """Persist an observed runtime trace event against its owning question."""
        with self._lock:
            try:
                run = self._read(run_id)
            except KeyError:
                return
            question = next((q for q in run.get("questions", []) if q.get("question_id") == question_id), None)
            if question is None or request_id not in (question.get("request_ids") or [question.get("request_id")]):
                return
            trace = question.setdefault("personality_trace", {"schema": "cynx-personality-trace-v1", "events": []})
            safe = _redact_trace(details)
            event = {
                "event_id": str(uuid.uuid4()), "run_id": run_id,
                "question_id": question_id, "request_id": request_id,
                "stage": safe.pop("stage", "unknown"), "status": safe.pop("status", "observed"),
                "timestamp": _now(), "details": safe,
            }
            trace["events"].append(event)
            trace["available"] = True
            self._append(run, "personality_trace_updated", question_id=question_id,
                         request_id=request_id, trace_event_id=event["event_id"])
            self._write(run)

    def register_question_request(self, run_id: str, question_id: str, request_id: str) -> None:
        """Associate an additional real chat request with a multi-turn scenario."""
        with self._lock:
            try:
                run = self._read(run_id)
            except KeyError:
                return
            question = next((q for q in run.get("questions", []) if q.get("question_id") == question_id), None)
            if question is None:
                return
            request_ids = question.setdefault("request_ids", [question.get("request_id")])
            if request_id not in request_ids:
                request_ids.append(request_id)
            run["current_request_id"] = request_id
            self._trace_callbacks[request_id] = (
                lambda details, rid=run_id, qid=question_id, req=request_id:
                self.record_personality_trace(rid, qid, req, details)
            )
            self._append(run, "question_turn_request_registered", question_id=question_id, request_id=request_id)
            self._write(run)

    def _clear_question_trace_callbacks(self, run_id: str, question_id: str) -> None:
        with self._lock:
            try:
                run = self._read(run_id)
            except KeyError:
                return
            question = next((q for q in run.get("questions", []) if q.get("question_id") == question_id), None)
            for request_id in (question or {}).get("request_ids", []):
                self._trace_callbacks.pop(request_id, None)

    def trace_callback(self, request_id: str):
        with self._lock:
            return self._trace_callbacks.get(request_id)

    @staticmethod
    def _tool_summary(events: list[dict]) -> list[dict]:
        calls = {}
        for event in events:
            if event.get("type") != "tool" or not event.get("name"):
                continue
            request_id = event.get("request_id")
            invocation_id = event.get("invocation_id")
            key = (request_id, invocation_id) if invocation_id else None
            if key is None and event.get("status") in {"completed", "failed"}:
                key = next((candidate for candidate, item in calls.items()
                            if item.get("request_id") == request_id and item.get("name") == event["name"]
                            and item.get("status") == "started"), None)
            if key is None:
                key = (request_id, f"{event['name']}:{len(calls)}")
            item = calls.setdefault(key, {
                "name": event["name"], "invocation_id": invocation_id, "request_id": request_id,
                "status": "started", "duration_seconds": None,
            })
            if event.get("status") == "started":
                item["started_elapsed_seconds"] = event.get("elapsed_seconds")
            elif event.get("status") in {"completed", "failed"}:
                item["status"] = event["status"]
                start = item.get("started_elapsed_seconds")
                end = event.get("elapsed_seconds")
                if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                    item["duration_seconds"] = round(max(0, end - start), 3)
        for item in calls.values():
            item.pop("started_elapsed_seconds", None)
        return list(calls.values())

    @staticmethod
    def _counts(run: dict) -> dict:
        questions = run.get("questions", [])
        states = [question.get("status") for question in questions]
        rubric_passed = sum(question.get("quality_status") == "passed" for question in questions)
        rubric_failed = sum(question.get("quality_status") == "failed" for question in questions)
        tool_failures = sum(
            1 for question in questions for event in question.get("tools", [])
            if isinstance(event, dict) and event.get("status") == "failed"
        )
        return {
            "total": len(questions),
            "completed": sum(state == "completed" for state in states),
            "pending": sum(state == "pending" for state in states),
            "running": sum(state == "running" for state in states),
            "interrupted": sum(state == "interrupted" for state in states),
            "failed": sum(state == "failed" for state in states) + rubric_failed,
            "passed": rubric_passed,
            "tool_failures": tool_failures,
            "partial_tool_failures": sum(
                question.get("status") == "completed" and any(
                    isinstance(event, dict) and event.get("status") == "failed"
                    for event in question.get("tools", [])
                ) for question in questions
            ),
            "scored_without_pass_rule": sum(question.get("quality_status") == "scored" for question in questions),
        }

    def _public(self, run: dict, after_event: int = 0) -> dict:
        value = dict(run)
        value["questions"] = [
            {**question, "metrics": question_metrics(question)}
            for question in run.get("questions", [])
        ]
        value["counts"] = self._counts(run)
        value["metrics_summary"] = self._aggregate_metrics(value["questions"])
        value["elapsed_seconds"] = _run_elapsed(run)
        value["events"] = [event for event in run.get("events", []) if event.get("id", 0) > after_event]
        current_id = run.get("current_request_id")
        if current_id:
            current_events = self.pipeline_events.read(current_id)
            value["live_request_events"] = current_events["events"]
            value["live_request_done"] = current_events["done"]
        else:
            value["live_request_events"] = []
            value["live_request_done"] = False
        return value

    @staticmethod
    def _aggregate_metrics(questions: list[dict]) -> dict:
        """Summarize actual measured question metrics, retaining coverage counts."""
        rows = [question_metrics(question) for question in questions
                if question.get("status") != "pending"]

        def valid(value):
            return (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) and value >= 0)

        def total(key):
            values = [row[key] for row in rows if valid(row.get(key))]
            return {"total": sum(values) if values else None,
                    "measured_questions": len(values), "eligible_questions": len(rows)}

        ttfts = [row["ttft_seconds"] for row in rows if valid(row.get("ttft_seconds"))]
        durations = [row["response_time_seconds"] for row in rows if valid(row.get("response_time_seconds"))]
        tps_rows = [row for row in rows if valid(row.get("completion_tokens"))
                    and valid(row.get("generation_duration_seconds"))
                    and row["generation_duration_seconds"] > 0]
        tps_tokens = sum(row["completion_tokens"] for row in tps_rows)
        tps_duration = sum(row["generation_duration_seconds"] for row in tps_rows)
        return {
            "prompt_tokens": total("prompt_tokens"),
            "completion_tokens": total("completion_tokens"),
            "total_tokens": total("total_tokens"),
            "generation_duration_seconds": total("generation_duration_seconds"),
            "request_duration_seconds": {
                "total": sum(durations) if durations else None,
                "average": sum(durations) / len(durations) if durations else None,
                "measured_questions": len(durations), "eligible_questions": len(rows),
            },
            "ttft_seconds": {
                "average": sum(ttfts) / len(ttfts) if ttfts else None,
                "measured_questions": len(ttfts), "eligible_questions": len(rows),
            },
            "tokens_per_second": {
                "value": tps_tokens / tps_duration if tps_duration > 0 else None,
                "measured_questions": len(tps_rows), "eligible_questions": len(rows),
            },
        }

    def _recover_interrupted_runs(self) -> None:
        for path in self.results_dir.glob("*.json"):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if run.get("schema") != "cynx-dx-benchmark-run-v1" or run.get("status") not in {"running", "pausing", "stopping"}:
                continue
            active = next((q for q in run.get("questions", []) if q.get("status") == "running"), None)
            if active:
                active["status"] = "interrupted"
                active["finished_at"] = _now()
                active["duration_seconds"] = _elapsed_since(active.get("started_at"))
                active["error"] = "The CYN-X server restarted before this question completed."
            run["status"] = "interrupted"
            run["current_question_id"] = None
            run["current_request_id"] = None
            run["interruption_reason"] = "server_restart"
            run["elapsed_total_seconds"] = run.get("elapsed_total_seconds", 0) + _elapsed_since(run.get("started_at"))
            run["started_at"] = None
            self._append(run, "run_interrupted", reason="server_restart")
            try:
                self._write(run)
            except OSError:
                logger.exception("Unable to persist interrupted benchmark run %s", run.get("run_id"))

    def start(self, suite_id: str, mode: str, idempotency_key: str) -> dict:
        path = (self.suites_dir / suite_id).resolve()
        if path.parent != self.suites_dir or path.suffix.lower() != ".json" or not path.is_file():
            raise ValueError("Benchmark suite not found")
        try:
            suite_data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Benchmark suite could not be read") from exc
        if isinstance(suite_data, dict):
            cases = suite_data.get("scenarios", suite_data.get("questions", []))
            contract_version = suite_data.get("contract_version")
            scenario_library_version = suite_data.get("version")
        else:
            cases = suite_data
            contract_version = None
            scenario_library_version = None
        if not isinstance(cases, list) or not cases or len(cases) > 500:
            raise ValueError("Benchmark suite must contain between 1 and 500 questions")
        if len(idempotency_key) < 8 or len(idempotency_key) > 160:
            raise ValueError("A valid start request ID is required")

        with self._lock:
            for saved_path in self.results_dir.glob("*.json"):
                try:
                    existing = json.loads(saved_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if existing.get("schema") != "cynx-dx-benchmark-run-v1":
                    continue
                if existing.get("idempotency_key") == idempotency_key:
                    return self._public(existing)
                if existing.get("status") in self.ACTIVE_STATES:
                    raise RuntimeError(existing.get("run_id", "An active benchmark already exists"))

            run_id = str(uuid.uuid4())
            questions = []
            for index, case in enumerate(cases):
                turns = case.get("turns") if isinstance(case, dict) else None
                turns = [str(turn).strip() for turn in turns if isinstance(turn, str) and turn.strip()] if isinstance(turns, list) else []
                question_text = case.get("question") if isinstance(case, dict) else None
                if not isinstance(question_text, str) or not question_text.strip():
                    question_text = turns[0] if turns else None
                if not isinstance(case, dict) or not isinstance(question_text, str) or not question_text.strip() or len(turns) > 20:
                    raise ValueError(f"Benchmark suite contains an invalid question at position {index + 1}")
                questions.append({
                    "question_id": str(uuid.uuid4()),
                    "position": len(questions) + 1,
                    "test_id": str(case.get("test_id", index + 1)),
                    "category": str(case.get("category", "unknown")),
                    "question": question_text,
                    "turns": turns,
                    "turn_expectations": case.get("turn_expectations", []),
                    "scenario_id": case.get("scenario_id"),
                    "scenario_version": case.get("scenario_version", scenario_library_version),
                    "scenario_category": case.get("scenario_category", case.get("category")),
                    "target_dimensions": case.get("target_dimensions", []),
                    "expected_behavior": case.get("expected_behavior"),
                    "failure_conditions": case.get("failure_conditions", []),
                    "test": case,
                    "status": "pending",
                    "quality_status": "unscored",
                    "response": "",
                    "score": None,
                    "analysis": None,
                    "error": None,
                    "request_id": None,
                    "terminal_request_id": None,
                    "tool_telemetry_available": None,
                    "personality_trace": {"schema": "cynx-personality-trace-v1", "available": False, "events": []},
                    "tools": [],
                    "metrics": {"response_time_seconds": None, "ttft_seconds": None,
                                "prompt_tokens": None, "completion_tokens": None, "tokens_generated": None,
                                "total_tokens": None, "prompt_evaluation_duration_seconds": None,
                                "generation_duration_seconds": None, "tokens_per_second": None},
                    "started_at": None,
                    "finished_at": None,
                    "duration_seconds": None,
                })
            if not questions:
                raise ValueError("Benchmark suite has no valid question records")
            now = _now()
            run = {
                "schema": "cynx-dx-benchmark-run-v1",
                "run_id": run_id,
                "idempotency_key": idempotency_key,
                "name": path.stem.replace("_", " ").replace("-", " "),
                "suite": suite_id,
                "personality_contract_version": contract_version or next((case.get("contract_version") for case in cases if isinstance(case, dict) and case.get("contract_version")), None),
                "scenario_library_version": scenario_library_version or next((case.get("scenario_version") for case in cases if isinstance(case, dict) and case.get("scenario_version")), None),
                "mode": "manual" if mode == "manual" else "automatic",
                "status": "running",
                "created_at": now,
                "started_at": now,
                "finished_at": None,
                "elapsed_total_seconds": 0.0,
                "current_question_id": None,
                "current_request_id": None,
                "pause_requested": False,
                "stop_requested": False,
                "questions": questions,
                "events": [],
            }
            self._append(run, "run_started", question_count=len(questions), mode=run["mode"])
            self._write(run)
            self._launch(run_id, one_question=False)
            return self._public(run)

    def _launch(self, run_id: str, one_question: bool) -> None:
        thread = threading.Thread(target=self._worker, args=(run_id, one_question), daemon=True, name=f"cynx-benchmark-{run_id[:8]}")
        self._threads[run_id] = thread
        thread.start()

    def _worker(self, run_id: str, one_question: bool) -> None:
        processed = 0
        while True:
            with self._lock:
                try:
                    run = self._read(run_id)
                except KeyError:
                    return
                if run.get("stop_requested"):
                    run["status"] = "stopped"
                    run["finished_at"] = _now()
                    if run.get("started_at"):
                        run["elapsed_total_seconds"] += _elapsed_since(run["started_at"])
                    run["started_at"] = None
                    run["current_question_id"] = None
                    run["current_request_id"] = None
                    self._append(run, "run_stopped")
                    self._write(run)
                    return
                if run.get("pause_requested"):
                    run["status"] = "paused"
                    run["pause_requested"] = False
                    if run.get("started_at"):
                        run["elapsed_total_seconds"] += _elapsed_since(run["started_at"])
                    run["started_at"] = None
                    run["current_question_id"] = None
                    run["current_request_id"] = None
                    self._append(run, "run_paused")
                    self._write(run)
                    return
                question = next((item for item in run["questions"] if item["status"] == "pending"), None)
                if question is None:
                    counts = self._counts(run)
                    run["status"] = "failed" if counts["completed"] == 0 and (counts["failed"] or counts["interrupted"]) else "completed_with_failures" if counts["failed"] or counts["interrupted"] or counts["tool_failures"] else "completed"
                    run["finished_at"] = _now()
                    if run.get("started_at"):
                        run["elapsed_total_seconds"] += _elapsed_since(run["started_at"])
                    run["started_at"] = None
                    run["current_question_id"] = None
                    run["current_request_id"] = None
                    self._append(run, "run_finished", status=run["status"], counts=counts)
                    self._write(run)
                    if self.on_finished:
                        self.on_finished(run_id)
                    return

                request_id = str(uuid.uuid4())
                question["status"] = "running"
                question["request_id"] = request_id
                question["request_ids"] = [request_id]
                question["started_at"] = _now()
                run["current_question_id"] = question["question_id"]
                run["current_request_id"] = request_id
                run["status"] = "running"
                self._append(run, "question_started", question_id=question["question_id"], position=question["position"], request_id=request_id)
                self._write(run)
                payload = {"message": question["question"], "request_id": request_id}
                if question.get("turns"):
                    payload.update({
                        "turns": question["turns"],
                        "turn_expectations": question.get("turn_expectations", []),
                        "conversation_id": str(uuid.uuid4()),
                        "_benchmark_run_id": run_id,
                        "_benchmark_question_id": question["question_id"],
                    })
                self._trace_callbacks[request_id] = (
                    lambda details, rid=run_id, qid=question["question_id"], req=request_id:
                    self.record_personality_trace(rid, qid, req, details)
                )

            result = {}
            try:
                result = self.dispatch(payload)
                self._clear_question_trace_callbacks(run_id, question["question_id"])
                response_text = str(result.get("response", "") or "")
                events = result.get("pipeline_events") if isinstance(result.get("pipeline_events"), list) else self.pipeline_events.read(request_id).get("events", [])
                tools = result.get("tools") if isinstance(result.get("tools"), list) else self._tool_summary(events)
                conversation_turns = result.get("conversation_turns") if isinstance(result.get("conversation_turns"), list) else []
                if result.get("cancelled"):
                    outcome = "interrupted"
                    error = "This question was cancelled before CYN-X returned a response."
                    score = analysis = None
                    quality_status = "unscored"
                elif result.get("failed"):
                    outcome = "failed"
                    error = str(result.get("error") or "A scenario turn did not complete.")[:500]
                    score = analysis = None
                    quality_status = "unscored"
                else:
                    score = score_response(response_text, question["category"], test=question["test"])
                    analysis = analyze_response(response_text)
                    rubric_total = score.get("rubric_total")
                    quality_status = (
                        "passed" if rubric_total and score.get("rubric_passed") == rubric_total
                        else "failed" if rubric_total
                        else "scored"
                    )
                    outcome = "completed"
                    error = None
                response_time = result.get("response_time")
                tool_telemetry_available = isinstance(result.get("tools"), list) or bool(events)
                request_trace = [
                    {
                        "id": event.get("id"),
                        "request_id": event.get("request_id") or request_id,
                        "turn_index": event.get("turn_index"),
                        "type": event.get("type"),
                        "stage": event.get("stage"),
                        "status": event.get("status"),
                        "elapsed_seconds": event.get("elapsed_seconds"),
                        "tool_name": event.get("name") if event.get("type") == "tool" else None,
                        "action": event.get("action") if event.get("type") == "decision" else None,
                    }
                    for event in events
                ]
            except Exception:
                self._clear_question_trace_callbacks(run_id, question["question_id"])
                logger.exception("Benchmark question failed; run_id=%s request_id=%s", run_id, request_id)
                response_text = ""
                conversation_turns = []
                events = self.pipeline_events.read(request_id).get("events", [])
                tools = self._tool_summary(events)
                tool_telemetry_available = bool(events)
                score = analysis = None
                quality_status = "unscored"
                outcome = "failed"
                error = "CYN-X could not complete this question. Inspect the request trace for details."
                response_time = None
                terminal_request_id = request_id
                request_trace = [
                    {"id": event.get("id"), "request_id": event.get("request_id") or request_id,
                     "turn_index": event.get("turn_index"), "type": event.get("type"), "stage": event.get("stage"),
                     "status": event.get("status"), "elapsed_seconds": event.get("elapsed_seconds"),
                     "tool_name": event.get("name") if event.get("type") == "tool" else None}
                    for event in events
                ]

            with self._lock:
                try:
                    run = self._read(run_id)
                except KeyError:
                    return
                question = next((item for item in run["questions"] if item["question_id"] == run.get("current_question_id")), None)
                if question is None:
                    return
                now = _now()
                question["status"] = outcome
                question["quality_status"] = quality_status
                question["response"] = response_text
                question["conversation_turns"] = conversation_turns
                question["score"] = score
                question["analysis"] = analysis
                question["error"] = error
                question["terminal_request_id"] = result.get("terminal_request_id") or result.get("request_id") or request_id
                question["tools"] = tools
                question["tool_telemetry_available"] = tool_telemetry_available
                question["request_events"] = request_trace
                if question.get("personality_trace") is not None:
                    question["personality_trace"]["available"] = bool(question["personality_trace"].get("events"))
                question["finished_at"] = now
                question["duration_seconds"] = _elapsed_since(question.get("started_at"))
                question["metrics"]["response_time_seconds"] = (
                    response_time if isinstance(response_time, (int, float))
                    and not isinstance(response_time, bool) and math.isfinite(response_time) and response_time >= 0
                    else question["duration_seconds"]
                )
                question["metrics"].update(generation_metrics(question))
                run["current_question_id"] = None
                run["current_request_id"] = None
                self._append(run, "question_finished", question_id=question["question_id"], status=outcome, quality_status=quality_status)
                processed += 1
                if run.get("stop_requested"):
                    run["status"] = "stopped"
                    run["finished_at"] = now
                    run["elapsed_total_seconds"] += _elapsed_since(run.get("started_at"))
                    run["started_at"] = None
                    run["stop_requested"] = False
                    self._append(run, "run_stopped", question_id=question["question_id"])
                    self._write(run)
                    if self.on_finished:
                        self.on_finished(run_id)
                    return
                if run.get("pause_requested"):
                    run["status"] = "paused"
                    run["pause_requested"] = False
                    run["elapsed_total_seconds"] += _elapsed_since(run.get("started_at"))
                    run["started_at"] = None
                    self._append(run, "run_paused")
                    self._write(run)
                    return
                pending_remains = any(item.get("status") == "pending" for item in run["questions"])
                if run.get("mode") == "manual" and processed >= 1 and pending_remains:
                    run["status"] = "paused"
                    run["elapsed_total_seconds"] += _elapsed_since(run.get("started_at"))
                    run["started_at"] = None
                    self._append(run, "run_waiting_for_next_question")
                    self._write(run)
                    return
                self._write(run)
                if one_question and processed >= 1 and pending_remains:
                    run["status"] = "paused"
                    run["elapsed_total_seconds"] += _elapsed_since(run.get("started_at"))
                    run["started_at"] = None
                    self._append(run, "run_waiting_for_next_question")
                    self._write(run)
                    return

    def get(self, run_id: str, after_event: int = 0) -> dict:
        with self._lock:
            try:
                return self._public(self._read(run_id), after_event)
            except KeyError:
                return self._legacy_public(run_id)

    def updates(self, run_id: str, after_event: int = 0) -> dict:
        with self._lock:
            try:
                run = self._read(run_id)
            except KeyError:
                return self._legacy_public(run_id)
            value = self._public(run, after_event)
            changed_ids = {
                event.get("question_id") for event in value["events"]
                if event.get("question_id")
            }
            if run.get("current_question_id"):
                changed_ids.add(run["current_question_id"])
            value["questions"] = [
                {**question, "metrics": question_metrics(question)}
                for question in run.get("questions", [])
                if question.get("question_id") in changed_ids
            ]
            return value

    def active(self) -> dict | None:
        with self._lock:
            active = []
            for path in self.results_dir.glob("*.json"):
                try:
                    run = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if run.get("schema") == "cynx-dx-benchmark-run-v1" and run.get("status") in self.ACTIVE_STATES:
                    active.append(run)
            if not active:
                return None
            active.sort(key=lambda run: run.get("created_at", ""), reverse=True)
            return self._public(active[0])

    def latest(self) -> dict | None:
        paths = sorted(self.results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths:
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if run.get("schema") == "cynx-dx-benchmark-run-v1":
                return self._public(run)
        return None

    def list_runs(self, limit: int = 25) -> list[dict]:
        runs = []
        for path in sorted(self.results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if run.get("schema") == "cynx-dx-benchmark-run-v1":
                counts = self._counts(run)
                runs.append({
                    "run_id": run.get("run_id"), "created_at": run.get("created_at"),
                    "suite": run.get("suite"), "name": run.get("name"), "mode": run.get("mode"),
                    "status": run.get("status"), "attempted": counts["total"] - counts["pending"] - counts["running"],
                    "total": counts["total"], "successful": counts["completed"], "completed": counts["completed"],
                    "passed": counts["passed"], "failed": counts["failed"], "tool_failures": counts["tool_failures"], "partial_tool_failures": counts["partial_tool_failures"], "pending": counts["pending"],
                    "interrupted": counts["interrupted"], "average_score": self._average_score(run),
                    "average_response_time": self._average_time(run), "elapsed_seconds": _run_elapsed(run),
                })
            else:
                runs.append({key: run.get(key) for key in ("run_id", "created_at", "suite", "mode", "attempted", "successful", "failed", "tool_failures", "partial_tool_failures", "average_response_time", "median_response_time", "average_score")})
            if len(runs) >= limit:
                break
        return runs

    @staticmethod
    def _average_score(run: dict):
        scores = [q["score"].get("overall") for q in run.get("questions", [])
                  if isinstance(q.get("score"), dict)
                  and isinstance(q["score"].get("overall"), (int, float))
                  and not isinstance(q["score"].get("overall"), bool)
                  and math.isfinite(q["score"].get("overall"))]
        return round(sum(scores) / len(scores), 2) if scores else None

    @staticmethod
    def _average_time(run: dict):
        values = [q["metrics"].get("response_time_seconds") for q in run.get("questions", [])
                  if isinstance(q.get("metrics", {}).get("response_time_seconds"), (int, float))
                  and not isinstance(q["metrics"].get("response_time_seconds"), bool)
                  and math.isfinite(q["metrics"].get("response_time_seconds"))
                  and q["metrics"].get("response_time_seconds") >= 0]
        return round(sum(values) / len(values), 3) if values else None

    def pause(self, run_id: str) -> dict:
        with self._lock:
            run = self._read(run_id)
            if run.get("status") not in {"running", "pausing"}:
                raise ValueError("Only a running benchmark can be paused")
            run["pause_requested"] = True
            run["status"] = "pausing"
            self._append(run, "pause_requested", current_question_finishes_first=bool(run.get("current_question_id")))
            self._write(run)
            return self._public(run)

    def resume(self, run_id: str, next_question: bool = False) -> dict:
        with self._lock:
            run = self._read(run_id)
            if run.get("status") not in {"paused", "interrupted"}:
                raise ValueError("This benchmark is not paused or interrupted")
            one_question = bool(next_question)
            if one_question and run.get("mode") != "manual":
                raise ValueError("Run Next Question is available only in manual mode")
            if run.get("status") == "interrupted":
                run["interruption_reason"] = None
            run["status"] = "running"
            run["started_at"] = _now()
            run["pause_requested"] = False
            run["stop_requested"] = False
            self._append(run, "run_resumed", one_question=one_question)
            self._write(run)
            self._launch(run_id, one_question=one_question)
            return self._public(run)

    def stop(self, run_id: str) -> dict:
        with self._lock:
            run = self._read(run_id)
            if run.get("status") not in self.ACTIVE_STATES:
                return self._public(run)
            request_id = run.get("current_request_id")
            run["stop_requested"] = True
            if request_id:
                run["status"] = "stopping"
                self._append(run, "stop_requested", request_id=request_id)
            else:
                run["status"] = "stopped"
                run["finished_at"] = _now()
                run["elapsed_total_seconds"] += _elapsed_since(run.get("started_at"))
                run["started_at"] = None
                self._append(run, "run_stopped")
                if self.on_finished:
                    self.on_finished(run_id)
            self._write(run)
        if request_id:
            self.pipeline_events.request_cancel(request_id)
        return self.get(run_id)

    def delete_completed(self) -> int:
        deleted = 0
        deleted_run_ids = set()
        with self._lock:
            for path in self.results_dir.glob("*.json"):
                try:
                    run = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if run.get("schema") == "cynx-dx-benchmark-run-v1" and run.get("status") in self.ACTIVE_STATES:
                    continue
                if run.get("run_id"):
                    deleted_run_ids.add(str(run["run_id"]))
                path.unlink(missing_ok=True)
                deleted += 1
            for run_id in deleted_run_ids:
                (self.results_dir / "personality_diagnostics" / f"{run_id}.json").unlink(missing_ok=True)
        return deleted
