# CYN-X Main Chat Redesign

This is a source overlay for the existing CYN-X-AI repository. It preserves the existing `/chat` dispatcher, Ollama client, prompt-layer pathway, tools, memory service, Lepro controls, and request-event API.

## Included changes

- Shared Barkly Labs/CYN-X design tokens used by both the chat screen and DX.
- Responsive sidebar, local searchable conversation list, welcome screen with the existing mascot, and multiline composer.
- Existing prompt-layer controls presented as a compact style/configuration panel.
- Existing model-selection API and Lepro device controls surfaced in the sidebar.
- Existing request pipeline changed to a compact modeless status dock so it does not block chat interaction.
- New conversation IDs isolate short-term chat context while retaining the existing shared long-term memory user and memory extraction behavior.
- Tests for preserved controls/assets and conversation context isolation.

Conversation transcripts are saved in browser local storage. Short-term server context remains in memory, as in the existing application; a server restart clears that short-term context. The existing backend does not stream response tokens, so the interface shows real generation status and final responses without simulated token streaming.

## Integration

Copy the included files to the same paths in the CYN-X-AI repository, reviewing the full-module replacements if your checkout contains local changes. This overlay includes the existing DX benchmark and trace files because `app.py` imports them.

## Verification

```bash
pytest -q tests/test_personality_trace.py tests/test_benchmark_run_manager.py tests/test_dx_api.py
pytest -q tests/test_live_decision_pipeline.py tests/test_personality_trace.py
node --test tests/frontend_pipeline.test.cjs
node --check interfaces/web/static/chat.js
node --check interfaces/web/static/chat-shell.js
python -m py_compile ai/chat_engine.py ai/prompt_builder.py interfaces/web/app.py interfaces/web/benchmark_runs.py
```
