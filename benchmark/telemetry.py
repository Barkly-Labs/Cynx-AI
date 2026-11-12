"""Shared derivation of benchmark-level telemetry from captured request traces."""

from __future__ import annotations

import math
from typing import Any


def generation_metrics(question: dict[str, Any]) -> dict[str, int | float | None]:
    """Aggregate only measured Ollama fields across calls in a benchmark question."""
    trace = question.get("personality_trace") or {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    generations = [
        event.get("details", {}) for event in events
        if isinstance(event, dict) and event.get("stage") == "generation_response_received"
        and event.get("status", "completed") == "completed"
        and isinstance(event.get("details"), dict)
    ]

    def finite_nonnegative(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0

    first_output = next((event.get("details", {}) for event in events
                         if isinstance(event, dict) and event.get("stage") == "first_model_output"
                         and isinstance(event.get("details"), dict)), {})
    ttft = first_output.get("ttft_seconds")
    if not finite_nonnegative(ttft):
        ttft = next((item.get("ttft_seconds") for item in generations
                     if finite_nonnegative(item.get("ttft_seconds"))), None)

    prompt_values = [item.get("prompt_tokens") for item in generations]
    completion_values = [item.get("completion_tokens", item.get("tokens_generated")) for item in generations]
    prompt_duration_values = [item.get("prompt_evaluation_duration_nanoseconds") for item in generations]
    duration_values = [item.get("generation_duration_nanoseconds") for item in generations]
    complete_prompt = bool(generations) and all(finite_nonnegative(value) for value in prompt_values)
    complete_completion = bool(generations) and all(finite_nonnegative(value) for value in completion_values)
    complete_prompt_durations = bool(generations) and all(finite_nonnegative(value) for value in prompt_duration_values)
    complete_durations = bool(generations) and all(finite_nonnegative(value) for value in duration_values)
    prompt_tokens = sum(prompt_values) if complete_prompt else None
    completion_tokens = sum(completion_values) if complete_completion else None
    total_tokens = (prompt_tokens + completion_tokens
                    if prompt_tokens is not None and completion_tokens is not None else None)
    prompt_duration_ns = sum(prompt_duration_values) if complete_prompt_durations else None
    duration_ns = sum(duration_values) if complete_durations else None
    generation_duration_seconds = duration_ns / 1_000_000_000 if duration_ns is not None else None
    prompt_evaluation_duration_seconds = prompt_duration_ns / 1_000_000_000 if prompt_duration_ns is not None else None
    tokens_per_second = (
        completion_tokens / generation_duration_seconds
        if completion_tokens is not None and generation_duration_seconds is not None and generation_duration_seconds > 0 else None
    )
    return {
        "ttft_seconds": ttft,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens_generated": completion_tokens,
        "total_tokens": total_tokens,
        "prompt_evaluation_duration_seconds": prompt_evaluation_duration_seconds,
        "generation_duration_seconds": generation_duration_seconds,
        "tokens_per_second": tokens_per_second,
    }


def question_metrics(question: dict[str, Any]) -> dict[str, Any]:
    """Return saved metrics, filling only missing fields from captured trace data."""
    metrics = dict(question.get("metrics") or {})
    for key, value in generation_metrics(question).items():
        if metrics.get(key) is None and value is not None:
            metrics[key] = value
    for key in (
        "response_time_seconds", "ttft_seconds", "prompt_tokens", "completion_tokens",
        "tokens_generated", "total_tokens", "prompt_evaluation_duration_seconds",
        "generation_duration_seconds", "tokens_per_second",
    ):
        metrics.setdefault(key, None)
    return metrics
