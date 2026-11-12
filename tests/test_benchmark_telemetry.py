from benchmark.telemetry import generation_metrics, question_metrics


def test_generation_metrics_aggregate_real_prompt_and_completion_counters_across_turns():
    question = {"personality_trace": {"events": [
        {"stage": "generation_response_received", "request_id": "turn-1", "status": "completed",
         "details": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28,
                     "prompt_evaluation_duration_nanoseconds": 400_000_000,
                     "generation_duration_nanoseconds": 800_000_000}},
        {"stage": "first_model_output", "request_id": "turn-1", "status": "observed",
         "details": {"ttft_seconds": 0.125}},
        {"stage": "generation_response_received", "request_id": "turn-2", "status": "completed",
         "details": {"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42,
                     "prompt_evaluation_duration_nanoseconds": 600_000_000,
                     "generation_duration_nanoseconds": 1_200_000_000}},
    ]}}

    assert generation_metrics(question) == {
        "ttft_seconds": 0.125,
        "prompt_tokens": 50,
        "completion_tokens": 20,
        "tokens_generated": 20,
        "total_tokens": 70,
        "prompt_evaluation_duration_seconds": 1.0,
        "generation_duration_seconds": 2.0,
        "tokens_per_second": 10.0,
    }


def test_metrics_preserve_zero_and_do_not_fill_missing_counters():
    zero = {"personality_trace": {"events": [{
        "stage": "generation_response_received", "status": "completed",
        "details": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                    "prompt_evaluation_duration_nanoseconds": 0,
                    "generation_duration_nanoseconds": 0},
    }]}}
    assert generation_metrics(zero) == {
        "ttft_seconds": None, "prompt_tokens": 0, "completion_tokens": 0,
        "tokens_generated": 0, "total_tokens": 0,
        "prompt_evaluation_duration_seconds": 0.0,
        "generation_duration_seconds": 0.0, "tokens_per_second": None,
    }

    partial = {"personality_trace": {"events": [{
        "stage": "generation_response_received", "status": "completed",
        "details": {"completion_tokens": 5, "generation_duration_nanoseconds": 1_000_000_000},
    }]}}
    assert generation_metrics(partial)["completion_tokens"] == 5
    assert generation_metrics(partial)["prompt_tokens"] is None
    assert generation_metrics(partial)["total_tokens"] is None
    assert question_metrics({"metrics": {"prompt_tokens": 0}})["prompt_tokens"] == 0


def test_failed_generation_event_does_not_get_counted_as_completed_tokens():
    question = {"personality_trace": {"events": [
        {"stage": "generation_response_received", "status": "failed",
         "details": {"prompt_tokens": 20, "completion_tokens": 3}},
        {"stage": "generation_response_received", "status": "completed",
         "details": {"prompt_tokens": 10, "completion_tokens": 4,
                     "generation_duration_nanoseconds": 1_000_000_000}},
    ]}}
    metrics = generation_metrics(question)
    assert metrics["prompt_tokens"] == 10
    assert metrics["completion_tokens"] == 4
