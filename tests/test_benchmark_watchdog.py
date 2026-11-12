import json

from benchmark.watchdog import BenchmarkWatchdog


def _run(
    run_id,
    *,
    created_at,
    response,
    quality,
    tool_status="completed",
    status="completed",
):
    return {
        "schema": "cynx-dx-benchmark-run-v1",
        "run_id": run_id,
        "suite": "style.json",
        "created_at": created_at,
        "status": status,
        "questions": [
            {
                "question_id": f"q-{run_id}",
                "test_id": "STYLE_01",
                "category": "PERSONALITY_STYLE",
                "question": "Respond warmly in one sentence.",
                "test": {
                    "expected_behavior": "A warm, concise answer.",
                    "rubric": {"required_phrases": ["glad to help"], "max_words": 10},
                },
                "status": (
                    status if status in {"failed", "interrupted"} else "completed"
                ),
                "quality_status": quality,
                "response": response,
                "score": {
                    "overall": 2.0 if quality == "passed" else 0.5,
                    "rubric_passed": 2 if quality == "passed" else 0,
                    "rubric_total": 2,
                },
                "error": "Model request timed out" if status == "failed" else None,
                "request_id": f"request-{run_id}",
                "request_events": [
                    {
                        "type": "stage",
                        "stage": "generating_response",
                        "status": "completed",
                    }
                ],
                "tools": (
                    [{"name": "web_search", "status": tool_status}]
                    if tool_status != "none"
                    else []
                ),
                "metrics": {
                    "response_time_seconds": 1.5 if run_id == "new" else 1.0,
                    "ttft_seconds": None,
                    "tokens_generated": None,
                    "tokens_per_second": None,
                },
            }
        ],
    }


def test_watchdog_compares_saved_run_and_explains_failed_rubric(tmp_path):
    (tmp_path / "old.json").write_text(
        json.dumps(
            _run(
                "old",
                created_at="2026-01-01",
                response="Glad to help you today.",
                quality="passed",
                tool_status="none",
            )
        )
    )
    (tmp_path / "new.json").write_text(
        json.dumps(
            _run(
                "new",
                created_at="2026-01-02",
                response="Here is a very long response without the required wording and far too many words today.",
                quality="failed",
            )
        )
    )

    report = BenchmarkWatchdog(tmp_path).report("new")

    assert report["baseline_run_id"] == "old"
    assert report["counts"]["regressions"] == 1
    item = report["questions"][0]
    assert item["previous_response"] == "Glad to help you today."
    assert item["score_delta"] == -1.5
    assert item["regression"] is True
    assert item["validation"]["failed"] == [
        "Required phrase: glad to help",
        "at most 10 words",
    ]
    assert item["telemetry"]["missing_metrics"] == [
        "ttft_seconds",
        "tokens_generated",
        "tokens_per_second",
    ]
    assert report["personality_dimensions"]["playfulness"] == {
        "available": False,
        "value": None,
    }


def test_watchdog_surfaces_partial_tool_failure_without_claiming_model_failure(
    tmp_path,
):
    (tmp_path / "old.json").write_text(
        json.dumps(
            _run(
                "old",
                created_at="2026-01-01",
                response="Glad to help.",
                quality="passed",
                tool_status="none",
            )
        )
    )
    (tmp_path / "new.json").write_text(
        json.dumps(
            _run(
                "new",
                created_at="2026-01-02",
                response="Glad to help.",
                quality="passed",
                tool_status="failed",
            )
        )
    )

    report = BenchmarkWatchdog(tmp_path).report("new", "old")

    assert report["counts"]["failed"] == 0
    assert report["health"] == "needs_attention"
    assert report["regression_feed"][0]["failure_kind"] == [
        "personality",
        "tool_routing",
    ]
    assert report["questions"][0]["failure"]["signals"][0]["kind"] == "tool_error"


def test_watchdog_handles_unknown_run_and_does_not_invent_baseline(tmp_path):
    report = BenchmarkWatchdog(tmp_path).report("missing")
    assert report is None
