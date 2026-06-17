@echo off
REM PromptForge - Windows Startup Script

echo.
echo ========================================
echo    PromptForge - LLM Penetration Testing
echo ========================================
echo.

REM Check if .env exists
if not exist .env (
    echo [!] .env file not found
    echo [*] Copying .env.example to .env
    copy .env.example .env
    echo [!] Please fill in your API keys in .env file
    pause
)

REM Start engine in a new window (http://localhost:8000)
echo [*] Starting engine (http://localhost:8000)...
start "PromptForge Engine" cmd /k "python server.py"

REM Wait a moment for the engine to start
timeout /t 2 /nobreak >nul

REM Start dashboard in a new window (http://localhost:8050)
echo [*] Starting dashboard (http://localhost:8050)...
start "PromptForge Dashboard" cmd /k "python -m uvicorn dashboard.app:app --port 8050"

echo.
echo ========================================
echo [+] PromptForge is running!
echo.
echo Engine:    http://localhost:8000
echo Dashboard: http://localhost:8050
echo API Docs:  http://localhost:8000/docs
echo.
echo [*] Close the windows when you're done
echo ========================================
echo.
pause
