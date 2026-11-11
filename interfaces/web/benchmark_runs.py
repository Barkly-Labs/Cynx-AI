"""Persistent background manager for DX benchmark runs.

The manager owns execution and JSON snapshots independently of browser state.
Each answer is dispatched through the same application chat dispatcher used by
POST /chat; this module does not call Ollama or construct a second ChatEngine.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from benchmark.analyzer import analyze_response
from benchmark.scoring import score_response


logger = logging.getLogger("cynx.web.benchmark")


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
    start = run.get("created_at")
    end = run.get("finished_at") if run.get("status") in {"completed", "completed_with_failures", "stopped", "failed"} else None
    if not start:
        return round(run.get("elapsed_total_seconds", 0.0), 3)
    try:
        end_time = datetime.fromisoformat(end) if end else datetime.now(timezone.utc)
        return max(0.0, round((end_time - datetime.fromisoformat(start)).total_seconds(), 3))
    except (ValueError, TypeError):
        return round(run.get("elapsed_total_seconds", 0.0), 3)


class BenchmarkRunManager:
    """Own queued execution, cancellation, reconnectable events and persistence."""

    ACTIVE_STATES = {"running", "pausing", "stopping", "paused"}

    def __init__(self, suites_dir: Path, results_dir: Path, pipeline_events, dispatch: Callable):
        self.suites_dir = Path(suites_dir).resolve()
        self.results_dir = Path(results_dir).resolve()
        self.pipeline_events = pipeline_events
        self.dispatch = dispatch
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
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

    @staticmethod
    def _tool_summary(events: list[dict]) -> list[dict]:
        calls = {}
        for event in events:
            if event.get("type") != "tool" or not event.get("name"):
                continue
            key = event.get("invocation_id") or f"{event['name']}:{len(calls)}"
            item = calls.setdefault(key, {
                "name": event["name"], "invocation_id": event.get("invocation_id"),
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
        value["counts"] = self._counts(run)
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
            cases = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Benchmark suite could not be read") from exc
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
                if not isinstance(case, dict) or not isinstance(case.get("question"), str):
                    continue
                questions.append({
                    "question_id": str(uuid.uuid4()),
                    "position": index + 1,
                    "test_id": str(case.get("test_id", index + 1)),
                    "category": str(case.get("category", "unknown")),
                    "question": case["question"],
                    "test": case,
                    "status": "pending",
                    "quality_status": "unscored",
                    "response": "",
                    "score": None,
                    "analysis": None,
                    "error": None,
                    "request_id": None,
                    "tools": [],
                    "metrics": {"response_time_seconds": None, "ttft_seconds": None, "tokens_generated": None, "tokens_per_second": None},
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
                    return

                request_id = str(uuid.uuid4())
                question["status"] = "running"
                question["request_id"] = request_id
                question["started_at"] = _now()
                run["current_question_id"] = question["question_id"]
                run["current_request_id"] = request_id
                run["status"] = "running"
                self._append(run, "question_started", question_id=question["question_id"], position=question["position"], request_id=request_id)
                self._write(run)
                payload = {"message": question["question"], "request_id": request_id}

            try:
                result = self.dispatch(payload)
                response_text = str(result.get("response", "") or "")
                events = self.pipeline_events.read(request_id).get("events", [])
                tools = self._tool_summary(events)
                if result.get("cancelled"):
                    outcome = "interrupted"
                    error = "This question was cancelled before CYN-X returned a response."
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
                request_trace = [
                    {
                        "id": event.get("id"),
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
                logger.exception("Benchmark question failed; run_id=%s request_id=%s", run_id, request_id)
                response_text = ""
                tools = []
                score = analysis = None
                quality_status = "unscored"
                outcome = "failed"
                error = "CYN-X could not complete this question. Inspect the request trace for details."
                response_time = None
                request_trace = [
                    {"id": event.get("id"), "type": event.get("type"), "stage": event.get("stage"),
                     "status": event.get("status"), "elapsed_seconds": event.get("elapsed_seconds"),
                     "tool_name": event.get("name") if event.get("type") == "tool" else None}
                    for event in self.pipeline_events.read(request_id).get("events", [])
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
                question["score"] = score
                question["analysis"] = analysis
                question["error"] = error
                question["tools"] = tools
                question["request_events"] = request_trace
                question["finished_at"] = now
                question["duration_seconds"] = _elapsed_since(question.get("started_at"))
                question["metrics"]["response_time_seconds"] = response_time if response_time is not None else question["duration_seconds"]
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
            return self._public(self._read(run_id), after_event)

    def updates(self, run_id: str, after_event: int = 0) -> dict:
        with self._lock:
            run = self._read(run_id)
            value = self._public(run, after_event)
            changed_ids = {
                event.get("question_id") for event in value["events"]
                if event.get("question_id")
            }
            if run.get("current_question_id"):
                changed_ids.add(run["current_question_id"])
            value["questions"] = [
                question for question in run.get("questions", [])
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
        scores = [q["score"].get("overall") for q in run.get("questions", []) if isinstance(q.get("score"), dict) and isinstance(q["score"].get("overall"), (int, float))]
        return round(sum(scores) / len(scores), 2) if scores else None

    @staticmethod
    def _average_time(run: dict):
        values = [q["metrics"].get("response_time_seconds") for q in run.get("questions", []) if isinstance(q.get("metrics", {}).get("response_time_seconds"), (int, float))]
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
            self._write(run)
        if request_id:
            self.pipeline_events.request_cancel(request_id)
        return self.get(run_id)

    def delete_completed(self) -> int:
        deleted = 0
        with self._lock:
            for path in self.results_dir.glob("*.json"):
                try:
                    run = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if run.get("schema") == "cynx-dx-benchmark-run-v1" and run.get("status") in self.ACTIVE_STATES:
                    continue
                path.unlink(missing_ok=True)
                deleted += 1
        return deleted
