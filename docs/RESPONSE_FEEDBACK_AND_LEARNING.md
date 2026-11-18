# Response Feedback, Learning Candidates, and Context Retrieval

## Architecture audit

The existing `knowledge` table is live: `ContextManager` retrieves it during chat and `ChatEngine` places context into the prompt. Its write/search behavior persisted across a database reopen, but the original search treated importance as a match even when query terms did not overlap. Duplicate entries were possible. The table had no source, owner, lifecycle, or review fields.

In the inspected database snapshot, `knowledge` and the server `conversations` table had no rows, while `memories` had 29 rows. The separate `memories` table is also live and remains intact. The server `conversations` table is not the source of browser chat history; the web shell stores conversations in browser local storage, while active engine history is process-local. The feedback implementation therefore attaches feedback to the existing conversation UUID and assistant request UUID, without replacing either memory system.

## Data and lifecycle

- `memory.sqlite.ensure_schema()` adds nullable/defaulted columns to the existing `knowledge` table. Existing rows remain `knowledge_type=legacy`, `status=active`.
- `response_feedback` stores only a rated example and model/configuration metadata. Before a user rates a response, the text is held in a bounded, four-hour in-memory cache.
- A rating can be updated. The same feedback ID upserts its one linked candidate, preventing duplicate candidates.
- New candidates are `unverified_candidate`, scoped to the local chat user, and explicitly labeled as subjective signals. They are not generalized to other users.
- The DX Learning & Feedback view supports accepting as user context, accepting a shared behavioral lesson, correcting a candidate, and discarding it. Review is authenticated and CSRF-protected by the existing DX middleware.
- The existing memory extractor is unchanged. Feedback does not rewrite personality settings, prompts, model configuration, or memory automatically.

## Retrieval and evaluation

The knowledge search now requires meaningful token overlap and is scoped to legacy/global lessons plus the current user's active context and unverified candidates. Context retrieval labels feedback as a signal, bounds example text, and appends it to the existing knowledge context. Historical response comparisons use local Ollama in a single-worker queue; they validate structured output and evidence excerpts, store subjective dimension scores and limitations, and never block a chat response. A full queue or local evaluator failure is surfaced as unavailable rather than changing generation behavior.

## API routes

- `GET /api/feedback/{conversation_id}/{message_id}`: current rating, comparison state, and whether the response can still be rated.
- `POST /api/feedback/{conversation_id}/{message_id}`: submit or update `rating` (`up`/`down`), optional category, and optional explanation.
- `DELETE /api/feedback/{conversation_id}/{message_id}`: remove the rating, candidate, and comparison.
- `GET /api/dx/knowledge/lessons`, `GET /api/dx/feedback/evaluations`, and `POST /api/dx/knowledge/{id}/review`: authenticated lesson review and comparison history.

Feedback and learning candidates are local database records. No external service or remote model is used.

## Verification

Run `python -m unittest tests.test_feedback_learning -v` for migration, search relevance, scoping, feedback upsert/restart/delete, context retrieval, assessment evidence validation, and input validation coverage. Run `node --test tests/frontend_feedback.test.cjs` for feedback-control and review-view contract checks. Frontend scripts can be checked with `node --check interfaces/web/static/chat.js`, `node --check interfaces/web/static/chat-shell.js`, and `node --check interfaces/web/static/dx.js`.

## Review, privacy, and extension notes

A negative rating always creates an unverified, user-scoped candidate. A positive rating is retained as a historical example; it creates a candidate only when accompanied by an explanation. Candidate confidence values are simple heuristics and are not calibrated probabilities. Accepting a candidate as shared behavior requires an administrator to enter generalized text; private user context is removed from the shared record's learning payload. User-context records can be corrected or discarded, and source feedback IDs remain attached for auditability.

To add an evaluation dimension, add its stable key to `EVALUATION_DIMENSIONS` in `ai/feedback/service.py`, then update the local evaluator's dimension descriptions in `_evaluate_feedback_examples` in `interfaces/web/app.py`. Keep the score scale explicit and validate any evidence against the actual response before persisting it. Do not treat evaluator confidence as calibrated or scores as objective truth.

Plain legacy `KnowledgeStore.add()` remains compatible with old callers. Feedback candidates are deduplicated by their unique `source_feedback_id`; general legacy entries do not have a reliable source key and may still be duplicated by older callers.
