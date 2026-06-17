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

REM Start backend in a new window
echo [*] Starting backend server (http://localhost:8000)...
start "PromptForge Backend" cmd /k "python server.py"

REM Wait a moment for backend to start
timeout /t 2 /nobreak

REM Start frontend in a new window
echo [*] Starting dashboard (http://localhost:3000)...
cd dashboard
echo [*] Installing dependencies...
call npm install
echo [*] Starting dev server...
start "PromptForge Dashboard" cmd /k "npm run dev"
cd ..

echo.
echo ========================================
echo [+] PromptForge is running!
echo.
echo Backend:  http://localhost:8000
echo Dashboard: http://localhost:3000
echo API Docs: http://localhost:8000/docs
echo.
echo [*] Close the windows when you're done
echo ========================================
echo.
pause
