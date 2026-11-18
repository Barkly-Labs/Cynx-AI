# DX accuracy and evaluation integrity audit

## Existing paths inspected

- Personality Studio HTTP endpoints and evaluation adapter: `interfaces/web/app.py` (`_studio_generate`, `_studio_generate_conversation`, `_studio_evaluate`, `/api/dx/personality/*`). Draft requests use the local Ollama client and isolated prompt builder; they do not use normal chat history, memory, or tools.
- Personality settings and evaluation persistence: `ai/personality_studio.py` (`personality_configs`, `personality_active`, `personality_evaluations`).
- Benchmark personality evaluation, saved reports, coverage, comparisons, and deterministic findings: `benchmark/personality/diagnostics.py`.
- Request instrumentation and persisted benchmark trace association: `ai/chat_engine.py` trace callback; `interfaces/web/app.py` `_dispatch_chat`; `interfaces/web/benchmark_runs.py` `record_personality_trace`.
- Personality Diagnostics and Studio presentation: `interfaces/web/static/dx.js` in the existing DX navigation and Benchmark Lab panels.

## Findings and repairs

| Area | Before | Repair | Remaining limit |
|---|---|---|---|
| Studio target vs observed score | Target percent was mapped linearly to a made-up 0–4 prediction, then subtracted from the judge score as a delta. | Removed the heuristic prediction and delta. Target remains a configuration value; only evidence-supported evaluator judgment is shown. | No statistically validated target-to-observation delta exists. |
| Evaluator confidence | LLM self-reported confidence was exposed in Studio and benchmark diagnostics; benchmark regression logic used it as a threshold. | Confidence is not solicited or shown as a probability. Benchmark comparison uses sample-based candidates and labels them unconfirmed; absent values remain null. | Scores remain experimental until a representative human-reviewed dataset demonstrates useful agreement. |
| Evidence sufficiency | A valid score could be accepted based on a model-selected quote, even for a very short answer. | Exact response quotes are checked. Responses under five words are marked insufficient; fabricated or too-short quotes invalidate the score. | The five-word threshold is a conservative rule, not a validated psychometric cutoff. |
| Personality vs alignment | Expression observations could be read as proof that the configured interaction style was followed. | Added a separate alignment result. It accepts only explicit, per-evaluation preference context; with no stated preference or verifiable response quote, alignment is insufficient. | The model judge still interprets behavior. It does not infer age, and does not use private memory as preference context. |
| Relationship preference handling | No dedicated evaluation context existed in Studio. | Added an optional explicit-preference field, persisted with the evaluation, and instructed the evaluator to keep age, preferences, traits, and boundaries distinct. | The tool does not establish a user's age or automatically import account preferences. |
| Human calibration | No durable label/review path or agreement statistic existed. | Added local SQLite human reviews for expression and alignment separately, per-dimension exact agreement, expression-only confusion matrix and Cohen's kappa, plus sample counts. | Descriptive sample statistics only. This is not an accuracy guarantee; selected samples and a single reviewer can bias results. No false-positive/false-negative claim is made without a calibrated reference set. |
| Multi-turn evaluation | Studio had an isolated multi-turn generator but consistency relied on a transcript string marker. | Retained real prior-turn context; consistency remains unavailable unless a multi-turn transcript is actually present. Preferences can accompany the conversation evaluation. | Relationship-style stability and preference changes across turns remain evaluator judgments, not a validated longitudinal metric. |
| Runtime trace | Existing trace records actual observed stages, request IDs, timestamps, statuses, selected context metadata, model counters, routing, tool execution, response transformation, and final output. Missing instrumented fields are marked unavailable. | Added evidence-linked root-cause hypotheses to deterministic diagnostic findings. Captured stage failures and observed output transformations are distinguished; missing traces produce “insufficient diagnostic evidence.” | Classification internals, context source IDs, some prompt transformations, output validation, and memory persistence are not consistently instrumented by every request path. No new event is fabricated to fill those gaps. |
| DX display | Personality Diagnostics displayed evaluator confidence and a confidence history chart. | Replaced that panel with evaluation coverage and removed confidence from ordinary diagnostic findings. Studio explains experimental expression scores and displays alignment separately. | This change does not audit every unrelated DX metric, chart, or page. |

## Trace interpretation

The trace collector persists an event only when the execution path emits it. `request_received`, context retrieval/preparation, configuration, constructed model messages, routing, tool calls, generation output/metrics, response transformation, and completion are observable where the corresponding hooks execute. A stage absent from a trace means it was not captured; it must not be interpreted as successful. Root-cause findings distinguish an observed stage failure from a confirmed causal explanation. A changed original/final response is a confirmed transformation observation; the reason for that change may still need investigation.

## Score definitions

- **Configured target:** saved 0–100 tendency. It is not a probability that the trait will appear in every answer.
- **Observed expression (0–4):** experimental local-evaluator judgment of the quoted response in context. Null means insufficient evidence. It is not an objective personality measurement.
- **Preference alignment:** separate categorical judgment against preferences explicitly supplied for that evaluation. Without explicit preferences and response evidence it is “insufficient evidence.”
- **Human review:** a saved reviewer label for one evaluation and one dimension. Expression labels are strong/mixed/weak/insufficient; alignment labels are aligned/mixed/misaligned/insufficient.
- **Agreement:** exact categorical agreement is reported with counts, separately by dimension. Cohen's kappa is calculated only for expression labels. It is descriptive and is not represented as calibrated evaluator confidence.

## Verification scope

Automated checks cover Studio generation/evaluation, quote validation, short-response insufficiency, multi-turn context, configuration isolation, review persistence/API, expression/alignment calibration separation, benchmark diagnostic evidence, trace behavior, and frontend diagnostic polling. A live Ollama and browser session were not used for this change. The complete visual hierarchy and every non-personality DX metric were not exhaustively browser-audited in this pass; those are explicit remaining verification items rather than claimed complete.
