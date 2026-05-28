@echo off
REM beautycrawler - Starter fuer Windows (einfach aufrufen oder doppelklicken).
REM
REM Beim ERSTEN Aufruf wird automatisch eine virtuelle Umgebung (.venv) erstellt
REM und alle Abhaengigkeiten installiert; danach startet es nur noch den Crawler.
REM Alle Argumente werden direkt an den Crawler durchgereicht.
REM
REM Beispiele:
REM   run.bat
REM   run.bat --city berlin --workers 8 --limit 200
REM   run.bat --city hamburg --limit 0
REM   run.bat --help
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [setup] Erstelle virtuelle Umgebung ^(.venv^) ...
  python -m venv .venv
  if errorlevel 1 (
    echo [Fehler] Python 3 nicht gefunden. Bitte installieren: https://www.python.org/downloads/
    exit /b 1
  )
  "%PY%" -m pip install --quiet --upgrade pip
  "%PY%" -m pip install --quiet -r requirements.txt
  echo [setup] fertig.
)

if "%~1"=="" (
  echo [info] Keine Argumente -^> Standardlauf ^(Hamburg, 8 Worker, Limit 50^).
  echo [info] Eigene Optionen z. B.: run.bat --city berlin --workers 8 --limit 200
  "%PY%" -m beautycrawler --city hamburg --workers 8 --limit 50
) else (
  "%PY%" -m beautycrawler %*
)
endlocal
