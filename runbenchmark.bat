
@echo off
setlocal

cd /d C:\Users\nickk\Documents\CYNX-AI

echo.
echo ==========================================
echo CYN-X Benchmark Pipeline
echo ==========================================
echo.

set CYNX_PERSONALITY_ARCH=v2

REM ============================================================
REM CONFIGURATION
REM ============================================================

set "ACTIVE_OUTPUT=benchmark\results"
set "ARCHIVE_ROOT=%USERPROFILE%\Documents\cyn-x-benchmarks"

REM ============================================================
REM CREATE TIMESTAMP
REM ============================================================

for /f "tokens=1-3 delims=/ " %%a in ("%date%") do (
    set "RUN_DATE=%%c-%%a-%%b"
)

for /f "tokens=1-2 delims=:." %%a in ("%time%") do (
    set "RUN_TIME=%%a%%b"
)

REM Remove spaces from the hour when Windows reports one-digit hours.
set "RUN_TIME=%RUN_TIME: =0%"

set "RUN_FOLDER=%ARCHIVE_ROOT%\%RUN_DATE%_%RUN_TIME%"

echo Run archive:
echo %RUN_FOLDER%
echo.

REM ============================================================
REM 1. ARCHIVE PREVIOUS RUN
REM ============================================================

if exist "%ACTIVE_OUTPUT%" (
    echo [1/5] Archiving previous benchmark output...

    if not exist "%ARCHIVE_ROOT%" (
        mkdir "%ARCHIVE_ROOT%"
    )

    mkdir "%RUN_FOLDER%"

    xcopy "%ACTIVE_OUTPUT%\*" "%RUN_FOLDER%\" /E /I /Y >nul

    if errorlevel 1 (
        echo ERROR: Failed to archive previous benchmark output.
        exit /b 1
    )

    echo Previous run saved.
) else (
    echo [1/5] No previous benchmark output to archive.
)

echo.

REM ============================================================
REM 2. CLEANER
REM ============================================================

echo [2/5] Cleaning benchmark output...

python -m benchmark.cleaner --execute

if errorlevel 1 (
    echo ERROR: Benchmark cleaner failed.
    exit /b %errorlevel%
)

echo Cleaner complete.
echo.

REM ============================================================
REM 3. RUNNER
REM ============================================================

echo [3/5] Running CYN-X voice benchmark...

python -m benchmark.runner --suite cyn-voice

if errorlevel 1 (
    echo ERROR: Benchmark runner failed.
    exit /b %errorlevel%
)

echo Runner complete.
echo.

REM ============================================================
REM 4. ANALYZER
REM ============================================================

echo [4/5] Analyzing benchmark results...

python -m benchmark.analyzer

if errorlevel 1 (
    echo ERROR: Benchmark analyzer failed.
    exit /b %errorlevel%
)

echo Analyzer complete.
echo.

REM ============================================================
REM 5. VISUALIZER
REM ============================================================

echo [5/5] Generating benchmark visualizations...

python -m benchmark.visualize

if errorlevel 1 (
    echo ERROR: Benchmark visualizer failed.
    exit /b %errorlevel%
)

echo Visualizer complete.
echo.

REM ============================================================
REM COMPLETE
REM ============================================================

echo ==========================================
echo CYN-X BENCHMARK COMPLETE
echo ==========================================
echo.
echo Current results:
echo %ACTIVE_OUTPUT%
echo.
echo Previous run archived at:
echo %RUN_FOLDER%
echo.

pause
