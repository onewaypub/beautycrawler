#!/usr/bin/env bash
# beautycrawler — Starter für Linux/macOS.
#
# Beim ERSTEN Aufruf wird automatisch eine virtuelle Umgebung (.venv) erstellt und
# alle Abhängigkeiten installiert; danach startet das Skript nur noch den Crawler.
# Alle Argumente werden direkt an den Crawler durchgereicht.
#
# Beispiele:
#   ./run.sh                                   # Standard: Hamburg, 8 Worker, Limit 50
#   ./run.sh --city berlin --workers 8 --limit 200
#   ./run.sh --city hamburg --limit 0          # ganz Hamburg (unbegrenzt)
#   ./run.sh --help                            # alle Optionen anzeigen
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "[setup] Erstelle virtuelle Umgebung (.venv) ..."
  if command -v python3 >/dev/null 2>&1; then PYBOOT=python3; else PYBOOT=python; fi
  if ! "$PYBOOT" -m venv .venv; then
    echo "[Fehler] Python 3 nicht gefunden. Bitte installieren: https://www.python.org/downloads/" >&2
    exit 1
  fi
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r requirements.txt
  echo "[setup] fertig."
fi

if [ "$#" -eq 0 ]; then
  echo "[info] Keine Argumente -> Standardlauf (Hamburg, 8 Worker, Limit 50)."
  echo "[info] Eigene Optionen z. B.: ./run.sh --city berlin --workers 8 --limit 200"
  exec "$PY" -m beautycrawler --city hamburg --workers 8 --limit 50
else
  exec "$PY" -m beautycrawler "$@"
fi
