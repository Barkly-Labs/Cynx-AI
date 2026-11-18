import json

from benchmark.watchdog import BenchmarkWatchdog


def _run(run_id, *, created_at, response, quality, tool_status="completed", status="completed"):
    return {
        "schema": "cynx-dx-benchmark-run-v1",
        "run_id": run_id,
        "suite": "style.json",
        "created_at": created_at,
        "status": status,
        "questions": [{
            "question_id": f"q-{run_id}",
            "test_id": "STYLE_01",
            "category": "PERSONALITY_STYLE",
            "question": "Respond warmly in one sentence.",
            "test": {
                "expected_behavior": "A warm, concise answer.",
                "rubric": {"required_phrases": ["glad to help"], "max_words": 10},
            },
            "status": status if status in {"failed", "interrupted"} else "completed",
            "quality_status": quality,
            "response": response,
            "score": {"overall": 2.0 if quality == "passed" else 0.5, "rubric_passed": 2 if quality == "passed" else 0, "rubric_total": 2},
            "error": "Model request timed out" if status == "failed" else None,
            "request_id": f"request-{run_id}",
            "request_events": [{"type": "stage", "stage": "generating_response", "status": "completed"}],
            "tools": [{"name": "web_search", "status": tool_status}] if tool_status != "none" else [],
            "metrics": {"response_time_seconds": 1.5 if run_id == "new" else 1.0, "ttft_seconds": None, "tokens_generated": None, "tokens_per_second": None},
        }],
    }


def test_watchdog_compares_saved_run_and_explains_failed_rubric(tmp_path):
    (tmp_path / "old.json").write_text(json.dumps(_run("old", created_at="2026-01-01", response="Glad to help you today.", quality="passed", tool_status="none")))
    (tmp_path / "new.json").write_text(json.dumps(_run("new", created_at="2026-01-02", response="Here is a very long response without the required wording and far too many words today.", quality="failed")))

    report = BenchmarkWatchdog(tmp_path).report("new")

    assert report["baseline_run_id"] == "old"
    assert report["counts"]["regressions"] == 1
    item = report["questions"][0]
    assert item["previous_response"] == "Glad to help you today."
    assert item["score_delta"] == -1.5
    assert item["regression"] is True
    assert item["validation"]["failed"] == ["Required phrase: glad to help", "at most 10 words"]
    assert item["telemetry"]["missing_metrics"] == [
        "prompt_tokens", "completion_tokens", "total_tokens", "ttft_seconds",
        "generation_duration_seconds", "tokens_per_second",
    ]
    assert report["personality_dimensions"]["playfulness"]["available"] is False
    assert report["personality_dimensions"]["playfulness"]["value"] is None


def test_watchdog_surfaces_partial_tool_failure_without_claiming_model_failure(tmp_path):
    (tmp_path / "old.json").write_text(json.dumps(_run("old", created_at="2026-01-01", response="Glad to help.", quality="passed", tool_status="none")))
    (tmp_path / "new.json").write_text(json.dumps(_run("new", created_at="2026-01-02", response="Glad to help.", quality="passed", tool_status="failed")))

    report = BenchmarkWatchdog(tmp_path).report("new", "old")

    assert report["counts"]["failed"] == 0
    assert report["health"] == "needs_attention"
    assert report["regression_feed"][0]["failure_kind"] == ["personality", "tool_routing"]
    assert report["questions"][0]["failure"]["signals"][0]["kind"] == "tool_error"


def test_watchdog_handles_unknown_run_and_does_not_invent_baseline(tmp_path):
    report = BenchmarkWatchdog(tmp_path).report("missing")
    assert report is None


def test_watchdog_uses_terminal_turn_request_and_keeps_unknown_tool_delta_unavailable(tmp_path):
    run = _run("terminal", created_at="2026-01-03", response="A saved answer.", quality="failed")
    question = run["questions"][0]
    question["request_id"] = "initial-request"
    question["terminal_request_id"] = "failing-final-turn"
    question["tool_telemetry_available"] = False
    question["tools"] = []
    (tmp_path / "terminal.json").write_text(json.dumps(run))

    report = BenchmarkWatchdog(tmp_path).report("terminal")

    assert report["questions"][0]["telemetry"]["request_id"] == "failing-final-turn"
    assert report["questions"][0]["tool_names"] is None
    assert report["questions"][0]["tool_changes"] is None


def test_watchdog_uses_saved_personality_diagnostic_scores_for_matching_run(tmp_path):
    run = _run("scored", created_at="2026-01-03", response="A measured response.", quality="passed")
    (tmp_path / "scored.json").write_text(json.dumps(run))
    diag_dir = tmp_path / "personality_diagnostics"
    diag_dir.mkdir()
    (diag_dir / "scored.json").write_text(json.dumps({
        "run_id": "scored",
        "diagnostics": [
            {"evaluator_version": "cynx-local-judge-v1", "dimension": "warmth", "score": 3.0, "status": "pass"},
            {"evaluator_version": "cynx-local-judge-v1", "dimension": "warmth", "score": 2.0, "status": "warning"},
            {"evaluator_version": "cynx-local-judge-v1", "dimension": "playfulness", "score": 0.0, "status": "fail"},
            {"evaluator_version": "deterministic-scan-v1", "dimension": "humor", "score": 4.0, "status": "pass"},
            {"evaluator_version": "cynx-local-judge-v1", "dimension": "tone_adaptation", "score": None, "status": "inconclusive"},
        ],
    }))

    report = BenchmarkWatchdog(tmp_path).report("scored")

    assert report["personality_dimensions"]["warmth"] == {
        "available": True, "value": 2.5, "sample_count": 2,
        "source": "saved_personality_diagnostics",
    }
    assert "saved on this run" in report["personality_dimensions"]["flirtiness"]["reason"] or "Contract" in report["personality_dimensions"]["flirtiness"]["reason"]
    assert report["personality_dimensions"]["playfulness"]["value"] == 0.0
    assert report["personality_dimensions"]["humor"]["available"] is False
    assert report["personality_dimensions"]["tone_adaptation"]["available"] is False
    assert report["personality_dimensions"]["flirtiness"]["available"] is False


def test_watchdog_exposes_full_turns_configuration_and_all_runtime_metric_comparisons(tmp_path):
    old = _run("old", created_at="2026-01-01", response="Old answer", quality="passed", tool_status="none")
    new = _run("new", created_at="2026-01-02", response="New answer", quality="passed", tool_status="none")
    old_question, new_question = old["questions"][0], new["questions"][0]
    old_question["conversation_turns"] = [{"turn_index": 1, "user_message": "Prompt one", "response": "Old answer", "metrics": {"prompt_tokens": 4}}]
    new_question["conversation_turns"] = [
        {"turn_index": 1, "user_message": "Prompt one", "response": "New answer", "metrics": {"prompt_tokens": 6}},
        {"turn_index": 2, "user_message": "Follow up", "response": "Second answer", "metrics": {"completion_tokens": 3}},
    ]
    old_question["metrics"] = {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6,
                                "tokens_per_second": 2, "generation_duration_seconds": 1,
                                "ttft_seconds": .2, "response_time_seconds": 1}
    new_question["metrics"] = {"prompt_tokens": 6, "completion_tokens": 3, "total_tokens": 9,
                                "tokens_per_second": 3, "generation_duration_seconds": 1,
                                "ttft_seconds": .1, "response_time_seconds": 2}
    new_question["personality_trace"] = {"events": [{"stage": "configuration_loaded", "details": {
        "model": "cynx-local:latest", "preset": "warm", "architecture": "v2",
        "prompt_layers": ["core", "personality"], "generation_parameters": "not exposed",
    }}]}
    (tmp_path / "old.json").write_text(json.dumps(old))
    (tmp_path / "new.json").write_text(json.dumps(new))

    report = BenchmarkWatchdog(tmp_path).report("new")

    row = report["questions"][0]
    assert [turn["user_message"] for turn in row["conversation_turns"]] == ["Prompt one", "Follow up"]
    assert row["personality_trace"]["events"][0]["details"]["preset"] == "warm"
    assert report["metadata"]["model_identifiers"] == ["cynx-local:latest"]
    assert report["metadata"]["personality_presets"] == ["warm"]
    assert report["run_comparison"]["matched_questions"] == 1
    assert report["run_comparison"]["metrics"]["prompt_tokens"]["delta"] == 2
    assert report["run_comparison"]["metrics"]["ttft_seconds"]["delta"] == -.1
    assert report["metrics_summary"]["completion_tokens"]["total"] == 3
    assert report["snapshot_source"] == "saved_benchmark_run"


def test_watchdog_recovers_legacy_response_time_when_saved_metric_is_null(tmp_path):
    run = _run("legacy", created_at="2026-01-02", response="Saved", quality="passed")
    run["questions"][0]["metrics"]["response_time_seconds"] = None
    run["questions"][0]["response_time"] = 2.75
    (tmp_path / "legacy.json").write_text(json.dumps(run))

    report = BenchmarkWatchdog(tmp_path).report("legacy")

    assert report["questions"][0]["metrics"]["response_time_seconds"] == 2.75
    assert report["questions"][0]["telemetry"]["response_time_seconds"] == 2.75
