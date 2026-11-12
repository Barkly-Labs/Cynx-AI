import json
import threading
import time
import uuid

from benchmark.personality.diagnostics import PersonalityDiagnosticsService, load_contract


class _Judge:
    model = "local-judge-test"

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def chat(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": messages, "tools": tools, "kwargs": kwargs})
        return {"message": {"content": json.dumps(self.answer)}}


def _saved_run(run_id, *, created, response, score, confidence=0.9):
    return {
        "schema": "cynx-dx-benchmark-run-v1", "run_id": run_id,
        "suite": "personality-diagnostics-v1.json", "status": "completed", "created_at": created,
        "personality_contract_version": "1.0.0", "scenario_library_version": "1.0.0",
        "questions": [{
            "question_id": f"question-{run_id}", "test_id": "tone-transition-01",
            "scenario_id": "tone-transition-01", "scenario_category": "tone_adaptation",
            "target_dimensions": ["tone_adaptation"], "expected_behavior": "Adapt tone to the user's emotional context.",
            "failure_conditions": [], "question": "I feel worried.",
            "test": {"rubric": {}}, "status": "completed", "quality_status": "scored",
            "request_id": f"request-{run_id}", "request_ids": [f"request-{run_id}"],
            "response": response,
            "conversation_turns": [{"turn_index": 1, "user_message": "I feel worried.", "response": response, "request_id": f"request-{run_id}"}],
            "request_events": [], "tools": [],
            "metrics": {"response_time_seconds": 0.7, "ttft_seconds": None, "tokens_generated": None, "tokens_per_second": None},
        }],
    }


def test_contract_has_thirteen_versioned_dimensions_and_scenarios_are_multiturn():
    contract = load_contract()
    suite = json.loads(open("benchmark/suites/personality-diagnostics-v1.json", encoding="utf-8").read())

    assert contract["version"] == suite["contract_version"] == "1.0.0"
    assert suite["version"] == "1.1.0"
    assert len(contract["dimensions"]) == 13
    assert len({dimension["id"] for dimension in contract["dimensions"]}) == 13
    assert len(suite["scenarios"]) >= 10
    assert all(len(scenario["turns"]) >= 2 for scenario in suite["scenarios"])
    assert all(scenario["target_dimensions"] and scenario["expected_behavior"] for scenario in suite["scenarios"])
    assert {dimension for scenario in suite["scenarios"] for dimension in scenario["target_dimensions"]} == {
        dimension["id"] for dimension in contract["dimensions"]
    }


def test_diagnostics_uses_trace_backed_aggregate_metrics_for_older_snapshots(tmp_path):
    run_id = str(uuid.uuid4())
    run = _saved_run(run_id, created="2026-11-01", response="A calm reply.", score=3.0)
    question = run["questions"][0]
    question["request_events"] = [{"type": "stage", "stage": "generating_response"}]
    question["personality_trace"] = {"events": [
        {"stage": "first_model_output", "details": {"ttft_seconds": 0.25}},
        {"stage": "generation_response_received", "details": {
            "tokens_generated": 12, "generation_duration_nanoseconds": 2_000_000_000,
        }},
    ]}
    service = PersonalityDiagnosticsService(tmp_path)

    findings = service._deterministic_findings(run, question)
    telemetry = next((item for item in findings if item[2] == "missing_telemetry"), None)

    assert telemetry is None


def test_local_evaluator_is_toolless_validates_quotes_and_redacts_pii(tmp_path):
    run_id = str(uuid.uuid4())
    run = _saved_run(run_id, created="2026-11-01", response="I can stay with the practical part and help you check it.", score=3.5)
    run["questions"][0]["conversation_turns"][0]["user_message"] = "Contact me at piper@example.org. I feel worried."
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")
    judge = _Judge({"evaluations": [{
        "dimension": "tone_adaptation", "score": 3.5, "confidence": 0.88,
        "observed_behavior": "The response is calm and practical.",
        "expected_behavior": "Adapt tone to the user's emotional context.",
        "explanation": "The wording stays measured.", "potential_contributing_factors": [],
        "recommendations": ["Keep the tone proportional."],
        "evidence": [{"turn_index": 1, "quote": "I can stay with the practical part"}],
    }]})
    service = PersonalityDiagnosticsService(tmp_path, judge)

    report = service.evaluate_run(run_id)
    evaluation = next(item for item in report["diagnostics"] if item["dimension"] == "tone_adaptation")

    assert judge.calls[0]["tools"] is None
    prompt = judge.calls[0]["messages"][1]["content"]
    assert "piper@example.org" not in prompt
    assert evaluation["status"] == "pass"
    assert evaluation["score"] == 3.5
    assert evaluation["evidence_references"][0]["request_id"] == f"request-{run_id}"
    assert report["calibration_status"] == "uncalibrated"
    assert json.loads((tmp_path / "personality_diagnostics" / f"{run_id}.json").read_text())["run_id"] == run_id


def test_evidence_quote_must_match_the_referenced_turn_and_runtime_model_is_saved(tmp_path):
    run_id = str(uuid.uuid4())
    run = _saved_run(run_id, created="2026-11-01", response="Answer from turn two.", score=3.2)
    question = run["questions"][0]
    question["conversation_turns"] = [
        {"turn_index": 1, "user_message": "First question.", "response": "First answer.", "request_id": "req-1"},
        {"turn_index": 2, "user_message": "Second question.", "response": "Answer from turn two.", "request_id": "req-2"},
    ]
    question["personality_trace"] = {"events": [{"request_id": "req-2", "details": {"model": "cynx-local:latest"}}]}
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")
    judge = _Judge({"evaluations": [{
        "dimension": "tone_adaptation", "score": 3.2, "confidence": 0.9,
        "observed_behavior": "The tone is direct.", "explanation": "The answer is concise.",
        "evidence": [{"turn_index": 1, "quote": "Answer from turn two."}],
    }]})

    report = PersonalityDiagnosticsService(tmp_path, judge).evaluate_run(run_id)
    item = next(item for item in report["diagnostics"] if item["dimension"] == "tone_adaptation")

    assert item["status"] == "inconclusive"
    assert item["score"] is None
    assert report["runtime_provenance"]["model_identifiers"] == ["cynx-local:latest"]


def test_failed_scenario_keeps_technical_failure_and_no_personality_score(tmp_path):
    run_id = str(uuid.uuid4())
    run = _saved_run(run_id, created="2026-11-01", response="", score=0)
    question = run["questions"][0]
    question["status"] = "failed"
    question["error"] = "A scenario turn failed."
    question["response"] = ""
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")
    service = PersonalityDiagnosticsService(tmp_path, _Judge({"evaluations": []}))

    report = service.evaluate_run(run_id)

    assert all(item["score"] is None for item in report["diagnostics"] if item["finding_class"] == "personality")
    assert any(item["finding_class"] == "technical" and item["finding_code"] == "request_failed" for item in report["diagnostics"])


def test_concurrent_evaluate_requests_are_coalesced(tmp_path):
    run_id = str(uuid.uuid4())
    run = _saved_run(run_id, created="2026-11-01", response="A calm answer.", score=3)
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")
    entered, release, second_started = threading.Event(), threading.Event(), threading.Event()

    class SlowJudge(_Judge):
        def chat(self, messages, tools=None, **kwargs):
            self.calls.append({"messages": messages, "tools": tools, "kwargs": kwargs})
            entered.set()
            assert release.wait(2)
            return {"message": {"content": json.dumps({"evaluations": [{
                "dimension": "tone_adaptation", "score": 3, "confidence": 0.8,
                "observed_behavior": "Measured tone.", "explanation": "Evidence-backed.",
                "evidence": [{"turn_index": 1, "quote": "A calm answer."}],
            }]})}}

    judge = SlowJudge(None)
    service = PersonalityDiagnosticsService(tmp_path, judge)
    first = threading.Thread(target=service.evaluate_run, args=(run_id,), kwargs={"refresh": True})
    second = threading.Thread(target=lambda: (second_started.set(), service.evaluate_run(run_id, refresh=True)))
    first.start()
    assert entered.wait(2)
    second.start()
    assert second_started.wait(2)
    time.sleep(0.05)
    release.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert len(judge.calls) == 1


def test_reviewed_baseline_requires_two_passing_scenarios(tmp_path):
    import copy

    run_id = str(uuid.uuid4())
    run = _saved_run(run_id, created="2026-11-01", response="A measured answer.", score=3.5)
    first = run["questions"][0]
    first["response"] = "A measured answer."
    first["conversation_turns"][0]["response"] = "A measured answer."
    second = copy.deepcopy(first)
    second.update({"question_id": "question-second", "test_id": "scenario-two", "scenario_id": "scenario-two", "request_id": "request-second", "request_ids": ["request-second"]})
    second["conversation_turns"][0]["request_id"] = "request-second"
    run["questions"].append(second)
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")
    judge = _Judge({"evaluations": [{
        "dimension": "tone_adaptation", "score": 3.5, "confidence": 0.9,
        "observed_behavior": "Measured and calm.", "explanation": "The wording is proportional.",
        "evidence": [{"turn_index": 1, "quote": "A measured answer."}],
    }]})
    service = PersonalityDiagnosticsService(tmp_path, judge)

    service.evaluate_run(run_id)
    approved = service.mark_reviewed_baseline(run_id)

    assert approved["baseline_review"]["status"] == "approved"
    assert approved["calibration_status"] == "uncalibrated"
    assert service._is_known_good(approved) is True


def test_missing_evaluator_is_inconclusive_not_zero_and_history_keeps_nulls(tmp_path):
    run_id = str(uuid.uuid4())
    run = _saved_run(run_id, created="2026-11-01", response="Some answer.", score=0)
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")
    service = PersonalityDiagnosticsService(tmp_path, ollama_client=None)

    report = service.evaluate_run(run_id)
    history = service.history(run_id=run_id)
    evaluation = next(item for item in report["diagnostics"] if item["dimension"] == "tone_adaptation")

    assert evaluation["status"] == "inconclusive"
    assert evaluation["score"] is None
    assert history["trend"][0]["dimensions"]["tone_adaptation"] is None
    assert history["trend"][0]["dimensions"]["warmth"] is None


def test_history_exposes_target_coverage_for_unscored_and_legacy_runs(tmp_path):
    run_id = str(uuid.uuid4())
    untagged = _saved_run(run_id, created="2026-11-01", response="A saved response.", score=2)
    untagged["questions"][0].pop("target_dimensions")
    (tmp_path / f"{run_id}.json").write_text(json.dumps(untagged), encoding="utf-8")
    legacy_id = str(uuid.uuid4())
    legacy = {"run_id": legacy_id, "suite": "cyn-persoanlility-tests.json", "status": "completed",
              "results": [{"status": "completed", "test": {"target_dimensions": ["warmth", "playfulness"]}},
                          {"status": "failed", "test": {"target_dimensions": ["warmth"]}}]}
    (tmp_path / f"{legacy_id}.json").write_text(json.dumps(legacy), encoding="utf-8")
    service = PersonalityDiagnosticsService(tmp_path, ollama_client=None)

    no_targets = service.history(run_id=run_id)
    legacy_history = service.history(run_id=legacy_id)

    assert no_targets["run_context"]["targeted_scenarios"] == 0
    assert no_targets["run_context"]["dimension_targets"] == {}
    assert legacy_history["run_context"]["targeted_scenarios"] == 2
    assert legacy_history["run_context"]["completed_targeted_scenarios"] == 1
    assert legacy_history["run_context"]["dimension_targets"] == {"warmth": 2, "playfulness": 1}


def test_personality_history_trend_is_limited_to_same_suite_and_reports_dimension_coverage(tmp_path):
    run_id = str(uuid.uuid4())
    run = _saved_run(run_id, created="2026-11-01", response="A calm reply.", score=3)
    run["questions"][0]["target_dimensions"] = ["tone_adaptation", "made_up_dimension"]
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")
    record_dir = tmp_path / "personality_diagnostics"
    record_dir.mkdir()
    current_report = {
        "schema": "cynx-personality-diagnostics-v1", "run_id": run_id,
        "suite": "personality-diagnostics-v1.json", "created_at": "2026-11-01",
        "personality_contract_version": "1.0.0", "evaluator_version": "judge-v1",
        "evaluation_coverage": {"eligible_scenarios": 1, "evaluated_scenarios": 1,
                                "dimension_evaluations": 1, "inconclusive_evaluations": 0},
        "diagnostics": [{"evaluator_version": "cynx-local-judge-v1", "finding_class": "personality",
                         "dimension": "tone_adaptation", "score": 3, "confidence": .9,
                         "status": "pass", "scenario_id": "scenario-1", "scenario_category": "tone"}],
    }
    unrelated_id = str(uuid.uuid4())
    unrelated = {**current_report, "run_id": unrelated_id, "suite": "technical-suite.json",
                 "created_at": "2026-11-02", "diagnostics": [{**current_report["diagnostics"][0], "score": 0}]}
    (record_dir / f"{run_id}.json").write_text(json.dumps(current_report), encoding="utf-8")
    (record_dir / f"{unrelated_id}.json").write_text(json.dumps(unrelated), encoding="utf-8")

    history = PersonalityDiagnosticsService(tmp_path).history(run_id=run_id)

    assert [point["run_id"] for point in history["trend"]] == [run_id]
    assert history["trend"][0]["dimensions"]["tone_adaptation"] == 3
    assert history["trend"][0]["dimension_coverage"]["tone_adaptation"]["scored_samples"] == 1
    assert history["run_context"]["targeted_scenarios"] == 1
    assert history["run_context"]["dimension_targets"] == {"tone_adaptation": 1}


def test_deterministic_findings_use_actual_tool_and_response_evidence(tmp_path):
    service = PersonalityDiagnosticsService(tmp_path)
    run_id = str(uuid.uuid4())
    run = {"run_id": run_id, "personality_contract_version": "1.0.0"}
    question = {
        "question_id": "q", "test_id": "tool-context-01", "scenario_id": "tool-context-01",
        "status": "completed", "question": "Calculate 2 plus 2.",
        "expected_behavior": "Answer without tools.",
        "test": {"turn_expectations": [{"expected_tools": []}]},
        "response": '{"tool_calls": []}',
        "conversation_turns": [{"turn_index": 1, "user_message": "Calculate 2 plus 2.", "response": '{"tool_calls": []}', "request_id": "req", "tools": ["web_search"], "expected_tools": []}],
        "request_events": [], "tools": [{"name": "web_search", "status": "completed"}],
    }

    findings = service._deterministic_findings(run, question)
    codes = {item["finding_code"] for item in findings}

    assert "possible_json_leak" in codes
    assert "unexpected_tool" in codes
    assert all(item["evidence_references"][0]["request_id"] == "req" for item in findings)


def test_regression_is_candidate_when_only_one_uncalibrated_sample_exists(tmp_path):
    service = PersonalityDiagnosticsService(tmp_path)
    baseline_id, current_id = str(uuid.uuid4()), str(uuid.uuid4())
    for run_id, created, score, status in ((baseline_id, "2026-11-01", 3.8, "pass"), (current_id, "2026-11-02", 2.0, "warning")):
        report = {
            "schema": "cynx-personality-diagnostics-v1", "run_id": run_id,
            "suite": "personality-diagnostics-v1.json", "created_at": created,
            "calibration_status": "uncalibrated", "evaluation_coverage": {"eligible_scenarios": 1, "evaluated_scenarios": 1},
            "diagnostics": [{"evaluator_version": "cynx-local-judge-v1", "dimension": "tone_adaptation",
                             "score": score, "confidence": 0.95, "status": status,
                             "severity": "high", "scenario_category": "tone_adaptation"}],
        }
        path = tmp_path / "personality_diagnostics" / f"{run_id}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        run = _saved_run(run_id, created=created, response="A response.", score=score)
        (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")

    history = service.history(run_id=current_id)

    assert history["comparisons"]["previous"] == baseline_id
    assert history["comparisons"]["regressions"][0]["status"] == "candidate_unconfirmed"
    assert history["comparisons"]["regressions"][0]["delta"] < -0.75
    assert history["comparisons"]["last_known_good"] is None
    assert len(history["comparisons"]["regressions"]) == 1
