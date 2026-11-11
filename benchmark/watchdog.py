"""Read-only diagnostics for persisted CYN-X benchmark runs.

The watchdog compares saved benchmark evidence. It does not run models, score
responses, or affect request routing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_TERMINAL = {"completed", "completed_with_failures", "failed", "stopped", "interrupted"}
_REFUSAL = re.compile(r"\b(i (?:can't|cannot|won't|will not) help|i must refuse|unable to assist)\b", re.I)
_JSON_LEAK = re.compile(r"(?:```\s*json\b|\{\s*\"(?:tool|function|arguments|name)\"\s*:)", re.I)


class BenchmarkWatchdog:
    """Compare immutable run snapshots and expose evidence-backed findings."""

    def __init__(self, results_dir: str | Path):
        self.results_dir = Path(results_dir)

    def _load(self, run_id: str) -> dict[str, Any] | None:
        if not run_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
            return None
        path = self.results_dir / f"{run_id}.json"
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(run, dict):
            return None
        return self._normalize(run)

    @staticmethod
    def _normalize(run: dict[str, Any]) -> dict[str, Any]:
        questions = run.get("questions")
        if not isinstance(questions, list):
            questions = run.get("results", [])
        normalized = []
        for index, item in enumerate(questions if isinstance(questions, list) else []):
            if not isinstance(item, dict):
                continue
            test = item.get("test") if isinstance(item.get("test"), dict) else {}
            score = item.get("score") if isinstance(item.get("score"), dict) else item.get("scores")
            if not isinstance(score, dict):
                score = {}
            metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
            response = item.get("response", "")
            status = item.get("status") or ("failed" if item.get("failed") else "completed")
            normalized.append({
                **item,
                "test": test,
                "test_id": str(item.get("test_id") or test.get("test_id") or f"question-{index + 1}"),
                "category": str(item.get("category") or test.get("category") or "unknown"),
                "question": str(item.get("question") or test.get("question") or ""),
                "response": str(response or ""),
                "status": status,
                "quality_status": item.get("quality_status") or ("failed" if item.get("failed") else "unscored"),
                "score": score,
                "metrics": {**metrics, "response_time_seconds": metrics.get("response_time_seconds", item.get("response_time"))},
                "tools": item.get("tools") if isinstance(item.get("tools"), list) else [],
                "request_events": item.get("request_events") if isinstance(item.get("request_events"), list) else [],
            })
        run["questions"] = normalized
        return run

    def report(self, run_id: str | None = None, baseline_id: str | None = None) -> dict[str, Any] | None:
        runs = self._available_runs()
        current = self._load(run_id) if run_id else (runs[0] if runs else None)
        if not current:
            return None
        if baseline_id:
            baseline = self._load(baseline_id)
        else:
            baseline = next((item for item in runs if item.get("run_id") != current.get("run_id")
                             and item.get("suite") == current.get("suite")
                             and item.get("status") in _TERMINAL), None)
        if baseline and (baseline.get("run_id") == current.get("run_id") or baseline.get("suite") != current.get("suite")):
            baseline = None

        previous = {self._key(q): q for q in (baseline or {}).get("questions", [])}
        current_questions = current.get("questions", [])
        results = []
        feed = []
        regressions = 0
        for question in current_questions:
            old = previous.get(self._key(question))
            row = self._compare_question(question, old)
            results.append(row)
            if row["failure"]["failed"]:
                feed.append(self._feed_item(row))
            if row["regression"]:
                regressions += 1

        total = len(current_questions)
        passed = sum(q.get("quality_status") == "passed" for q in current_questions)
        interrupted = sum(q.get("status") == "interrupted" for q in current_questions)
        failed = sum(q.get("status") == "failed" or q.get("quality_status") == "failed" for q in current_questions)
        completed = sum(q.get("status") == "completed" for q in current_questions)
        verdicts_available = all(
            q.get("status") in {"failed", "interrupted"} or q.get("quality_status") in {"passed", "failed"}
            for q in current_questions
        )
        if current.get("status") in {"running", "pausing", "stopping", "paused"}:
            health = "running"
        elif failed or interrupted or regressions or feed:
            health = "needs_attention"
        elif total and completed == total and verdicts_available:
            health = "healthy"
        else:
            health = "incomplete"

        return {
            "schema": "cynx-benchmark-watchdog-v1",
            "run_id": current.get("run_id"),
            "baseline_run_id": (baseline or {}).get("run_id"),
            "suite": current.get("suite"),
            "status": current.get("status"),
            "health": health,
            "counts": {"total": total, "passed": passed, "failed": failed,
                       "interrupted": interrupted, "completed": completed,
                       "pending": sum(q.get("status") == "pending" for q in current_questions),
                       "regressions": regressions},
            "regression_feed": feed,
            "questions": results,
            "personality_dimensions": self._personality_dimensions(current_questions),
            "comparison_available": baseline is not None,
            "baseline_note": None if baseline else "No previous terminal run for this suite was found.",
        }

    def _available_runs(self) -> list[dict[str, Any]]:
        runs = []
        for path in self.results_dir.glob("*.json"):
            try:
                run = self._normalize(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                continue
            if isinstance(run, dict) and run.get("run_id"):
                runs.append(run)
        runs.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return runs

    @staticmethod
    def _key(question: dict[str, Any]) -> tuple[str, str, str]:
        return (str(question.get("test_id", "")), str(question.get("category", "")), str(question.get("question", "")))

    @staticmethod
    def _failed(question: dict[str, Any]) -> bool:
        return question.get("status") in {"failed", "interrupted"} or question.get("quality_status") == "failed"

    @classmethod
    def _compare_question(cls, question: dict[str, Any], old: dict[str, Any] | None) -> dict[str, Any]:
        failure = cls._diagnose(question)
        was_passing = bool(old and old.get("quality_status") == "passed" and old.get("status") == "completed")
        regressed = bool(was_passing and failure["failed"])
        old_score = old.get("score", {}).get("overall") if old else None
        score = question.get("score", {}).get("overall")
        old_time = old.get("metrics", {}).get("response_time_seconds") if old else None
        new_time = question.get("metrics", {}).get("response_time_seconds")
        old_ttft = old.get("metrics", {}).get("ttft_seconds") if old else None
        new_ttft = question.get("metrics", {}).get("ttft_seconds")
        old_tokens = old.get("metrics", {}).get("tokens_generated") if old else None
        new_tokens = question.get("metrics", {}).get("tokens_generated")
        old_tools = [str(t.get("name")) for t in old.get("tools", []) if isinstance(t, dict)] if old else None
        new_tools = [str(t.get("name")) for t in question.get("tools", []) if isinstance(t, dict)]
        return {
            "question_id": question.get("question_id"), "test_id": question.get("test_id"),
            "category": question.get("category"), "status": question.get("status"),
            "quality_status": question.get("quality_status"), "question": question.get("question"),
            "response": question.get("response", ""), "previous_response": old.get("response", "") if old else None,
            "expected": cls._expected(question), "score": score, "previous_score": old_score,
            "score_delta": round(float(score) - float(old_score), 3) if _number(score) and _number(old_score) else None,
            "runtime_seconds": new_time, "previous_runtime_seconds": old_time,
            "runtime_delta_seconds": round(float(new_time) - float(old_time), 3) if _number(new_time) and _number(old_time) else None,
            "ttft_seconds": new_ttft, "previous_ttft_seconds": old_ttft,
            "ttft_delta_seconds": round(float(new_ttft) - float(old_ttft), 3) if _number(new_ttft) and _number(old_ttft) else None,
            "tokens_generated": new_tokens, "previous_tokens_generated": old_tokens,
            "tools": question.get("tools", []), "previous_tools": old_tools,
            "tool_names": new_tools, "tool_changes": _tool_delta(old_tools, new_tools),
            "failure": failure, "regression": regressed,
            "failure_kind": cls._failure_kind(question, failure),
            "validation": cls._validation_checks(question),
            "telemetry": cls._telemetry(question),
        }

    @staticmethod
    def _expected(question: dict[str, Any]) -> dict[str, Any]:
        test = question.get("test", {})
        return {key: test[key] for key in ("expected_behavior", "expected", "expected_tool", "rubric", "social_style") if key in test}

    @classmethod
    def _diagnose(cls, question: dict[str, Any]) -> dict[str, Any]:
        response = question.get("response", "")
        events = question.get("request_events", [])
        error = question.get("error")
        signals = []
        if error:
            signals.append({"kind": "request_error", "evidence": str(error)})
            if re.search(r"\b(timeout|timed out)\b", str(error), re.I):
                signals.append({"kind": "timeout", "evidence": "The saved request error identifies a timeout."})
            elif question.get("status") == "failed":
                signals.append({"kind": "exception_or_request_failure", "evidence": "The request failed; the user-facing run record omits raw exception details."})
        failed_tools = [tool for tool in question.get("tools", []) if isinstance(tool, dict) and tool.get("status") == "failed"]
        if failed_tools:
            signals.append({"kind": "tool_error", "evidence": ", ".join(str(t.get("name", "tool")) for t in failed_tools)})
        failed_stages = [event for event in events if isinstance(event, dict) and event.get("status") == "failed"]
        if failed_stages:
            signals.append({"kind": "failed_stage", "evidence": ", ".join(str(event.get("stage", "stage")) for event in failed_stages)})
        if response and _JSON_LEAK.search(response):
            signals.append({"kind": "possible_json_leak", "evidence": "Response contains a JSON/tool-call-shaped fragment."})
        if response and _REFUSAL.search(response) and question.get("test", {}).get("expected_behavior"):
            signals.append({"kind": "possible_unexpected_refusal", "evidence": "Response contains refusal wording; compare it with the recorded expected behavior."})
        if question.get("status") == "interrupted":
            signals.append({"kind": "interrupted", "evidence": "The saved question status is interrupted."})
        if not question.get("request_events"):
            signals.append({"kind": "telemetry_missing", "evidence": "No request lifecycle events were saved for this question."})
        explanation = "Recorded failure evidence is available below." if signals else (
            "The stored rubric marks this response as failed." if question.get("quality_status") == "failed"
            else "No failure was recorded for this question."
        )
        steps = []
        if any(s["kind"] == "tool_error" for s in signals):
            steps.append("Inspect the named tool invocation and its request trace.")
        if any(s["kind"] in {"request_error", "failed_stage", "interrupted"} for s in signals):
            steps.append("Open Request Inspector for this request ID and review the failed lifecycle stage.")
        if question.get("quality_status") == "failed":
            steps.append("Compare the failed rubric checks with the benchmark case's recorded expectations.")
        if not steps:
            steps.append("Compare the recorded response with the benchmark case and inspect available request telemetry.")
        diagnostic_failure = cls._failed(question) or any(
            signal["kind"] in {"tool_error", "failed_stage", "possible_json_leak", "possible_unexpected_refusal"}
            for signal in signals
        )
        return {"failed": diagnostic_failure, "explanation": explanation, "signals": signals, "suggested_steps": steps}

    @classmethod
    def _validation_checks(cls, question: dict[str, Any]) -> dict[str, Any]:
        rubric = question.get("test", {}).get("rubric")
        if not isinstance(rubric, dict) or not question.get("response"):
            score = question.get("score", {})
            if score.get("rubric_total") is not None:
                return {"available": False, "passed": score.get("rubric_passed"), "total": score.get("rubric_total"), "failed": []}
            return {"available": False, "passed": None, "total": None, "failed": []}
        text = question["response"]
        lower = text.lower()
        checks: list[tuple[str, bool]] = []
        for phrase in rubric.get("required_phrases", []):
            checks.append((f"Required phrase: {phrase}", str(phrase).lower() in lower))
        for group in rubric.get("required_any", []):
            checks.append((f"One of these phrases: {', '.join(map(str, group))}", any(str(p).lower() in lower for p in group)))
        phrases = rubric.get("forbidden_phrases", [])
        if phrases:
            checks.append((f"Avoid forbidden phrases: {', '.join(map(str, phrases))}", all(str(p).lower() not in lower for p in phrases)))
        for pattern in rubric.get("required_regex", []):
            try:
                checks.append((f"Required pattern: {pattern}", re.search(pattern, text, re.I | re.S) is not None))
            except re.error:
                checks.append((f"Required pattern could not be evaluated: {pattern}", False))
        for pattern in rubric.get("forbidden_regex", []):
            try:
                checks.append((f"Avoid pattern: {pattern}", re.search(pattern, text, re.I | re.S) is None))
            except re.error:
                checks.append((f"Forbidden pattern could not be evaluated: {pattern}", False))
        for key, actual, op in (("max_words", len(text.split()), "at most"), ("min_words", len(text.split()), "at least"), ("max_questions", text.count("?"), "at most")):
            if key in rubric:
                limit = int(rubric[key])
                checks.append((f"{op} {limit} {('questions' if key.endswith('questions') else 'words')}", actual <= limit if key.startswith("max") else actual >= limit))
        failed = [label for label, passed in checks if not passed]
        return {"available": True, "passed": len(checks) - len(failed), "total": len(checks), "failed": failed}

    @staticmethod
    def _telemetry(question: dict[str, Any]) -> dict[str, Any]:
        metrics = question.get("metrics", {})
        return {
            "request_id": question.get("request_id"),
            "events": question.get("request_events", []),
            "response_time_seconds": metrics.get("response_time_seconds"),
            "ttft_seconds": metrics.get("ttft_seconds"),
            "tokens_generated": metrics.get("tokens_generated"),
            "tokens_per_second": metrics.get("tokens_per_second"),
            "available_metrics": [key for key, value in metrics.items() if value is not None],
            "missing_metrics": [key for key in ("ttft_seconds", "tokens_generated", "tokens_per_second") if metrics.get(key) is None],
        }

    @staticmethod
    def _failure_kind(question: dict[str, Any], failure: dict[str, Any]) -> list[str]:
        category = str(question.get("category", "")).lower()
        kinds = []
        if any(term in category for term in ("personality", "social", "style", "character", "emotional")):
            kinds.append("personality")
        elif question.get("quality_status") == "failed":
            kinds.append("benchmark_validation")
        if question.get("tools") or any(event.get("type") == "tool" for event in question.get("request_events", []) if isinstance(event, dict)):
            kinds.append("tool_routing")
        if question.get("status") in {"failed", "interrupted"} or question.get("error"):
            kinds.append("technical")
        if any(item["kind"] == "possible_json_leak" for item in failure.get("signals", [])):
            kinds.append("response_format")
        return kinds or (["benchmark_validation"] if failure["failed"] else [])

    @staticmethod
    def _feed_item(row: dict[str, Any]) -> dict[str, Any]:
        return {key: row[key] for key in ("question_id", "test_id", "category", "status", "failure_kind", "regression", "failure", "score_delta")}

    @staticmethod
    def _personality_dimensions(questions: list[dict[str, Any]]) -> dict[str, Any]:
        # Current saved scorer does not emit these trait-level measurements.
        return {name: {"available": False, "value": None} for name in (
            "playfulness", "flirtiness", "warmth", "humor",
            "conversational_naturalness", "tone_adaptation", "consistency",
        )}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tool_delta(old: list[str] | None, new: list[str]) -> dict[str, list[str]] | None:
    if old is None:
        return None
    return {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new))}
