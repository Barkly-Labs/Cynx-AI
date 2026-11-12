# CYN-X DX Benchmark Lab audit

Audit date: 2026-11-12

## Scope and implementation map

The existing page is served by `interfaces/web/templates/dx.html` and rendered by
the single vanilla-JavaScript DX client in `interfaces/web/static/dx.js`. Its
shared visual rules are in `interfaces/web/static/cynx-theme.css` and
`interfaces/web/static/dx.css`; Benchmark Lab-specific tabs, diagnostics, and
charts are in `dx.css`. The API lives in `interfaces/web/app.py`. Persistent
background execution, event polling, saved snapshots, and summary calculations
are in `interfaces/web/benchmark_runs.py`. Read-only comparisons are in
`benchmark/watchdog.py`. Personality contract evaluation and historical series
are in `benchmark/personality/diagnostics.py`.

The page does not have a separate development preview or a second pipeline
component. The DX document loads the same `dx.js` and stylesheet bundle for the
actual `/dx` page. The benchmark worker dispatches through the ordinary CYN-X
chat request dispatcher; it does not call a second model engine.

## Data and interaction inventory

| UI item / location | Meaning and source of truth | Current implementation / status | Required behavior or limitation |
|---|---|---|---|
| Benchmark Lab dataset dropdown | Suite filename/name/count from `GET /api/dx/benchmark/suites`; question records from `GET /api/dx/benchmark/suites/{suite_id}` | Reads JSON suites in `benchmark/suites`; empty/invalid suites are omitted or rejected | Data-backed; suite count is the actual case count |
| Suite records and question positions | Case objects in selected suite JSON | Manager validates case records at run start and assigns one-based positions | Fixed: invalid cases now reject the run with their position instead of being silently skipped and shrinking the total |
| Execution mode dropdown | `automatic` or `manual`; sent to `POST /api/dx/benchmark/start` | Backend manager controls sequence and pauses after each manual question | Data-backed; manual next-question control only appears while paused |
| Start Benchmark | Starts persistent run via `/api/dx/benchmark/start` using idempotency key; manager blocks a second active run | UI has `startBusy`; backend also enforces active-run uniqueness and idempotency | Functional; duplicate UI submits are guarded, duplicate backend starts are rejected/replayed |
| Previous runs list | `GET /api/dx/benchmark/runs`; status, completed/attempted, average score, average response duration | Manager-format and legacy summary rows were mixed; legacy rows could not be opened through the run detail route | Fixed: unavailable values render as unavailable; legacy snapshots are exposed as read-only runs without changing their saved records |
| Run ID / run title | Persistent `run_id`, suite name, mode from snapshot | `GET /active`, `/latest`, `/runs/{id}`; run ID/question IDs are generated and persisted by manager | Data-backed |
| Run status indicator | Persistent manager status: running, paused, completed, completed with failures, stopped, interrupted, failed | Derived from worker lifecycle and saved question states | Data-backed; status is not inferred from UI timing |
| Progress bar and percentage | Attempted questions divided by total; attempted excludes pending and running | Counts from manager snapshot, refreshed by `/updates?after_event=` | Percent is an execution count, not a quality pass rate |
| Completed count | Questions whose saved request completed | `counts.completed` from question statuses | Does not imply the rubric passed |
| Pending count | Questions still pending | `counts.pending` | Data-backed |
| Rubric passed count | Questions with explicit rubric and every scored rubric check passed | `counts.passed` / `quality_status` | Cases without a pass rule are not counted as passes |
| Failed count | Request failures plus explicit failed rubric verdicts | Manager count; Watchdog also separates technical and rubric signals | Data-backed; tool failures may be partial and are reported separately in Watchdog |
| Interrupted count | Cancelled or restart-interrupted questions | Saved question status | Data-backed |
| Total elapsed | Benchmark execution time | Manager accumulated active execution segments | Fixed: new runs exclude paused/waiting time; older snapshots retain fallback wall-time behavior when no accumulator exists |
| Current/last question | Actual suite question, position, category, status, start timestamp, live duration or saved duration | Current question is selected from persisted question state | Fixed label changes to “Last question” for terminal runs |
| Actual CYN-X response | Exact response returned by normal chat dispatch; multi-turn scenarios preserve turn records | Live response appears when completed; web chat route is currently non-streaming | No placeholder response is used; it explicitly says generation is non-streaming while active |
| Current error and request ID | User-safe failure text and request identifier | Saved question error/request data; raw exceptions remain in developer logs | Data-backed; unavailable IDs remain unavailable |
| Live lifecycle stage | Last stage event for the active chat request | `live_request_events` from `PipelineEventStore`, otherwise saved request events | Data-backed when stage events exist; empty trace is not presented as successful execution |
| Connection indicator | Success or error of polling/reconnect request | `/active`, `/latest`, `/runs/{id}/updates` polled every 900 ms | Reconnects on next poll; network error is explicitly shown |
| Pause | Requests pause after active question completes | `POST /runs/{id}/pause`; worker persists paused status | Functional; elapsed accumulator now includes the just-finished active interval before pause |
| Resume | Resumes paused/interrupted saved run | `POST /runs/{id}/resume` | Functional for supported run statuses |
| Run Next Question | Executes one question in manual mode | `POST /runs/{id}/next` | Functional; hidden outside manual paused state |
| Stop | Cancels active request and preserves completed questions | `POST /runs/{id}/stop`; pipeline cancellation event and worker persistence | Functional; in-flight question is interrupted, completed results remain |
| Run Again | Starts selected suite/mode through normal start path | Start button and backend manager | Functional; duplicate/active-run rules still apply |
| Clear Results | Confirmation followed by DELETE on benchmark run collection | Backend removes saved run files and personality sidecars, retaining active runs | Functional; destructive action is confirmed |
| Question Results tab | Actual response, question, duration, score/rubric status, TTFT, token counts, throughput, tools | Persisted question records and request trace | Each unavailable metric displays “unavailable”; completed responses remain after following questions start |
| Watchdog health totals | Total, passed, failed, regressions, interrupted | `GET /api/dx/benchmark/watchdog?run_id=...`; read-only normalization/comparison of actual stored runs | Passed means explicit quality rubric passed; no pass rule is not a pass |
| Watchdog regression feed | Saved request/rubric/tool/format failures, compared with previous terminal same-suite run | Watchdog signals from actual response, status, request events, tool records, and rubric | Diagnostic explanations are evidence-based heuristics, not model causal claims |
| Watchdog comparison rows | Prior/current score, response, runtime, TTFT, tokens, tool changes | Watchdog compares matched test ID/category/question and saved fields | Missing comparisons/measurements remain unavailable; no baseline is fabricated |
| Failure Inspector | Prompt, expected behavior, prior/current response, failed validations, signals, request telemetry | Selected Watchdog question report | Missing test details and telemetry are labeled unavailable |
| Watchdog personality dimensions | Trait-specific scores | Not emitted by existing benchmark scorer; API returns `available:false` | UI honestly says “Not measured”; no inferred trait values |
| Personality contract and dimensions | Versioned contract JSON with dimension definitions and expected/undesirable behavior | `benchmark/personality/contract-v1.json` loaded by diagnostics service | Versioned and data-backed |
| Personality evaluation control | Evaluates completed eligible scenario questions using actual saved multi-turn replies; local Ollama judge where configured | `POST /api/dx/benchmark/personality/{run_id}/evaluate` | No runtime personality prompt/tools are changed; missing evaluator/data yields inconclusive/unavailable findings |
| Personality run/baseline filters | Selected run and same-suite previous or reviewed baseline | `/api/dx/benchmark/personality/history?run_id=&baseline_id=` | Filters query stored diagnostic sidecars; selected run is retained in client state |
| Personality summary counts | Eligible/evaluated scenarios, scored dimensions, personality/technical findings, inconclusive results | Stored report `evaluation_coverage` and `diagnostics` | Missing results are not converted to zero |
| Dimension result cards | Mean evidence-backed evaluator score (0–4) by dimension for current run | Stored evaluator records and contract dimensions | Untargeted dimensions say not targeted; absent scores say not evaluated |
| Personality trend graph | Scores over timestamped evaluated runs, 0–4 scale | Stored diagnostic history summaries; null values break line segments | Real data only; no points for unevaluated dimensions |
| Personality dimension filters | Select which contract dimensions to draw | Frontend checked dimension set | Functional; rerenders chart only |
| Delta/regression chart | Current minus selected baseline dimension score | Two real diagnostic history points with scores for same dimension | Missing point pair is omitted; configured threshold and sample confidence determine candidates |
| Scenario performance bars | Average score by recorded scenario category | Current stored report, evaluator dimension scores | Only scored categories are drawn |
| Severity history graph | Stored count of diagnostics by severity per evaluated run | Sidecar reports, sorted by timestamp | Empty history has an explicit empty state |
| Confidence graph | Mean evaluator self-reported confidence (uncalibrated) and evaluated/eligible scenario coverage | Stored evaluator confidence and coverage | Percent is not called a calibrated probability; zero-eligible runs are omitted |
| Personality regression list | Dimension/scenario deltas, prior/current score, threshold, baseline ID, candidate status | Diagnostic service comparison logic; requires comparable stored evidence and confidence | Candidates remain unconfirmed until sufficient samples/calibration; no missing scores become zero |
| Personality evidence details | Observed behavior, expected behavior, concise interpretation, exact quote references, confidence, recommendations | Saved diagnostic records; quote references validated against actual conversation turns | Expandable; hidden reasoning is excluded; confidence remains marked uncalibrated |
| Mark known-good baseline | Human-reviewed, fully passing, sufficiently confident diagnostic record | `POST .../{run_id}/review-baseline` validates the report | Rejects unreviewed, incomplete, low-confidence, or failed reports |
| Personality Trace question dropdown | Executed saved question | Questions on selected run | Functional for running and historical runs |
| Trace timeline | Captured runtime stages, timestamps, statuses, and redacted details | Per-question `personality_trace` callback events stored in run JSON | Only occurred instrumentation events appear; unavailable instrumentation is identified |
| Copy trace | Copy selected run/question/request identifiers and events | Clipboard API using rendered trace data | Functional where browser clipboard permission is available; otherwise reports unavailable |
| Performance elapsed | Saved question response duration | Dispatch timing or manager-measured question duration | A stored duration is shown; absent legacy value remains unavailable |
| Performance TTFT | Time-to-first-token | Ollama/streaming trace only | Current normal web response is non-streaming; unavailable unless real telemetry exists |
| Performance tokens | Tokens generated and tokens/second | Actual generation event/metrics | Not estimated; unavailable if the request pathway did not return them |
| Performance tool calls | Number of recorded tool invocations | Persisted tool summaries from real request events | New manager runs distinguish known zero from invocations; old records without tool telemetry may not establish a true zero |
| Performance run elapsed | Accumulated execution elapsed | Run snapshot | New runs use accumulated active execution time; legacy value unavailable if not persisted |
| Errors / Diagnostics tab | Failed/interrupted questions, saved error, request ID | Persistent question statuses and safe error strings | Raw stack traces stay in logs; empty state means no saved failure/interruption |
| DX History summary table | Suite, completed/attempted, average score, average response time, failure count | Run list API across manager and legacy summaries | Fixed to display unavailable values honestly; legacy runs now open read-only |
| DX History comparison table | Timestamped stored score/time/failure values for most recent ten runs | Same run-list API | This is a tabular comparison, not a performance-over-time chart |
| Context panel saved run count | Number of records returned by run list endpoint | `GET /api/dx/benchmark/runs` | Data-backed; API errors do not fabricate a count |
| Mascot/status labels and empty/loading/error text | Presentational UI, not benchmark measurements | Shared DX template/client/theme | No numeric claim; content reflects endpoint/run state |

## Changes made in this audit

- Legacy `/api/dx/benchmark/runs` records can now be opened as read-only question
  histories through the existing run detail/update API. IDs are deterministic
  for these read-only synthesized views; original JSON files are untouched.
- The legacy save route stores missing, invalid, or non-finite response timing
  as unavailable and calculates averages only from actual timing values.
- Suite starts reject malformed cases instead of silently omitting them, so the
  displayed dataset count and actual run total cannot diverge unnoticed.
- Failed legacy rows do not contribute to the response-score average. An empty
  scored set produces `null`, not a fabricated `0`.
- DX overview and history cells render absent metrics as “Not available” rather
  than coercing them to zero or displaying `nulls`/`undefined`.
- Terminal run question labeling now says “Last question.”
- New manager runs report accumulated execution time and exclude time spent
  paused. Older snapshots without the accumulator retain the wall-time fallback.

## Known instrumentation limitations

- The current `/chat` path is non-streaming, so TTFT and streaming updates are
  not available unless emitted by the active model trace.
- Model token counts, tokens/second, configured generation parameters,
  tokenizer-based context utilization, and per-run available-tool inventory are
  not consistently captured by the current request pathway.
- The standard benchmark scorer does not emit personality trait scores. The
  Watchdog leaves these explicitly unavailable; Personality Diagnostics is a
  separate local-judge flow for eligible versioned scenarios.
- No standalone performance-over-time chart exists in Benchmark Lab. The
  existing charts are personality score, delta, scenario, severity, confidence,
  and coverage charts, all sourced from saved diagnostic records.
- Legacy snapshots do not contain request identifiers, per-question trace
  events, tokens, or TTFT. Their missing values remain unavailable.
