# Companion Personality Studio

## Architecture

The Studio is a view inside the existing `/dx` application. `ai/personality_studio.py` owns the SQLite-backed version, active pointer, preset library, and evaluation records. `ai/personality.py` remains the production personality entry point. Once a Studio config is explicitly activated, both V1 `PromptManager` and V2 `ContextBuilder` read it through `build_personality_prompt`; until then, the existing legacy personality remains authoritative.

Draft state is kept in browser local storage and never becomes production state. Preview/evaluation uses a fresh `PromptBuilder`, the production prompt assembly path, and the configured local Ollama client. It sends no tools, uses no chat history or retrieved memory, and does not call conversation persistence or memory extraction. Only the activation API changes the active configuration. Activation uses SQLite `BEGIN IMMEDIATE` plus an expected-version check; stale tabs receive HTTP 409. Restoring a version creates a new immutable version, and restoring the initial legacy version reactivates the original legacy behavior.

## API

- `GET /api/dx/personality/studio`: active version, immutable history, presets, trait definitions, starter draft, and saved evaluations.
- `POST /api/dx/personality/preview`: actual draft response only; no persistence.
- `POST /api/dx/personality/evaluate`: actual response plus local-model evaluation; saved locally.
- `POST /api/dx/personality/evaluate-batch`: 1–20 independent prompts, each saved separately; failures are reported by index.
- `POST /api/dx/personality/conversation`: 2–10 sequential turns with prior turns in context; saves actual transcript and turn evidence.
- `POST /api/dx/personality/compare`: identical prompt against two drafts and optionally two installed local Ollama models.
- `POST /api/dx/personality/activate`: explicit activation with `expected_version`.
- `POST /api/dx/personality/restore`: restore a saved version as a new version.
- `POST`, `DELETE /api/dx/personality/presets...`: save/update and delete draft presets.
- `POST /api/dx/personality/import`, `GET /api/dx/personality/export/{preset_id}`: validated JSON preset transfer.
- `GET /api/dx/personality/evaluations`: saved evaluation history.

## Evaluation method and limits

The evaluator is the selected local Ollama model, asked for JSON ratings from 0–4, confidence, concise explanation, possible contradictions, missing evidence, and a short response excerpt. Quotes must exactly occur in the generated response; otherwise the score is marked insufficient. Hidden `<think>`/`<analysis>` text and common credential forms are redacted before display and persistence. The raw model response remains visible apart from those redactions.

Scores are model interpretations, not ground truth. Confidence is uncalibrated. The displayed expected score is an explicitly uncalibrated linear mapping of target percent to 0–4; deviation is therefore exploratory. Single-response consistency is unavailable. Multi-turn consistency is only shown when the evaluator returns a valid score for a multi-turn transcript. Repeated runs and human review remain necessary before treating changes as regressions.

The owner example in the brief is installed as a draft preset only. Existing installations initialize the active pointer from the current legacy matrix; traits that the old matrix did not measure are stored as `null` until activation. No model behavior is verified in this environment because the local Ollama endpoint was unavailable during implementation.
