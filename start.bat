@echo off
rem Starts the Sprinto AI backend (port 8000) and dashboard (port 5173) in their own windows.
cd /d "%~dp0"
start "Sprinto API" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000"
start "Sprinto Dashboard" cmd /k "cd frontend && npm run dev"
timeout /t 6 >nul
start http://localhost:5173
