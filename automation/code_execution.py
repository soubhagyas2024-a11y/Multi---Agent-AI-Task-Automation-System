"""Best-effort restricted Python execution.

NOT a hardened sandbox: it combines an AST allow-list (no file/OS/network access, no dunder
tricks), an isolated interpreter (-I), an empty environment, a working directory inside the user
workspace and a hard timeout. For untrusted multi-tenant use, run it inside a container/VM.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import uuid
from pathlib import Path

from backend.config import settings
from utils.helpers import truncate

ALLOWED_IMPORTS = {"math", "json", "csv", "random", "statistics", "datetime", "re", "collections", "itertools",
                   "functools", "string", "decimal", "fractions", "textwrap", "heapq", "bisect", "typing", "dataclasses", "time"}
BLOCKED_NAMES = {"eval", "exec", "compile", "open", "__import__", "input", "globals", "locals", "vars",
                 "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "help", "memoryview"}


def validate_code(code: str) -> None:
    """Raise ValueError if the script uses anything outside the allow-list."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Syntax error: {exc}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [(node.module or "").split(".")[0]]
        else:
            mods = []
        for m in mods:
            if m not in ALLOWED_IMPORTS:
                raise ValueError(f"Import of '{m}' is not allowed in the restricted environment")
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise ValueError(f"Use of '{node.id}' is not allowed")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Access to dunder attributes is not allowed")


def run_python(code: str, workdir: Path) -> dict:
    validate_code(code)
    scripts = Path(workdir) / ".scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    script = scripts / f"run_{uuid.uuid4().hex[:8]}.py"
    script.write_text(code, encoding="utf-8")
    env = {"PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    try:
        p = subprocess.run([sys.executable, "-I", str(script)], cwd=str(workdir), env=env, capture_output=True,
                           text=True, timeout=settings.python_exec_timeout, encoding="utf-8", errors="replace")
        return {"ok": p.returncode == 0, "returncode": p.returncode, "stdout": truncate(p.stdout, 8000), "stderr": truncate(p.stderr, 4000), "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": f"Timed out after {settings.python_exec_timeout}s", "timed_out": True}
    finally:
        script.unlink(missing_ok=True)
