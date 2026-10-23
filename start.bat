@echo off
REM DocuLens - start everything with one command.
REM Double-click this file, or run "start.bat" in a VS Code terminal.

cd /d "%~dp0"

echo [1/2] Checking Ollama...
curl -s --max-time 3 http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo       Ollama is not running. Starting it now...
    start "Ollama" cmd /k "ollama serve"
    timeout /t 5 /nobreak >nul
) else (
    echo       Ollama is already running in the background ^(system tray^).
    echo       No separate Ollama terminal is needed - that is expected.
)

echo [2/2] Starting DocuLens on http://127.0.0.1:8000 ...
start "DocuLens" cmd /k "cd /d %~dp0backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

echo.
echo ============================================
echo  DocuLens is starting in a new window:
echo    App:      http://127.0.0.1:8000
echo    API docs: http://127.0.0.1:8000/docs
echo  Close that window to stop the app.
echo ============================================
