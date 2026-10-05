[CmdletBinding()]
param(
    [ValidateSet('Menu','Tests','Benchmark','Regression','Full','Compare','View','Configure')]
    [string]$Mode = 'Menu',
    [ValidatePattern('^(All|[1-9][0-9]*)$')]
    [string]$Questions = 'All',
    [string[]]$Category,
    [string[]]$Suite,
    [string]$Baseline,
    [string]$Output = '.\results',
    [string]$Python = 'python',
    [string]$Model,
    [double]$MaxPassRateDropPct = 3.0,
    [double]$MaxScoreDrop = 0.25,
    [double]$MaxLatencyIncreasePct = 25.0,
    [double]$MaxToolCallsPerQuestionIncrease = 0.50,
    [double]$MaxSearchQuestionPctIncrease = 15.0,
    [int]$MaxAdditionalTimeouts = 0,
    [int]$MaxAdditionalCrashes = 0,
    [int]$MaxAdditionalResourceErrors = 0,
    [switch]$MarkBaseline,
    [switch]$ReplaceBaseline,
    [switch]$NoColor
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$EXIT_SUCCESS = 0
$EXIT_TEST_FAILURE = 1
$EXIT_REGRESSION = 2
$EXIT_ENVIRONMENT = 3
$EXIT_RUNNER = 4
$script:FinalExitCode = $EXIT_SUCCESS
$script:RunDir = $null
$script:LogFile = $null
$script:ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:Cancelled = $false

function Write-Status {
    param([ValidateSet('PASS','FAIL','REGRESSION','WARNING','INFO')][string]$Status,[string]$Message)
    $prefix = "[$Status]"
    if ($NoColor) { Write-Host "$prefix $Message"; return }
    $color = switch ($Status) { 'PASS' {'Green'} 'FAIL' {'Red'} 'REGRESSION' {'Magenta'} 'WARNING' {'Yellow'} default {'Cyan'} }
    Write-Host $prefix -ForegroundColor $color -NoNewline
    Write-Host " $Message"
}

function Write-Log {
    param([string]$Message)
    if ($script:LogFile) { Add-Content -LiteralPath $script:LogFile -Value $Message -Encoding UTF8 }
}

function Save-Json {
    param([Parameter(Mandatory)]$Object,[Parameter(Mandatory)][string]$Path,[int]$Depth=20)
    $Object | ConvertTo-Json -Depth $Depth | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Resolve-ProjectPath {
    param([string]$Path)
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot $Path))
}

function New-RunDirectory {
    $root = Resolve-ProjectPath $Output
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    $stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
    $candidate = Join-Path $root $stamp
    $i = 1
    while (Test-Path -LiteralPath $candidate) { $candidate = Join-Path $root ("{0}_{1}" -f $stamp,$i); $i++ }
    New-Item -ItemType Directory -Path $candidate | Out-Null
    $script:RunDir = $candidate
    $script:LogFile = Join-Path $candidate 'console.log'
    "CYN-X test pipeline started $(Get-Date -Format o)" | Set-Content -LiteralPath $script:LogFile -Encoding UTF8
    return $candidate
}

function Get-CommandInfoSafe {
    param([string]$Name,[string[]]$Arguments=@())
    try {
        $cmd = Get-Command $Name -ErrorAction Stop
        $text = & $cmd.Source @Arguments 2>&1 | Out-String
        return [ordered]@{ available=$true; path=$cmd.Source; output=$text.Trim(); exit_code=$LASTEXITCODE }
    } catch { return [ordered]@{ available=$false; path=$null; output=$_.Exception.Message; exit_code=$null } }
}

function Get-CynxModelName {
    if ($Model) { return $Model }
    if ($env:MODEL_NAME) { return $env:MODEL_NAME }
    return 'cyn-x:latest'
}

function Get-EnvironmentInfo {
    param([switch]$RequireOllama)
    $pythonInfo = Get-CommandInfoSafe $Python @('--version')
    $ollamaInfo = Get-CommandInfoSafe 'ollama' @('--version')
    $modelName = Get-CynxModelName
    $cpu = @(); $gpu = @(); $memoryBytes = $null
    try { $cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors) } catch {}
    try { $gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion) } catch {}
    try { $memoryBytes = [int64](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory } catch {}
    $modelList = $null; $modelShow = $null
    if ($ollamaInfo.available) {
        try { $modelList = (& ollama list 2>&1 | Out-String).Trim() } catch { $modelList = $_.Exception.Message }
        try { $modelShow = (& ollama show $modelName --modelfile 2>&1 | Out-String).Trim() } catch { $modelShow = $_.Exception.Message }
    }
    $info = [ordered]@{
        timestamp=(Get-Date).ToUniversalTime().ToString('o'); project_root=$script:ProjectRoot
        powershell=[ordered]@{ version=$PSVersionTable.PSVersion.ToString(); edition=$PSVersionTable.PSEdition }
        python=$pythonInfo; ollama=$ollamaInfo; model=[ordered]@{ name=$modelName; list=$modelList; modelfile=$modelShow }
        cpu=$cpu; gpu=$gpu; total_physical_memory_bytes=$memoryBytes
    }
    if ($RequireOllama -and -not $ollamaInfo.available) { throw "Ollama is required for benchmark modes but was not found. Start/install Ollama and ensure 'ollama' is on PATH." }
    if (-not $pythonInfo.available) { throw "Python command '$Python' was not found or failed. Use -Python to select the interpreter." }
    return $info
}

function Invoke-CapturedProcess {
    param([Parameter(Mandatory)][string]$FilePath,[string[]]$Arguments=@(),[string]$WorkingDirectory=$script:ProjectRoot)
    $started = Get-Date
    Write-Log ("> {0} {1}" -f $FilePath,($Arguments -join ' '))
    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments 2>&1 | ForEach-Object { $line = $_.ToString(); Write-Host $line; Write-Log $line }
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
    } catch {
        Write-Log $_.Exception.ToString(); throw
    } finally { Pop-Location }
    $ended = Get-Date
    return [ordered]@{ command=$FilePath; arguments=$Arguments; exit_code=[int]$code; started=$started.ToUniversalTime().ToString('o'); ended=$ended.ToUniversalTime().ToString('o'); duration_seconds=[math]::Round(($ended-$started).TotalSeconds,3) }
}

function Get-BenchmarkCatalog {
    $suiteDir = Join-Path $script:ProjectRoot 'benchmark\suites'
    if (-not (Test-Path $suiteDir)) { throw "Benchmark suite directory not found: $suiteDir" }
    $items = @()
    foreach ($file in Get-ChildItem -LiteralPath $suiteDir -Filter '*.json' | Sort-Object Name) {
        $data = Get-Content -Raw -LiteralPath $file.FullName | ConvertFrom-Json
        $tests = if ($data -is [array]) { @($data) } elseif ($data.tests) { @($data.tests) } elseif ($data.questions) { @($data.questions) } else { @() }
        foreach ($t in $tests) { $items += [pscustomobject]@{ suite=[IO.Path]::GetFileNameWithoutExtension($file.Name); category=[string]$t.category; test_id=[string]$t.test_id } }
    }
    return @($items)
}

function Select-BenchmarkCatalog {
    param([object[]]$Catalog)
    $selected = @($Catalog)
    if ($Suite) { $selected = @($selected | Where-Object { $Suite -contains $_.suite }) }
    if ($Category) { $selected = @($selected | Where-Object { $Category -contains $_.category }) }
    return $selected
}

function Get-NewestBenchmarkRaw {
    param([datetime]$After)
    $raw = Join-Path $script:ProjectRoot 'benchmark\results\raw'
    if (-not (Test-Path $raw)) { return $null }
    return Get-ChildItem -LiteralPath $raw -Filter 'benchmark_*.json' | Where-Object LastWriteTime -ge $After | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Get-ToolTraceMetrics {
    param([object[]]$Results)
    $toolCalls=0; $searchCalls=0; $questionsWithTools=0; $searchQuestions=0; $unnecessary=0; $expectationComparable=0
    foreach ($r in $Results) {
        $trace = $r.tool_test
        if (-not $trace) { continue }
        $called = $false; $name = $null; $expected = $null
        if ($trace.tool_called -eq $true) { $called=$true }
        if ($trace.executed_tool) { $name=[string]$trace.executed_tool; $called=$true }
        elseif ($trace.detected_tool -and [string]$trace.detected_tool -ne 'none') { $name=[string]$trace.detected_tool; $called=$true }
        elseif ($trace.tool_name) { $name=[string]$trace.tool_name; $called=$true }
        if ($trace.expected_tool) { $expected=[string]$trace.expected_tool }
        if ($called) { $toolCalls++; $questionsWithTools++ }
        $isSearch = $name -match '(?i)search|web'
        if ($isSearch) { $searchCalls++; $searchQuestions++ }
        if ($expected) {
            $expectationComparable++
            if ($isSearch -and $expected -notmatch '(?i)search|web') { $unnecessary++ }
        }
    }
    $n=[math]::Max(1,$Results.Count)
    return [ordered]@{
        total_tool_calls=$toolCalls; search_calls=$searchCalls
        tool_calls_per_question=[math]::Round($toolCalls/$n,4)
        percentage_questions_requiring_tools=[math]::Round(100*$questionsWithTools/$n,2)
        percentage_questions_using_search=[math]::Round(100*$searchQuestions/$n,2)
        unnecessary_search_calls=if($expectationComparable -gt 0){$unnecessary}else{$null}
        unnecessary_search_metric_available=($expectationComparable -gt 0)
        expectation_comparable_questions=$expectationComparable
    }
}

function Get-BenchmarkMetrics {
    param([object[]]$Results,[int]$Requested,[int]$Available,[double]$Duration,[int]$ProcessExitCode)
    $actual=$Results.Count
    $failed=[math]::Max(0,[math]::Min($Requested,$Available)-$actual)
    $scores=@($Results | ForEach-Object { if ($_.scores -and $null -ne $_.scores.overall) {[double]$_.scores.overall} })
    $lat=@($Results | ForEach-Object { if ($_.metrics -and $null -ne $_.metrics.response_time_seconds) {[double]$_.metrics.response_time_seconds} elseif ($null -ne $_.response_time_seconds) {[double]$_.response_time_seconds} })
    $timeouts=@($Results | Where-Object { ($_.runtime.error -match '(?i)timeout') -or ($_.output.response -match '(?i)timed out') }).Count
    $crashes=@($Results | Where-Object { $_.runtime.failed -eq $true }).Count + $(if($ProcessExitCode -ne 0){1}else{0})
    $resourceErrors=@($Results | Where-Object { $_.runtime.error -match '(?i)memory|resource|cuda|gpu|out of memory|oom' }).Count
    $tools=Get-ToolTraceMetrics $Results
    return [ordered]@{
        requested_question_count=$Requested; available_question_count=$Available; actual_question_count=$actual
        questions_passed=$actual; questions_failed=$failed; questions_skipped=[math]::Max(0,$Available-[math]::Min($Requested,$Available))
        execution_pass_rate_pct=if(($actual+$failed)-gt 0){[math]::Round(100*$actual/($actual+$failed),2)}else{0}
        benchmark_score=if($scores.Count){[math]::Round(($scores|Measure-Object -Average).Average,4)}else{$null}
        average_latency_seconds=if($lat.Count){[math]::Round(($lat|Measure-Object -Average).Average,4)}else{$null}
        timeout_count=$timeouts; crash_count=$crashes; model_resource_errors=$resourceErrors; execution_time_seconds=$Duration
        tool_metrics=$tools
        memory_resource_metrics=$null
        memory_resource_metrics_note='Not emitted by the existing benchmark result schema; environment memory is recorded separately.'
    }
}

function Invoke-BenchmarkRun {
    $catalog=Get-BenchmarkCatalog; $selected=Select-BenchmarkCatalog $catalog
    $available=$selected.Count
    if ($available -eq 0) { throw "No benchmark prompts match the selected suite/category filters." }
    $requested = if ($Questions -eq 'All') { $available } else { [int]$Questions }
    $limit=[math]::Min($requested,$available)
    if ($requested -gt $available) { Write-Status WARNING "Requested $requested questions, but only $available match. Running $available." }

    # Existing runner already supports categories internally, but its CLI does not expose them.
    # Use a tiny import bridge so the canonical datasets and Python benchmark implementation remain unchanged.
    $catsJson = if($Category){$Category|ConvertTo-Json -Compress}else{'null'}
    $suitesJson = if($Suite){$Suite|ConvertTo-Json -Compress}else{'null'}
    $env:CYNX_RUNNER_CATEGORIES=$catsJson; $env:CYNX_RUNNER_SUITES=$suitesJson; $env:CYNX_RUNNER_LIMIT=[string]$limit
    if ($Model) { $env:MODEL_NAME=$Model }
    $bridge = @'
import json, os, sys
from benchmark.runner import create_cynx_engine, run_benchmark
cats=json.loads(os.environ.get("CYNX_RUNNER_CATEGORIES","null"))
suites=json.loads(os.environ.get("CYNX_RUNNER_SUITES","null"))
limit=int(os.environ["CYNX_RUNNER_LIMIT"])
try:
    engine=create_cynx_engine()
    results=run_benchmark(engine, limit=limit, categories=cats, suites=suites)
    sys.exit(0 if len(results)==limit else 1)
except KeyboardInterrupt:
    print("Benchmark cancelled by user.", file=sys.stderr); sys.exit(130)
except Exception as exc:
    print(f"Benchmark runner error: {exc}", file=sys.stderr); sys.exit(4)
'@
    $started=Get-Date
    $proc=Invoke-CapturedProcess $Python @('-c',$bridge)
    $raw=Get-NewestBenchmarkRaw $started
    $results=@()
    if ($raw) { $parsed=Get-Content -Raw -LiteralPath $raw.FullName | ConvertFrom-Json; $results=@($parsed) }
    $metrics=Get-BenchmarkMetrics $results $requested $available $proc.duration_seconds $proc.exit_code
    $artifact=[ordered]@{ schema_version='1.0'; kind='benchmark'; selection=[ordered]@{questions=$Questions; categories=$Category; suites=$Suite}; source_result=if($raw){$raw.FullName}else{$null}; process=$proc; metrics=$metrics; results=$results }
    Save-Json $artifact (Join-Path $script:RunDir 'benchmark.json') 30
    if ($proc.exit_code -ne 0 -or $metrics.questions_failed -gt 0) { Write-Status FAIL "Benchmark completed with $($metrics.questions_failed) failed/missing prompt result(s)."; $script:FinalExitCode=[math]::Max($script:FinalExitCode,$EXIT_TEST_FAILURE) }
    else { Write-Status PASS "Benchmark: $($metrics.actual_question_count)/$limit prompts completed; score=$($metrics.benchmark_score); avg latency=$($metrics.average_latency_seconds)s." }
    return $artifact
}

function Invoke-TestSuite {
    $started=Get-Date
    $proc=Invoke-CapturedProcess $Python @('-m','pytest','-q')
    $artifact=[ordered]@{ schema_version='1.0'; kind='tests'; process=$proc; passed=($proc.exit_code -eq 0) }
    Save-Json $artifact (Join-Path $script:RunDir 'tests.json')
    if ($proc.exit_code -eq 0) { Write-Status PASS "Unit/integration tests passed." } else { Write-Status FAIL "pytest exited with code $($proc.exit_code)."; $script:FinalExitCode=[math]::Max($script:FinalExitCode,$EXIT_TEST_FAILURE) }
    return $artifact
}

function Get-BaselineDocument {
    param([string]$Path)
    if (-not $Path) {
        $default=Join-Path (Resolve-ProjectPath $Output) 'baseline.json'
        if (Test-Path $default) { $Path=$default } else { throw "No baseline selected. Use -Baseline <path> or mark a successful run with -MarkBaseline." }
    }
    $resolved=Resolve-ProjectPath $Path
    if (-not (Test-Path $resolved)) { throw "Baseline not found: $resolved" }
    return Get-Content -Raw -LiteralPath $resolved | ConvertFrom-Json
}

function Add-ComparisonRow {
    param([System.Collections.ArrayList]$Rows,[string]$Metric,$BaselineValue,$CurrentValue,[double]$Difference,[double]$Threshold,[ValidateSet('higher_bad','lower_bad')][string]$Direction)
    $regressed = if($Direction -eq 'higher_bad'){ $Difference -gt $Threshold } else { $Difference -lt (-1*$Threshold) }
    $status=if($regressed){'REGRESSION'}elseif([math]::Abs($Difference) -gt (0.8*[math]::Abs($Threshold))){'WARNING'}else{'PASS'}
    [void]$Rows.Add([ordered]@{metric=$Metric; baseline=$BaselineValue; current=$CurrentValue; difference=[math]::Round($Difference,4); threshold=$Threshold; status=$status})
}

function Compare-Benchmark {
    param($CurrentBenchmark)
    $baseDoc=Get-BaselineDocument $Baseline
    $base = if($baseDoc.benchmark){$baseDoc.benchmark.metrics}elseif($baseDoc.metrics){$baseDoc.metrics}else{throw 'Baseline does not contain benchmark metrics.'}
    $cur=$CurrentBenchmark.metrics; $rows=New-Object System.Collections.ArrayList
    Add-ComparisonRow $rows 'Execution pass rate (percentage points)' $base.execution_pass_rate_pct $cur.execution_pass_rate_pct ([double]$cur.execution_pass_rate_pct-[double]$base.execution_pass_rate_pct) $MaxPassRateDropPct 'lower_bad'
    if($null-ne$base.benchmark_score -and $null-ne$cur.benchmark_score){Add-ComparisonRow $rows 'Benchmark score' $base.benchmark_score $cur.benchmark_score ([double]$cur.benchmark_score-[double]$base.benchmark_score) $MaxScoreDrop 'lower_bad'}
    if($base.average_latency_seconds -gt 0 -and $null-ne$cur.average_latency_seconds){$d=100*([double]$cur.average_latency_seconds-[double]$base.average_latency_seconds)/[double]$base.average_latency_seconds;Add-ComparisonRow $rows 'Average latency (%)' $base.average_latency_seconds $cur.average_latency_seconds $d $MaxLatencyIncreasePct 'higher_bad'}
    Add-ComparisonRow $rows 'Tool calls per question' $base.tool_metrics.tool_calls_per_question $cur.tool_metrics.tool_calls_per_question ([double]$cur.tool_metrics.tool_calls_per_question-[double]$base.tool_metrics.tool_calls_per_question) $MaxToolCallsPerQuestionIncrease 'higher_bad'
    Add-ComparisonRow $rows 'Questions using search (percentage points)' $base.tool_metrics.percentage_questions_using_search $cur.tool_metrics.percentage_questions_using_search ([double]$cur.tool_metrics.percentage_questions_using_search-[double]$base.tool_metrics.percentage_questions_using_search) $MaxSearchQuestionPctIncrease 'higher_bad'
    Add-ComparisonRow $rows 'Timeout count' $base.timeout_count $cur.timeout_count ([double]$cur.timeout_count-[double]$base.timeout_count) $MaxAdditionalTimeouts 'higher_bad'
    Add-ComparisonRow $rows 'Crash count' $base.crash_count $cur.crash_count ([double]$cur.crash_count-[double]$base.crash_count) $MaxAdditionalCrashes 'higher_bad'
    Add-ComparisonRow $rows 'Model/resource errors' $base.model_resource_errors $cur.model_resource_errors ([double]$cur.model_resource_errors-[double]$base.model_resource_errors) $MaxAdditionalResourceErrors 'higher_bad'
    $reg=@($rows|Where-Object status -eq 'REGRESSION'); $warn=@($rows|Where-Object status -eq 'WARNING')
    $comparison=[ordered]@{status=if($reg.Count){'REGRESSION'}elseif($warn.Count){'WARNING'}else{'PASS'}; thresholds=[ordered]@{max_pass_rate_drop_percentage_points=$MaxPassRateDropPct;max_score_drop=$MaxScoreDrop;max_latency_increase_pct=$MaxLatencyIncreasePct;max_tool_calls_per_question_increase=$MaxToolCallsPerQuestionIncrease;max_search_question_pct_increase=$MaxSearchQuestionPctIncrease;max_additional_timeouts=$MaxAdditionalTimeouts;max_additional_crashes=$MaxAdditionalCrashes;max_additional_resource_errors=$MaxAdditionalResourceErrors}; metrics=$rows }
    Save-Json $comparison (Join-Path $script:RunDir 'regression.json')
    foreach($r in $rows){Write-Status $r.status ("{0}: baseline={1}, current={2}, difference={3}, threshold={4}" -f $r.metric,$r.baseline,$r.current,$r.difference,$r.threshold)}
    if($reg.Count){$script:FinalExitCode=[math]::Max($script:FinalExitCode,$EXIT_REGRESSION)}
    return $comparison
}

function Save-RunSummary {
    param($Environment,$Tests,$Benchmark,$Regression)
    $status=if($script:FinalExitCode -eq 0){'PASS'}elseif($script:FinalExitCode -eq 2){'REGRESSION'}elseif($script:FinalExitCode -eq 1){'FAIL'}else{'ERROR'}
    $summary=[ordered]@{schema_version='1.0';status=$status;exit_code=$script:FinalExitCode;timestamp=(Get-Date).ToUniversalTime().ToString('o');run_directory=$script:RunDir;requested=[ordered]@{mode=$Mode;questions=$Questions;categories=$Category;suites=$Suite;baseline=$Baseline};tests=$Tests;benchmark=if($Benchmark){$Benchmark.metrics}else{$null};regression=$Regression;environment_file='environment.json';exit_codes=[ordered]@{'0'='success';'1'='test/benchmark failure';'2'='regression detected';'3'='configuration/environment failure';'4'='runner error'}}
    Save-Json $summary (Join-Path $script:RunDir 'summary.json') 25
    $txt=@("CYN-X Test Pipeline","Status: $status","Exit code: $($script:FinalExitCode)","Run: $($script:RunDir)")
    if($Benchmark){$txt += "Questions: requested=$($Benchmark.metrics.requested_question_count) actual=$($Benchmark.metrics.actual_question_count) passed=$($Benchmark.metrics.questions_passed) failed=$($Benchmark.metrics.questions_failed) skipped=$($Benchmark.metrics.questions_skipped)";$txt += "Benchmark score: $($Benchmark.metrics.benchmark_score)";$txt += "Average latency: $($Benchmark.metrics.average_latency_seconds)s";$txt += "Tool calls: $($Benchmark.metrics.tool_metrics.total_tool_calls); search calls: $($Benchmark.metrics.tool_metrics.search_calls)"}
    $txt | Set-Content -LiteralPath (Join-Path $script:RunDir 'summary.txt') -Encoding UTF8
    return $summary
}

function Set-BaselineFromRun {
    param($Summary)
    if($script:FinalExitCode -ne 0){Write-Status WARNING 'Baseline was not marked because this run was not successful.';return}
    $target=if($Baseline){Resolve-ProjectPath $Baseline}else{Join-Path (Resolve-ProjectPath $Output) 'baseline.json'}
    if((Test-Path $target)-and -not $ReplaceBaseline){throw "Baseline already exists: $target. Re-run with -ReplaceBaseline for explicit replacement."}
    $parent=Split-Path -Parent $target; New-Item -ItemType Directory -Force -Path $parent|Out-Null
    Copy-Item -LiteralPath (Join-Path $script:RunDir 'summary.json') -Destination $target -Force:$ReplaceBaseline
    Write-Status PASS "Baseline saved to $target"
}

function Show-PreviousResults {
    $root=Resolve-ProjectPath $Output
    if(-not(Test-Path $root)){Write-Status WARNING "No results directory exists: $root";return}
    Get-ChildItem $root -Directory | Sort-Object Name -Descending | Select-Object -First 10 | ForEach-Object { $s=Join-Path $_.FullName 'summary.json'; if(Test-Path $s){$j=Get-Content -Raw $s|ConvertFrom-Json; Write-Host ("{0}  {1}  exit={2}" -f $_.Name,$j.status,$j.exit_code)} }
}

function Show-Configuration {
    $catalog=Get-BenchmarkCatalog
    Write-Host "Benchmark prompts: $($catalog.Count)"
    Write-Host 'Suites:'; $catalog|Group-Object suite|Sort-Object Name|ForEach-Object{Write-Host ("  {0}: {1}" -f $_.Name,$_.Count)}
    Write-Host 'Categories:'; $catalog|Group-Object category|Sort-Object Name|ForEach-Object{Write-Host ("  {0}: {1}" -f $_.Name,$_.Count)}
    Write-Host "`nThreshold policy (all configurable by parameters):"
    Write-Host "  pass-rate drop > $MaxPassRateDropPct percentage points = REGRESSION"
    Write-Host "  benchmark-score drop > $MaxScoreDrop = REGRESSION"
    Write-Host "  latency increase > $MaxLatencyIncreasePct% = REGRESSION"
    Write-Host "  tool calls/question increase > $MaxToolCallsPerQuestionIncrease = REGRESSION"
    Write-Host "  search-question rate increase > $MaxSearchQuestionPctIncrease percentage points = REGRESSION"
    Write-Host "  additional timeouts/crashes/resource errors > $MaxAdditionalTimeouts/$MaxAdditionalCrashes/$MaxAdditionalResourceErrors = REGRESSION"
    Write-Host 'WARNING begins at 80% of a configured threshold.'
}

function Invoke-PipelineMode {
    param([string]$SelectedMode)
    if($SelectedMode -eq 'View'){Show-PreviousResults;return}
    if($SelectedMode -eq 'Configure'){Show-Configuration;return}
    $needsBenchmark=$SelectedMode -in @('Benchmark','Regression','Full','Compare')
    $run=New-RunDirectory
    try {
        $envInfo=Get-EnvironmentInfo -RequireOllama:$needsBenchmark
        Save-Json $envInfo (Join-Path $run 'environment.json') 15
    } catch { Write-Status FAIL $_.Exception.Message; Write-Log $_.Exception.ToString(); $script:FinalExitCode=$EXIT_ENVIRONMENT; Save-RunSummary $null $null $null $null|Out-Null; return }
    $tests=$null;$bench=$null;$reg=$null
    try {
        if($SelectedMode -in @('Tests','Full')){$tests=Invoke-TestSuite}
        if($SelectedMode -in @('Benchmark','Regression','Full')){$bench=Invoke-BenchmarkRun}
        if($SelectedMode -in @('Regression','Full')){$reg=Compare-Benchmark $bench}
        if($SelectedMode -eq 'Compare'){
            $currentPath=Join-Path $run 'benchmark.json'
            throw "Compare mode needs a current benchmark run. Use -Mode Regression to run and compare in one step, or compare saved summary.json files manually."
        }
    } catch [System.Management.Automation.PipelineStoppedException] { $script:Cancelled=$true; Write-Status WARNING 'Cancelled by user.'; $script:FinalExitCode=$EXIT_TEST_FAILURE }
      catch { Write-Status FAIL $_.Exception.Message; Write-Log $_.Exception.ToString(); if($script:FinalExitCode -eq 0){$script:FinalExitCode=$EXIT_RUNNER} }
    $summary=Save-RunSummary $envInfo $tests $bench $reg
    if($MarkBaseline){try{Set-BaselineFromRun $summary}catch{Write-Status FAIL $_.Exception.Message;if($script:FinalExitCode -eq 0){$script:FinalExitCode=$EXIT_RUNNER};Save-RunSummary $envInfo $tests $bench $reg|Out-Null}}
    Write-Status INFO "Results saved to $run"
}

function Show-Menu {
    while($true){
        Write-Host ''; Write-Host 'CYN-X Test Pipeline'; Write-Host ''
        Write-Host '[1] Run unit/integration tests'; Write-Host '[2] Run benchmark'; Write-Host '[3] Run regression benchmark'; Write-Host '[4] Run full pipeline'; Write-Host '[5] Compare against baseline'; Write-Host '[6] View previous results'; Write-Host '[7] Configure test options'; Write-Host '[Q] Quit'; Write-Host ''
        $choice=Read-Host 'Select'
        switch($choice.ToUpperInvariant()){
            '1'{Invoke-PipelineMode 'Tests';return};'2'{Invoke-PipelineMode 'Benchmark';return};'3'{Invoke-PipelineMode 'Regression';return};'4'{Invoke-PipelineMode 'Full';return};
            '5'{Write-Status INFO 'Use Regression to execute a fresh benchmark and compare it to -Baseline.'};'6'{Show-PreviousResults};'7'{Show-Configuration};'Q'{return};default{Write-Status WARNING 'Unknown selection.'}
        }
    }
}

try {
    Set-Location $script:ProjectRoot
    if($Mode -eq 'Menu'){Show-Menu}else{Invoke-PipelineMode $Mode}
} catch { Write-Status FAIL $_.Exception.Message; if($script:FinalExitCode -eq 0){$script:FinalExitCode=$EXIT_RUNNER} }
exit $script:FinalExitCode
