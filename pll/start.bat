@echo off
title PLL Agentic IDE Launcher
echo ===============================================
echo      LAUNCHER PLL AGENTIC IDE (DEV MODE)
echo ===============================================
echo.

REM 1. Start FastAPI backend server in background
echo [..] Starting backend server (FastAPI)...
start "PLL Backend Server" /min cmd /c "call serveur.bat"

REM 2. Wait 2 seconds for server initialization
timeout /t 2 /nobreak >nul

REM 3. Start Tauri desktop application
echo [..] Starting Tauri desktop application...
call npx @tauri-apps/cli dev

echo.
echo ===============================================
echo   IDE stopped. Closing launcher.
echo ===============================================
pause
