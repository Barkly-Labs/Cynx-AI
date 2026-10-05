@echo off
cd /d "C:\Users\nickk\Documents\CYNX-AI\moddelfiles"

echo Setting CYN-X personality architecture to v2...
set CYNX_PERSONALITY_ARCH=v2

echo Creating CYN-X model...
ollama create cyn-x -f Modelfile

if errorlevel 1 (
    echo.
    echo ERROR: Ollama model creation failed.
    pause
    exit /b 1
)

cd /d "C:\Users\nickk\Documents\CYNX-AI"

echo.
echo Starting CYN-X web interface...
uvicorn interfaces.web.app:app

pause