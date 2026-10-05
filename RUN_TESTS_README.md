# CYN-X PowerShell Test Pipeline

`run-tests.ps1` is an orchestration layer over the repository's existing pytest and `benchmark.runner` infrastructure. It does not install dependencies, change Ollama configuration, modify benchmark datasets, or alter CYN-X source code.

## Common commands

```powershell
.\run-tests.ps1
.\run-tests.ps1 -Mode Tests
.\run-tests.ps1 -Mode Benchmark -Questions 25
.\run-tests.ps1 -Mode Benchmark -Questions All -Category SEARCH_ROUTING,TOOL_TRACE
.\run-tests.ps1 -Mode Benchmark -Suite cyn-research -Questions 50
.\run-tests.ps1 -Mode Regression -Questions 132 -Baseline .\results\baseline.json
.\run-tests.ps1 -Mode Full -Questions 132 -Baseline .\results\baseline.json
.\run-tests.ps1 -Mode Benchmark -Questions 25 -MarkBaseline
.\run-tests.ps1 -Mode Benchmark -Questions 25 -MarkBaseline -ReplaceBaseline
```

`-Questions` accepts `All` or a positive integer. If fewer prompts match the suite/category filters, the runner reports the mismatch and records both requested and actual counts.

## Regression thresholds

Defaults are explicit runner policy, not claims about CYN-X's intrinsic quality bar. Override them on the command line:

- `-MaxPassRateDropPct 3` — regression if execution pass rate drops by more than 3 percentage points.
- `-MaxScoreDrop 0.25` — regression if the existing benchmark's average `overall` score drops by more than 0.25.
- `-MaxLatencyIncreasePct 25` — regression if average latency rises by more than 25%.
- `-MaxToolCallsPerQuestionIncrease 0.5` — regression if calls/question rises by more than 0.5.
- `-MaxSearchQuestionPctIncrease 15` — regression if the share of questions using search rises by more than 15 percentage points.
- `-MaxAdditionalTimeouts 0`, `-MaxAdditionalCrashes 0`, `-MaxAdditionalResourceErrors 0` — no additional occurrences by default.

A `WARNING` is emitted when a difference exceeds 80% of a configured threshold. Tool/search metrics are derived only from `tool_test` traces already emitted by the benchmark. Unnecessary-search counts are only populated when an expected tool is recorded; otherwise that metric is explicitly unavailable.

## Results

Each execution creates `results\yyyy-MM-dd_HH-mm-ss\` containing `summary.json`, `summary.txt`, `environment.json`, `console.log`, and, when applicable, `tests.json`, `benchmark.json`, and `regression.json`.

The environment record includes PowerShell/Python/Ollama versions, selected model, `ollama list`, model Modelfile when available, CPU/GPU information, and physical memory. Benchmark modes fail clearly if Ollama is unavailable.

## Baselines

`-MarkBaseline` copies a successful run's `summary.json` to `results\baseline.json` unless `-Baseline` names another target. Existing baselines are never replaced unless `-ReplaceBaseline` is also supplied.

## Exit codes

- `0` success
- `1` test or benchmark failure
- `2` regression detected
- `3` configuration/environment failure
- `4` runner/orchestration error

The existing Python benchmark catches individual prompt failures and omits those failed results. The PowerShell runner detects that by comparing the expected selected count to the raw result count, so those failures cannot silently become PASS.
