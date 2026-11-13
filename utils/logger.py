"""Console + rotating-file logging (Windows safe)."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from backend.config import settings

_configured = False


def get_logger(name: str = "app") -> logging.Logger:
    global _configured
    root = logging.getLogger("agentflow")
    if not _configured:
        root.setLevel(settings.log_level)
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)
        try:
            settings.logs_dir.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(settings.logs_dir / "agentflow.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            pass
        root.propagate = False
        _configured = True
    return logging.getLogger(f"agentflow.{name}")
