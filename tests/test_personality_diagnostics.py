import json
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


def test_contract_has_twelve_versioned_dimensions_and_scenarios_are_multiturn():
    contract = load_contract()
    suite = json.loads(open("benchmark/suites/personality-diagnostics-v1.json", encoding="utf-8").read())

    assert contract["version"] == suite["contract_version"] == "1.0.0"
    assert len(contract["dimensions"]) == 12
    assert len({dimension["id"] for dimension in contract["dimensions"]}) == 12
    assert len(suite["scenarios"]) >= 10
    assert all(len(scenario["turns"]) >= 2 for scenario in suite["scenarios"])
    assert all(scenario["target_dimensions"] and scenario["expected_behavior"] for scenario in suite["scenarios"])


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
