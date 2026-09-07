@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "VENV=.venv"
set "PY=%VENV%\Scripts\python.exe"

echo ============================================================
echo   KnowHow Tool wird gestartet
echo ============================================================

if not exist "%PY%" (
    echo   [1/3] Python-Umgebung wird angelegt ...
    py -3 -m venv "%VENV%" 2>nul || python -m venv "%VENV%"
    if not exist "%PY%" (
        echo.
        echo   FEHLER: Es wurde kein Python gefunden.
        echo   Bitte Python 3.10 oder neuer installieren: https://www.python.org/downloads/
        echo.
        pause
        exit /b 1
    )
    echo   [2/3] Abhaengigkeiten werden installiert ...
    "%PY%" -m pip install --upgrade pip --quiet
    "%PY%" -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo.
        echo   FEHLER: Die Abhaengigkeiten konnten nicht installiert werden.
        pause
        exit /b 1
    )
)

echo   [3/3] Anwendung startet ...
echo.
"%PY%" run.py %*

if errorlevel 1 (
    echo.
    echo   Die Anwendung wurde mit einem Fehler beendet.
    echo   Details stehen in data\logs\app.log
    pause
)
endlocal
