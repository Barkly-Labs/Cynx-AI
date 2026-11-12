"""Shared derivation of benchmark-level telemetry from captured request traces."""

from __future__ import annotations

import math
from typing import Any


def generation_metrics(question: dict[str, Any]) -> dict[str, int | float | None]:
    """Aggregate only measured model-output fields across a benchmark question."""
    trace = question.get("personality_trace") or {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    generations = [
        event.get("details", {}) for event in events
        if isinstance(event, dict) and event.get("stage") == "generation_response_received"
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

    token_values = [item.get("tokens_generated") for item in generations]
    duration_values = [item.get("generation_duration_nanoseconds") for item in generations]
    complete_tokens = bool(generations) and all(finite_nonnegative(value) for value in token_values)
    complete_durations = bool(generations) and all(finite_nonnegative(value) for value in duration_values)
    tokens = sum(token_values) if complete_tokens else None
    duration_ns = sum(duration_values) if complete_durations else None
    tokens_per_second = (
        tokens / (duration_ns / 1_000_000_000)
        if tokens is not None and duration_ns is not None and duration_ns > 0 else None
    )
    return {"ttft_seconds": ttft, "tokens_generated": tokens, "tokens_per_second": tokens_per_second}


def question_metrics(question: dict[str, Any]) -> dict[str, Any]:
    """Return saved metrics, filling only missing fields from captured trace data."""
    metrics = dict(question.get("metrics") or {})
    for key, value in generation_metrics(question).items():
        if metrics.get(key) is None and value is not None:
            metrics[key] = value
    return metrics
