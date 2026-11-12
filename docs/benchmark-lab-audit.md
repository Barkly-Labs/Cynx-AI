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
- When the model trace provides generation token counts and evaluation duration,
  new benchmark snapshots now persist TTFT, total generated tokens, and
  aggregate tokens/second. If any turn in a multi-turn question lacks the
  required values, the corresponding aggregate remains unavailable.
- Configured generation parameters, tokenizer-based context utilization, and
  per-run available-tool inventory are not captured by the current request
  pathway.
- The standard benchmark scorer does not emit personality trait scores. The
  Watchdog leaves these explicitly unavailable; Personality Diagnostics is a
  separate local-judge flow for eligible versioned scenarios.
- No standalone performance-over-time chart exists in Benchmark Lab. The
  existing charts are personality score, delta, scenario, severity, confidence,
  and coverage charts, all sourced from saved diagnostic records.
- Legacy snapshots do not contain request identifiers, per-question trace
  events, tokens, or TTFT. Their missing values remain unavailable.

## Run Benchmark datapoint-to-source audit (2026-11-12)

This pass traced the rendered Run Benchmark values from `dx.js` through the
existing API and manager snapshot to their originating suite, scorer, request
trace, or lifecycle clock. The table groups values by UI binding; repeated
appearances of the same source (for example, TTFT in Results and Performance)
are counted once. Status `Connected` means the existing source was already
correct; `Fixed` means the existing source now reaches the appropriate view;
`Unavailable` means the runtime does not provide evidence for the value.

| Datapoint binding | UI location | Pipeline source and stage | Persistence/API/frontend path | Status and change |
|---|---|---|---|---|
| Suite ID, suite display name, question count | Dataset selector | `benchmark/suites/*.json`; catalog reads cases | `/api/dx/benchmark/suites` → suite selector | Connected; count is the actual case-list length. |
| Run ID, run name, suite, mode, creation time, run status | Run history and run header | Manager-generated run ID; selected suite/mode; persisted lifecycle timestamps/status | `BenchmarkRunManager` JSON snapshot → runs/detail API → `dx.js` | Connected. |
| Total questions, processed questions, progress percentage | Overview progress bar | Persisted question statuses; processed = total minus pending and running | Manager `counts` and `total` → `/updates` → progress calculation | Connected; accessible value text reports processed count rather than claiming all processed cases passed. |
| Completed, pending, rubric-passed, failed, interrupted | Overview counters | Question status plus explicit scorer rubric verdict | Manager `_counts()` → `counts` → overview cards | Connected; rubric pass is distinct from request completion. Failed combines failed requests and explicit rubric failures as defined by existing manager semantics. |
| Run elapsed seconds | Overview and Performance | Manager’s accumulated active execution intervals | Snapshot `elapsed_total_seconds` → `_run_elapsed()` → public `elapsed_seconds` → UI | Connected; paused time excluded for new snapshots; old records use their existing fallback. |
| Current/last question position and total | Overview | Current question ID or last non-pending persisted question | Snapshot questions/current ID → `dx.js` | Connected. |
| Question test ID, category, exact prompt, question status | Overview and Results | Selected suite case and manager lifecycle status | Snapshot question fields → detail/updates API → UI | Connected. |
| Question start timestamp, live duration, final duration | Overview and Results | Manager `started_at`; browser elapsed display while running; persisted manager `duration_seconds` on finish | Snapshot fields → detail/updates API → UI | Connected; live duration is a view of elapsed time from the saved start timestamp, final duration is persisted. |
| Actual generated response and multi-turn response records | Overview and Results | Normal `/chat` dispatch result and each actual scenario turn | `response` and `conversation_turns` snapshot fields → API → UI | Connected; no placeholder response is persisted. Streaming is unavailable on the current benchmark web path. |
| Error explanation, question status, terminal request ID | Overview, Results, Errors | Dispatch exception/cancellation and returned terminal request ID | Safe `error`, `status`, `terminal_request_id` in question snapshot → API → UI | Fixed; failure diagnostics now point to the actual failing/cancelled final turn when multi-turn. Raw exceptions remain logs only. |
| Live request stage and stage status | Overview | `PipelineEventStore` stages for current request; saved request events after completion | `/updates` live events or question `request_events` → UI | Connected for stages actually emitted; no event is represented as success. |
| Connection status | Overview | Success/failure of active/detail/update API polling | Client poll result/catch state → connection label | Connected; interrupted connection says retrying. |
| Question result status and quality status | Questions / Results | Request lifecycle plus rubric evaluation | Snapshot `status`, `quality_status` → detail API → Results tag | Connected; request completion does not imply rubric pass. |
| Overall score, rubric passed count, rubric total | Questions / Results and Watchdog | Existing `score_response()` output | Saved `score` → run API → UI | Connected; missing/unscored values remain unavailable. |
| Question response duration | Results and Performance | Real dispatch `response_time`; manager-measured duration fallback only when dispatch did not supply valid duration | `metrics.response_time_seconds` and `duration_seconds` in snapshot/API | Connected; invalid/non-finite timing is not accepted as a measurement. |
| Time to first token (TTFT) | Results, Performance, Watchdog | `ai/chat_engine.py` first output or generation trace event | Per-request `personality_trace` → shared `generation_metrics()` → saved `metrics`, public question, Watchdog | Fixed; first actual observed output is used; no timing is inferred for non-streaming requests. |
| Tokens generated | Results, Performance, Watchdog | Ollama `eval_count` on each `generation_response_received` trace event | Trace event details → shared aggregate → saved question metrics/API → UI | Fixed; sums all turns only when each turn has a measured count. |
| Tokens per second | Results, Performance, Watchdog | Total measured generation tokens divided by total measured Ollama evaluation nanoseconds | Same trace aggregate → persisted/API metric → UI | Fixed; unavailable if any turn is missing a count/duration or total generation duration is zero. |
| Tool call name, status, duration, and count | Results, Performance, Watchdog comparison | Actual tool lifecycle events captured in request pipeline | Request events → request-scoped tool summary → `tools` and availability flag in snapshot/API → UI | Fixed; repeated invocation IDs are scoped by request ID; old ambiguous empty lists are unavailable, not falsely zero. |
| Request event ID, request ID, turn index, event type, stage/status, elapsed time | Personality Trace and Watchdog telemetry | Actual pipeline event and originating chat request | Saved `request_events` retains request/turn association → API → UI | Fixed for new manager snapshots; legacy event records may lack these identifiers. |
| Run/question/request identifiers, trace stage, trace status, timestamp, redacted details | Personality Trace | Runtime trace callbacks and request pipeline instrumentation | Per-question `personality_trace.events` in run JSON → run API → UI | Connected; only actual emitted events appear. |
| Diagnostic final response | Personality Trace | Final saved response from the benchmark question | Question `response` → run API → trace panel | Connected. |
| Watchdog total, passed, failed, regressions, interrupted, health | Watchdog | Selected run’s saved question states/rubric results and matched baseline | Watchdog reads run snapshots → `/watchdog` → client cards/status | Connected; no baseline or unavailable data is synthesized. |
| Watchdog baseline run ID/note; regression test ID/category/failure kind/explanation | Watchdog feed and comparison | Previous terminal run of same suite; real matched question evidence | Watchdog comparison output → `/watchdog` → UI | Connected; explanations are evidence-based signals, not claims about hidden causes. |
| Previous/current score and score delta | Watchdog comparison | Saved scorer output for matched question IDs/test keys | Watchdog compare → API → comparison rows | Connected; delta is null if either score is absent. |
| Previous/current response | Watchdog comparison and Failure Inspector | Actual responses saved in each matched run | Watchdog report → API → UI | Connected. |
| Previous/current runtime, TTFT, token count, tool changes | Watchdog comparison | Saved response duration and shared trace-derived metrics/tool availability | `question_metrics()` and `_observed_tools()` → report/API → UI | Fixed; same metric aggregation is used for current and historical traces; ambiguous legacy tool measurements stay unavailable. |
| Original prompt, expected behavior, actual behavior, validation checks, failed labels | Watchdog Failure Inspector | Saved case prompt/test rubric and actual response; deterministic rubric re-evaluation | Watchdog failure report → API → inspector | Connected; labels remain unavailable if not persisted or not defined. |
| Watchdog runtime telemetry request ID, event list, available/missing metric names | Failure Inspector | Terminal request ID, saved request events, question metrics | Watchdog telemetry projection → API → UI | Fixed; terminal request ID now identifies final/failing turn. |
| Watchdog personality trait values | Watchdog personality panel | Standard benchmark scorer has no trait-level output | Watchdog marks each dimension unavailable → API → UI | Unavailable by design; no traits are inferred from response text. |
| Personality run ID, contract version, calibration status | Personality Diagnostics | Persisted report, versioned contract, human review status | Diagnostic sidecar/history API → UI | Connected. |
| Personality eligible/evaluated/inconclusive scenario counts and dimension evaluation count | Personality Diagnostics summary | Suite target dimensions and persisted evaluator records/coverage | `run_context` + diagnostic report → history API → UI | Connected; missing evaluations are not zero scores. |
| Personality finding counts (personality and technical) | Personality Diagnostics summary | Saved diagnostic classification/status | Diagnostic sidecar → history API → UI | Connected. |
| Dimension names, descriptions, target counts, evaluation statuses and scores | Dimension cards | Versioned contract, suite target metadata, validated evaluator records | Contract + run context + report → history API → cards | Connected; untargeted and unavailable dimensions remain distinguishable. |
| Dimension selection filters | Personality trend graph | User-selected dimension IDs | Frontend filter state → chart renderer | Connected control; not a measured datapoint. |
| Historical dimension score/date/run points | Personality trend graph | Saved diagnostic sidecars with finite scores only | History API trend → graph | Connected; null evaluations create no points. |
| Comparison threshold, baseline ID, prior/current dimension score, delta, candidate state | Version/regression comparison | Configured threshold and matched persisted reports | Personality history comparison → graph/list | Connected; only comparable real scores are compared. |
| Scenario-category scores | Scenario performance | Saved scored diagnostic results grouped by scenario category | Report/history → chart | Connected; empty when no scenarios are scored. |
| Severity counts by severity and run/date | Diagnostic severity history | Persisted finding severities | Diagnostic sidecars → history API → chart | Connected; counts share a consistent scale. |
| Evaluator confidence and scenario coverage | Confidence and coverage | Persisted evaluator confidence and targeted/evaluated counts | Diagnostic report/history → graph | Connected; confidence is labeled uncalibrated and unavailable when absent. |
| Finding status/class/dimension/scenario/severity, observed/expected text, explanation, score/confidence, evidence turn/request/quote, factors/recommendations | Personality evidence details | Saved deterministic findings and validated evaluator evidence references | Diagnostic sidecar/history API → expandable evidence panel | Connected; hidden reasoning and redacted sensitive values are not exposed. |
| Selected question, all request IDs, timeline timestamps/stages/status/details, final response | Personality Trace | Question-scoped request traces and actual saved response | Run detail API → trace selector/timeline/copy action | Connected; multiple-turn requests remain individually identifiable. |
| Failed/interrupted test ID/category/status/error/terminal request ID | Errors / Diagnostics | Persisted question status/error/request association | Run detail API → error list | Fixed; final request ID is preferred for multi-turn failures. |
| Start, pause, resume, next, stop, run again, clear results | Benchmark controls | Existing benchmark manager APIs and actions | Existing endpoints → frontend controls | Connected controls; not data metrics. |

### Datapoint audit findings and changes in this pass

- **43 grouped data bindings** were audited in the matrix above, plus one
  separate control-actions row. Each data row
  is one binding family; where a row lists several values, each named value was
  traced individually. Repeated displays of the same measurement are counted
  once. This count excludes static labels, button actions, and the many
  repeated per-question/per-run instances.
- **Existing correctly connected:** 33 binding families.
- **Existing mappings repaired:** 9 binding families: multi-turn terminal
  request IDs, TTFT, token totals,
  throughput, per-turn request-event association, terminal request ID,
  request-scoped tool calls/availability, trace-derived metrics in
  Watchdog/personality diagnostics, and the accessible processed-count label.
- **Missing datapoints added:** 0. The needed generation fields already existed
  in the actual request trace; they were not propagated to benchmark question
  metrics.
- **Unavailable:** 1 whole binding family (Watchdog personality trait scores;
  the standard scorer does not emit them). Individual values also remain
  unavailable when configured generation/context-window metrics are not
  captured, the non-streaming path emits no TTFT event, model token telemetry
  is absent, or legacy tool records cannot establish a real zero. Those cases
  are described in their respective table rows and are not counted as missing
  datapoints.
- **Targeted regression cases added or updated:** 9 across manager, Watchdog,
  personality diagnostics, API detail serialization, and frontend mapping. The
  API TestClient case is present but could not execute in this environment.
- **Unverified due to environment:** live HTTP API/browser rendering could not
  be exercised because the environment lacks Jinja2 and pytest. Backend manager
  behavior, serialization, and client source mappings were checked by targeted
  tests and syntax checks instead.

## Screenshot-driven Personality Diagnostics audit

The supplied screenshots show a selected run with no dimension scores, an empty
trend plot that still drew axes and all selected legends, no same-suite score
comparison, no scored scenario categories, and no evaluator confidence or
coverage. The severity bars contain actual saved deterministic findings; those
are separate from the missing model-judge scores.

| Screenshot region | Source of truth | What was wrong | Repair / remaining constraint |
|---|---|---|---|
| Dimension cards | Saved run question `target_dimensions`, contract dimensions, diagnostic sidecar | Personality-flavored legacy suite questions did not declare target dimensions. Evaluation correctly generated no scores, while the cards all said “Not evaluated,” obscuring that they were ineligible. | History API now returns redacted eligibility counts from the saved run snapshot. Cards say “Not targeted” or “Not evaluated” according to actual target metadata, and show target counts when available. |
| Evaluate control / empty report | Saved run status and target counts | An evaluation of a run with zero eligible scenarios could produce a `not_evaluated` report, but the UI offered Evaluate again and its generic non-completed warning implied evaluator failure. | Evaluation is disabled when there are no targets. The UI reports that fact and offers to launch the existing versioned personality suite through the existing benchmark start API and normal CYN-X request pathway. |
| Personality trend graph | Persisted diagnostic sidecars summarized by `PersonalityDiagnosticsService.history()` | For historical runs with null values in every selected dimension, the frontend drew axes, every legend and dates without any data marks. | It now renders a true empty state unless at least one real finite score exists. Missing scores remain missing, never zero. Date ticks are limited to three positions. |
| Version and dimension comparisons | Same-suite saved scored dimensions | The screenshot's no-comparison states are accurate when no matched scored baseline exists. | Kept honest empty states; comparisons are populated only from real comparable runs. |
| Scenario performance | Saved scored scenario categories | No judge scores meant no categories could be calculated. | Kept empty state; it fills only from saved evaluator scores. |
| Diagnostic severity history | Saved finding severity counts per report | Bars were individually normalized to 100%, making different finding totals look equally large. | Bars now share a run-to-run scale and show actual finding totals; severity segments remain count-proportional. |
| Evaluator confidence and coverage | Saved evaluator self-reports and targeted/evaluated scenario counts | With no target cases, “Coverage not recorded” did not distinguish zero eligible scenarios from absent legacy telemetry. | Chart now distinguishes no targeted scenarios from coverage not recorded. Confidence remains unavailable unless actual scored evaluator records exist. |
| Scenario coverage | `benchmark/suites/personality-diagnostics-v1.json` and personality contract | The versioned suite targeted 12 of 13 contract dimensions; voice identity had no scenario coverage. | Scenario library is versioned to 1.1.0 and its tone-transition scenario now explicitly evaluates voice identity. All 13 contract dimensions are targeted. Existing historical runs are not rewritten. |

The workspace supplied for this audit has no saved `benchmark/results/dx_runs`
records. Therefore the screenshot's exact run IDs and report payloads could not
be matched to local persisted records. The screenshots plus source inspection
establish the empty-data rendering path, but live API values and a rendered
browser screenshot could not be verified in this environment. Launching the
versioned suite creates real run data; scores still require the configured local
Ollama evaluator and are not fabricated when it is unavailable.
