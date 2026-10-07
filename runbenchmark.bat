@echo off
setlocal

cd /d C:\Users\nickk\Documents\CYNX-AI

echo Setting CYN-X personality architecture to v2...
set CYNX_PERSONALITY_ARCH=v2

REM 1. Archive previous run
REM 2. CLEANER
REM 3. RUNNER
REM 4. ANALYZER
REM 5. VISUALIZER

python -m benchmark.cleaner --execute
if errorlevel 1 exit /b %errorlevel%

python -m benchmark.runner --suite cyn-voice
if errorlevel 1 exit /b %errorlevel%

python -m benchmark.analyzer
if errorlevel 1 exit /b %errorlevel%

python -m benchmark.visualize
if errorlevel 1 exit /b %errorlevel%

pause