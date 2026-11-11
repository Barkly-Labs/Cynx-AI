# CYN-X DX Personality Trace integration

This is a source overlay for the existing CYN-X-AI repository. Copy the included files into the repository at the same relative paths, replacing the corresponding files. It extends the existing benchmark run JSON records; no database migration is required.

## Included changes

- Runtime trace capture in the existing ChatEngine and PromptBuilder.
- Association and persistence of trace events with benchmark run, question, and request IDs.
- DX Personality Trace, Performance, and Diagnostics tabs with per-question trace selection.
- Tests for runtime capture, persistence, redaction, historical retrieval, DX asset serving, and benchmark dispatch integration.

## Verify

From the repository root:

```bash
pytest -q tests/test_personality_trace.py tests/test_benchmark_run_manager.py tests/test_dx_api.py
node --check interfaces/web/static/dx.js
python -m py_compile ai/chat_engine.py ai/prompt_builder.py interfaces/web/app.py interfaces/web/benchmark_runs.py
```

The current architecture does not provide a separate policy classifier, memory source IDs, model-version reporting, or a configurable trace-retention policy. These are identified as unavailable by the UI. Tool output payloads are intentionally omitted from the trace; invocation references and context-inclusion status are captured.
