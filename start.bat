@echo off
title Enterprise RFP Solver
echo ==========================================
echo   Starting Enterprise RFP Application...
echo ==========================================

:: 1. Start backend in the background of THIS window
echo [1/3] Starting Python Backend...
start /B cmd /c "cd backend && ..\venv\Scripts\activate && python -m uvicorn app.main:app --reload"
:: 2. Start frontend in the background of THIS window
echo [2/3] Starting React Frontend...
start /B cmd /c "cd frontend && npm run dev"

:: 3. Wait and open browser
echo [3/3] Waiting for servers to initialize (6s)...
start http://localhost:8080
echo ==========================================
echo  Ready! The tool opened in your browser.
echo ==========================================
echo.
echo  TO CLOSE THE TOOL:
echo Just close this black window with the "X" at the top right,
echo or press any key in here.
echo.
pause

:: If the user presses a key instead of X, make sure everything is closed
echo Shutting down...
taskkill /F /IM node.exe /T >nul 2>&1
taskkill /F /IM python.exe /T >nul 2>&1