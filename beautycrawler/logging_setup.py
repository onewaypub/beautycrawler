"""Logging-Konfiguration: schreibt gleichzeitig in Konsole und (optional) Logdatei."""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

LOGGER_NAME = "beautycrawler"


def setup_logging(log_dir: str | Path = "logs", level: int = logging.INFO, to_file: bool = True) -> tuple[logging.Logger, Path | None]:
    # Konsole auf UTF-8 stellen, damit Umlaute/Sonderzeichen sauber erscheinen.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(console)

    log_path: Path | None = None
    if to_file:
        d = Path(log_dir)
        d.mkdir(parents=True, exist_ok=True)
        log_path = d / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"
        fileh = logging.FileHandler(log_path, encoding="utf-8")
        fileh.setLevel(logging.DEBUG)
        fileh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fileh)

    return logger, log_path
