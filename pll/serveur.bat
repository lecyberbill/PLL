@echo off
chcp 65001 >nul
title PLL Server - Agentic IDE
setlocal enabledelayedexpansion

set SERVER_DIR=%~dp0server
set PORT=8080
set HOST=127.0.0.1

echo.
echo === PLL Agentic IDE Server ===
echo FastAPI + Monaco + DeepSeek + GCA
echo.

:: Navigate to server dir
cd /d "%SERVER_DIR%"
if %ERRORLEVEL% neq 0 (
    echo [ERR] Dossier introuvable: %SERVER_DIR%
    pause
    exit /b 1
)

:: Load .env if present
if exist ".env" (
    echo [..] Chargement .env...
    for /f "usebackq delims=" %%a in (".env") do (
        set "line=%%a"
        if not "!line!"=="" if "!line:~0,1!" neq "#" (
            for /f "tokens=1,* delims==" %%b in ("!line!") do (
                set "%%b=%%c"
            )
        )
    )
    echo [OK]  .env charge
)

:: Check Python
where py >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERR] Python introuvable. Installe Python 3.10+
    pause
    exit /b 1
)

:: Create venv if needed
if not exist ".venv\Scripts\python.exe" (
    echo [..] Creation du venv...
    py -3.13 -m venv .venv 2>nul || py -3.12 -m venv .venv 2>nul || py -3.11 -m venv .venv 2>nul || py -3.10 -m venv .venv 2>nul
    if not exist ".venv\Scripts\python.exe" (
        echo [ERR] Echec creation venv
        pause
        exit /b 1
    )
    echo [OK]  Venv cree
)

:: Install deps if needed
if not exist ".venv\Lib\site-packages\fastapi" (
    echo [..] Installation des dependances...
    call .venv\Scripts\pip install -q -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [ERR] Echec installation
        pause
        exit /b 1
    )
    echo [OK]  Dependances installees
)

:: Check DeepSeek key
if "%Dp_API_KEY%"=="" (
    echo [!!] Cle DeepSeek manquante. Les agents ne fonctionneront pas.
    echo      Definis Dp_API_KEY ou copie example.env en .env
) else (
    echo [OK]  DeepSeek API cle trouvee
)

:: Check LM Studio
curl -s -o nul -w "%%{http_code}" http://localhost:1234/v1/models >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK]  LM Studio disponible
) else (
    echo [..]  LM Studio non detecte
)

echo.
echo Demarrage sur http://%HOST%:%PORT%
echo Ctrl+C pour arreter.
echo.

start http://%HOST%:%PORT%
call .venv\Scripts\python.exe -m uvicorn main:app --host %HOST% --port %PORT% --reload

echo.
echo Serveur arrete.
pause
