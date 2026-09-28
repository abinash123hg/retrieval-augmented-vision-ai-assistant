@echo off
REM DocuLens - start everything with one command.
REM Double-click this file, or run "start.bat" in a VS Code terminal.

cd /d "%~dp0"

echo [1/3] Checking Ollama...
curl -s --max-time 3 http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo       Ollama is not running. Starting it now...
    start "Ollama" cmd /k "ollama serve"
    timeout /t 5 /nobreak >nul
) else (
    echo       Ollama is running.
)

echo [2/3] Starting backend on http://127.0.0.1:8000 ...
start "DocuLens Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

echo [3/3] Starting frontend on http://localhost:5173 ...
start "DocuLens Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ============================================
echo  DocuLens is starting in two new windows:
echo    App:      http://localhost:5173
echo    Backend:  http://127.0.0.1:8000
echo    API docs: http://127.0.0.1:8000/docs
echo  Close those windows to stop the app.
echo ============================================
