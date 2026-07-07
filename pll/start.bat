@echo off
chcp 65001 >nul
title PLL Agentic IDE Launcher
echo ===============================================
echo      LANCEUR PLL AGENTIC IDE (MODE DEV)
echo ===============================================
echo.

:: 1. Démarrer le serveur backend FastAPI en tâche de fond (minimisé)
echo [..] Démarrage du serveur backend (FastAPI)...
start "PLL Backend Server" /min cmd /c "call serveur.bat"

:: 2. Attendre 2 secondes pour laisser le serveur s'initialiser
timeout /t 2 /nobreak >nul

:: 3. Démarrer l'application de bureau Tauri
echo [..] Démarrage de l'application de bureau Tauri...
call npx @tauri-apps/cli dev

echo.
echo ===============================================
echo   IDE arrêté. Fermeture du lanceur.
echo ===============================================
pause
