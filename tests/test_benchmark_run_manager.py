import json
import threading
import time
import uuid
from pathlib import Path

import pytest

from interfaces.web.benchmark_runs import BenchmarkRunManager, _redact_trace, _run_elapsed
from interfaces.web.pipeline import PipelineEventStore


def _manager(tmp_path, dispatch):
    suites = tmp_path / "suites"
    results = tmp_path / "results"
    suites.mkdir(exist_ok=True)
    (suites / "small.json").write_text(json.dumps([
        {"test_id": "Q1", "category": "SOCIAL_STYLE", "question": "Question one"},
        {"test_id": "Q2", "category": "SOCIAL_STYLE", "question": "Question two"},
    ]), encoding="utf-8")
    return BenchmarkRunManager(suites, results, PipelineEventStore(), dispatch)


def _wait(manager, run_id, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = manager.get(run_id)
        if predicate(run):
            return run
        time.sleep(0.01)
    raise AssertionError(f"Run did not reach the expected state: {manager.get(run_id)['status']}")


def test_manual_run_persists_real_dispatch_results_and_resumes_one_question(tmp_path):
    calls = []
    def dispatch(payload):
        calls.append(payload)
        return {"response": f"Actual answer to: {payload['message']}", "response_time": 0.125}

    manager = _manager(tmp_path, dispatch)
    first = manager.start("small.json", "manual", "manual-run-request-001")
    run_id = first["run_id"]
    paused = _wait(manager, run_id, lambda run: run["status"] == "paused")

    assert paused["questions"][0]["response"] == "Actual answer to: Question one"
    assert paused["questions"][0]["status"] == "completed"
    assert paused["questions"][0]["metrics"]["response_time_seconds"] == 0.125
    assert paused["questions"][0]["metrics"]["ttft_seconds"] is None
    assert paused["questions"][0]["metrics"]["tokens_generated"] is None
    assert paused["questions"][0]["metrics"]["tokens_per_second"] is None
    assert paused["questions"][1]["status"] == "pending"

    manager.resume(run_id, next_question=True)
    finished = _wait(manager, run_id, lambda run: run["counts"]["completed"] == 2 and run["status"] == "completed")
    assert [item["message"] for item in calls] == ["Question one", "Question two"]
    assert finished["questions"][1]["response"] == "Actual answer to: Question two"
    assert manager.latest()["run_id"] == run_id


def test_idempotency_pause_and_resume_are_backend_owned(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    def dispatch(payload):
        entered.set()
        release.wait(2)
        return {"response": "real generated response", "response_time": 0.2}

    manager = _manager(tmp_path, dispatch)
    first = manager.start("small.json", "automatic", "stable-start-key-0001")
    run_id = first["run_id"]
    assert entered.wait(1)
    duplicate = manager.start("small.json", "automatic", "stable-start-key-0001")
    assert duplicate["run_id"] == run_id
    with pytest.raises(RuntimeError):
        manager.start("small.json", "automatic", "different-start-key-0002")

    paused_request = manager.pause(run_id)
    assert paused_request["status"] == "pausing"
    release.set()
    paused = _wait(manager, run_id, lambda run: run["status"] == "paused")
    assert paused["questions"][0]["response"] == "real generated response"
    assert paused["questions"][1]["status"] == "pending"
    manager.resume(run_id)
    _wait(manager, run_id, lambda run: run["status"] == "completed")


def test_server_restart_marks_running_question_interrupted_and_keeps_pending(tmp_path):
    suites = tmp_path / "suites"
    results = tmp_path / "results"
    suites.mkdir(); results.mkdir()
    run_id = str(uuid.uuid4())
    run = {
        "schema": "cynx-dx-benchmark-run-v1", "run_id": run_id,
        "status": "running", "created_at": "2026-11-11T12:00:00+00:00",
        "started_at": "2026-11-11T12:00:00+00:00", "elapsed_total_seconds": 0,
        "current_question_id": "q1", "current_request_id": "request-1",
        "questions": [
            {"question_id": "q1", "position": 1, "status": "running", "started_at": "2026-11-11T12:00:00+00:00"},
            {"question_id": "q2", "position": 2, "status": "pending"},
        ], "events": [],
    }
    (results / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")
    manager = BenchmarkRunManager(suites, results, PipelineEventStore(), lambda payload: {})

    restored = manager.latest()
    assert restored["status"] == "interrupted"
    assert restored["questions"][0]["status"] == "interrupted"
    assert restored["questions"][1]["status"] == "pending"
    assert manager.active() is None


def test_failed_question_is_not_reported_as_a_successful_run(tmp_path):
    def dispatch(payload):
        if payload["message"] == "Question one":
            raise RuntimeError("private technical details stay in logs")
        return {"response": "Actual answer to question two.", "response_time": 0.3}

    manager = _manager(tmp_path, dispatch)
    started = manager.start("small.json", "automatic", "failure-run-request-001")
    run = _wait(manager, started["run_id"], lambda value: value["status"] == "completed_with_failures")

    assert run["questions"][0]["status"] == "failed"
    assert "private technical details" not in run["questions"][0]["error"]
    assert run["questions"][1]["response"] == "Actual answer to question two."
    assert run["counts"]["failed"] == 1


def test_personality_trace_is_question_scoped_persisted_and_redacted(tmp_path):
    def dispatch(payload):
        callback = manager.trace_callback(payload["request_id"])
        callback({"stage": "instructions_assembled", "status": "completed",
                  "system_prompt": "Be helpful. api_key=secret-value",
                  "policy_classification": "not instrumented"})
        callback({"stage": "model_response_received", "status": "completed",
                  "output": "<think>private hidden thought</think>Actual response"})
        return {"response": "Actual response", "response_time": 0.01}

    manager = _manager(tmp_path, dispatch)
    started = manager.start("small.json", "automatic", "trace-run-request-0001")
    run = _wait(manager, started["run_id"], lambda value: value["status"] == "completed")

    first, second = run["questions"]
    assert first["personality_trace"]["available"] is True
    assert second["personality_trace"]["available"] is True
    assert first["personality_trace"]["events"] is not second["personality_trace"]["events"]
    for question in (first, second):
        events = question["personality_trace"]["events"]
        assert {event["stage"] for event in events} == {"instructions_assembled", "model_response_received"}
        assert all(event["run_id"] == run["run_id"] for event in events)
        assert all(event["question_id"] == question["question_id"] for event in events)
        assert all(event["request_id"] == question["request_id"] for event in events)
        prompt = events[0]["details"]["system_prompt"]
        assert "secret-value" not in prompt
        assert "[REDACTED]" in prompt
        output = events[1]["details"]["output"]
        assert "private hidden thought" not in output
        assert "HIDDEN REASONING REDACTED" in output

    historical = manager.get(run["run_id"])
    assert historical["questions"][0]["personality_trace"] == first["personality_trace"]


def test_stop_cancels_current_request_and_preserves_completed_question(tmp_path):
    suites = tmp_path / "suites"; suites.mkdir()
    results = tmp_path / "results"
    (suites / "two.json").write_text(json.dumps([
        {"test_id": "Q1", "category": "SOCIAL_STYLE", "question": "Question one"},
        {"test_id": "Q2", "category": "SOCIAL_STYLE", "question": "Question two"},
    ]), encoding="utf-8")
    events = PipelineEventStore()
    entered_second = threading.Event()

    def dispatch(payload):
        request_id = payload["request_id"]
        events.create(request_id)
        if payload["message"] == "Question two":
            entered_second.set()
            while not events.is_cancelled(request_id):
                time.sleep(0.01)
            events.publish(request_id, "request_cancelled", message="Cancelled")
            return {"cancelled": True, "response_time": 0.1}
        events.publish(request_id, "request_completed")
        return {"response": "Question one result", "response_time": 0.1}

    manager = BenchmarkRunManager(suites, results, events, dispatch)
    started = manager.start("two.json", "manual", "stop-run-request-0001")
    run_id = started["run_id"]
    _wait(manager, run_id, lambda value: value["status"] == "paused")
    manager.resume(run_id, next_question=True)
    assert entered_second.wait(1)
    manager.stop(run_id)
    stopped = _wait(manager, run_id, lambda value: value["status"] == "stopped")

    assert stopped["questions"][0]["status"] == "completed"
    assert stopped["questions"][0]["response"] == "Question one result"
    assert stopped["questions"][1]["status"] == "interrupted"


def test_versioned_multiturn_personality_scenario_is_one_persisted_benchmark_case(tmp_path):
    suites = tmp_path / "suites"
    results = tmp_path / "results"
    suites.mkdir(); results.mkdir()
    suite = {
        "schema": "cynx-personality-scenario-library-v1", "version": "1.0.0",
        "contract_version": "1.0.0", "scenarios": [{
            "scenario_id": "tone-1", "test_id": "TONE_1", "category": "tone_adaptation",
            "target_dimensions": ["tone_adaptation"], "expected_behavior": "Adapt tone.",
            "turns": ["I feel worried.", "Please explain the next step."],
        }],
    }
    (suites / "personality.json").write_text(json.dumps(suite), encoding="utf-8")
    seen = []

    def dispatch(payload):
        seen.append(payload)
        return {
            "response": "Use the next step that fits.", "response_time": 0.2,
            "conversation_turns": [
                {"turn_index": i + 1, "user_message": message, "response": f"CYN-X reply {i + 1}", "request_id": f"req-{i + 1}"}
                for i, message in enumerate(payload["turns"])
            ],
            "pipeline_events": [],
        }

    manager = BenchmarkRunManager(suites, results, PipelineEventStore(), dispatch)
    started = manager.start("personality.json", "automatic", "versioned-personality-run-001")
    finished = _wait(manager, started["run_id"], lambda run: run["status"] == "completed")
    question = finished["questions"][0]

    assert finished["personality_contract_version"] == "1.0.0"
    assert finished["scenario_library_version"] == "1.0.0"
    assert seen[0]["turns"] == suite["scenarios"][0]["turns"]
    assert question["scenario_id"] == "tone-1"
    assert [turn["user_message"] for turn in question["conversation_turns"]] == suite["scenarios"][0]["turns"]
    assert question["response"] == "Use the next step that fits."


def test_generation_metrics_are_aggregated_persisted_and_request_scoped_for_multiturn_question(tmp_path):
    suites = tmp_path / "suites"; suites.mkdir()
    results = tmp_path / "results"
    (suites / "multi.json").write_text(json.dumps([{
        "test_id": "MULTI_1", "category": "SOCIAL_STYLE", "question": "First turn?",
        "turns": ["First turn?", "Second turn?"],
    }]), encoding="utf-8")
    manager = None

    def dispatch(payload):
        first_id = payload["request_id"]
        callback = manager.trace_callback(first_id)
        callback({"stage": "first_model_output", "status": "observed", "ttft_seconds": 0.12})
        callback({"stage": "generation_response_received", "status": "completed",
                  "prompt_tokens": 20, "completion_tokens": 11, "tokens_generated": 11,
                  "total_tokens": 31, "prompt_evaluation_duration_nanoseconds": 500_000_000,
                  "generation_duration_nanoseconds": 1_000_000_000})
        second_id = str(uuid.uuid4())
        manager.register_question_request(payload["_benchmark_run_id"], payload["_benchmark_question_id"], second_id)
        manager.trace_callback(second_id)({"stage": "generation_response_received", "status": "completed",
                                           "prompt_tokens": 30, "completion_tokens": 19, "tokens_generated": 19,
                                           "total_tokens": 49, "prompt_evaluation_duration_nanoseconds": 500_000_000,
                                           "generation_duration_nanoseconds": 2_000_000_000})
        return {
            "response": "Second response.", "response_time": 3.0, "terminal_request_id": second_id,
            "tools": [],
            "conversation_turns": [
                {"turn_index": 1, "request_id": first_id,
                 "metrics": {"response_time_seconds": 1.25, "ttft_seconds": 0.12,
                             "prompt_tokens": 20, "completion_tokens": 11,
                             "total_tokens": 31, "generation_duration_seconds": 1.0,
                             "tokens_per_second": 11.0}},
                {"turn_index": 2, "request_id": second_id,
                 "metrics": {"response_time_seconds": 1.75, "ttft_seconds": None,
                             "prompt_tokens": 30, "completion_tokens": 19,
                             "total_tokens": 49, "generation_duration_seconds": 2.0,
                             "tokens_per_second": 9.5}},
            ],
            "pipeline_events": [
                {"type": "stage", "stage": "generating_response", "status": "completed", "request_id": first_id, "turn_index": 1},
                {"type": "stage", "stage": "generating_response", "status": "completed", "request_id": second_id, "turn_index": 2},
            ],
        }

    manager = BenchmarkRunManager(suites, results, PipelineEventStore(), dispatch)
    started = manager.start("multi.json", "automatic", "multi-metrics-run-0001")
    finished = _wait(manager, started["run_id"], lambda run: run["status"] == "completed")
    question = finished["questions"][0]
    saved = json.loads((results / f"{started['run_id']}.json").read_text(encoding="utf-8"))["questions"][0]

    assert question["metrics"] == {
        "response_time_seconds": 3.0, "ttft_seconds": 0.12,
        "prompt_tokens": 50, "completion_tokens": 30, "tokens_generated": 30,
        "total_tokens": 80, "prompt_evaluation_duration_seconds": 1.0,
        "generation_duration_seconds": 3.0, "tokens_per_second": 10.0,
    }
    assert [turn["metrics"]["completion_tokens"] for turn in question["conversation_turns"]] == [11, 19]
    assert finished["metrics_summary"]["prompt_tokens"] == {
        "total": 50, "measured_questions": 1, "eligible_questions": 1,
    }
    assert finished["metrics_summary"]["completion_tokens"]["total"] == 30
    assert finished["metrics_summary"]["tokens_per_second"]["value"] == 10.0
    assert question["terminal_request_id"] == question["request_ids"][1]
    assert [(event["request_id"], event["turn_index"]) for event in question["request_events"]] == [
        (question["request_ids"][0], 1), (question["request_ids"][1], 2),
    ]
    assert question["tool_telemetry_available"] is True
    assert saved["metrics"] == question["metrics"]


def test_historical_trace_metrics_are_exposed_without_rewriting_saved_snapshot(tmp_path):
    suites = tmp_path / "suites"; suites.mkdir()
    results = tmp_path / "results"; results.mkdir()
    run_id = str(uuid.uuid4())
    saved_run = {
        "schema": "cynx-dx-benchmark-run-v1", "run_id": run_id,
        "created_at": "2026-11-11T12:00:00+00:00", "suite": "multi.json",
        "status": "completed", "questions": [{
            "question_id": "q1", "position": 1, "test_id": "MULTI_1",
            "category": "SOCIAL_STYLE", "question": "Question?", "response": "Answer.",
            "status": "completed", "request_id": "turn-1", "request_ids": ["turn-1", "turn-2"],
            "metrics": {"response_time_seconds": 2.0, "ttft_seconds": None,
                        "tokens_generated": None, "tokens_per_second": None},
            "personality_trace": {"events": [
                {"stage": "first_model_output", "details": {"ttft_seconds": 0.2}},
                {"stage": "generation_response_received", "request_id": "turn-1",
                 "details": {"tokens_generated": 4, "generation_duration_nanoseconds": 1_000_000_000}},
                {"stage": "generation_response_received", "request_id": "turn-2",
                 "details": {"tokens_generated": 6, "generation_duration_nanoseconds": 2_000_000_000}},
            ]},
        }], "events": [],
    }
    snapshot = results / f"{run_id}.json"
    snapshot.write_text(json.dumps(saved_run), encoding="utf-8")
    manager = BenchmarkRunManager(suites, results, PipelineEventStore(), lambda payload: {})

    historical = manager.get(run_id)
    assert historical["questions"][0]["metrics"] == {
        "response_time_seconds": 2.0, "ttft_seconds": 0.2,
        "prompt_tokens": None, "completion_tokens": 10, "tokens_generated": 10,
        "total_tokens": None, "prompt_evaluation_duration_seconds": None,
        "generation_duration_seconds": 3.0, "tokens_per_second": 10 / 3,
    }
    # Reading an older snapshot must not rewrite its original representation.
    assert json.loads(snapshot.read_text(encoding="utf-8"))["questions"][0]["metrics"]["tokens_generated"] is None


def test_tool_invocations_with_reused_ids_remain_scoped_to_their_request():
    events = [
        {"type": "tool", "name": "web_search", "invocation_id": "web_search", "request_id": "turn-1", "status": "started", "elapsed_seconds": 0.1},
        {"type": "tool", "name": "web_search", "invocation_id": "web_search", "request_id": "turn-1", "status": "completed", "elapsed_seconds": 0.4},
        {"type": "tool", "name": "web_search", "invocation_id": "web_search", "request_id": "turn-2", "status": "started", "elapsed_seconds": 0.2},
        {"type": "tool", "name": "web_search", "invocation_id": "web_search", "request_id": "turn-2", "status": "failed", "elapsed_seconds": 0.7},
    ]

    calls = BenchmarkRunManager._tool_summary(events)

    assert len(calls) == 2
    assert [(call["request_id"], call["status"], call["duration_seconds"]) for call in calls] == [
        ("turn-1", "completed", 0.3), ("turn-2", "failed", 0.5),
    ]


def test_elapsed_time_uses_accumulated_execution_time_and_excludes_pauses():
    assert _run_elapsed({"elapsed_total_seconds": 12.5, "started_at": None, "status": "paused"}) == 12.5
    assert _run_elapsed({"elapsed_total_seconds": 0, "created_at": "2026-11-12T00:00:00+00:00", "status": "completed"}) == 0


def test_legacy_saved_run_can_be_opened_read_only_with_missing_metrics_unavailable(tmp_path):
    suites = tmp_path / "suites"; suites.mkdir()
    results = tmp_path / "results"; results.mkdir()
    run_id = str(uuid.uuid4())
    (results / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "created_at": "2026-11-10T12:00:00+00:00", "suite": "old.json",
        "attempted": 1, "successful": 1, "failed": 0, "average_score": None,
        "average_response_time": None,
        "results": [{"test_id": "OLD_1", "question": "Question?", "response": "Saved answer.",
                     "response_time": None, "failed": False, "scores": None}],
    }), encoding="utf-8")
    manager = BenchmarkRunManager(suites, results, PipelineEventStore(), lambda payload: {})

    restored = manager.get(run_id)
    assert restored["legacy_record"] is True
    assert restored["questions"][0]["response"] == "Saved answer."
    assert restored["questions"][0]["metrics"]["response_time_seconds"] is None
    assert restored["questions"][0]["quality_status"] == "unscored"


def test_invalid_suite_record_is_rejected_instead_of_silently_reducing_total(tmp_path):
    suites = tmp_path / "suites"; suites.mkdir()
    results = tmp_path / "results"
    (suites / "invalid.json").write_text(json.dumps([
        {"test_id": "VALID", "category": "SOCIAL_STYLE", "question": "A real question?"},
        {"test_id": "EMPTY", "category": "SOCIAL_STYLE", "question": "   "},
    ]), encoding="utf-8")
    manager = BenchmarkRunManager(suites, results, PipelineEventStore(), lambda payload: {})

    with pytest.raises(ValueError, match="invalid question at position 2"):
        manager.start("invalid.json", "automatic", "invalid-suite-request-001")


def test_tool_trace_data_is_pii_redacted_before_persistence():
    safe = _redact_trace({"result_output": {"result": "Saved result for piper@example.org; phone 313-555-0199"},
                          "api_key": "secret-value"})
    serialized = json.dumps(safe)
    assert "piper@example.org" not in serialized
    assert "313-555-0199" not in serialized
    assert safe["api_key"] == "[REDACTED]"
    assert "Saved result" in serialized
    long_text = _redact_trace("x" * 50005)
    assert "TRACE TEXT OMITTED: 5 characters" in long_text


def test_multiturn_trace_events_retain_their_turn_number(tmp_path):
    manager = None
    def dispatch(payload):
        request_id = payload["request_id"]
        manager.register_question_request(payload["_benchmark_run_id"], payload["_benchmark_question_id"], request_id, 2)
        manager.trace_callback(request_id)({"stage": "tool_execution", "status": "completed", "tool_name": "fixture",
                                            "result_output": "Result for piper@example.org"})
        return {"response": "Completed turn", "response_time": 0.1}

    suites = tmp_path / "suites"; suites.mkdir()
    results = tmp_path / "results"
    (suites / "scenario.json").write_text(json.dumps([{
        "test_id": "SCENARIO", "category": "PERSONALITY", "question": "First?",
        "turns": ["First?", "Second?"],
    }]), encoding="utf-8")
    manager = BenchmarkRunManager(suites, results, PipelineEventStore(), dispatch)
    started = manager.start("scenario.json", "automatic", "turn-trace-start-001")
    finished = _wait(manager, started["run_id"], lambda run: run["status"] == "completed")

    trace = finished["questions"][0]["personality_trace"]["events"]
    item = next(event for event in trace if event["stage"] == "tool_execution")
    assert item["turn_index"] == 2
    assert "piper@example.org" not in json.dumps(item)
    assert "[EMAIL REDACTED]" in json.dumps(item)
