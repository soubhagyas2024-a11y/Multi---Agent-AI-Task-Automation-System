"""Coding Agent: generate / explain / debug Python, validate syntax, save code files."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from agents.agent_state import AgentState, SubTask, build_context
from automation.file_automation import output_path
from integrations import gemini_client
from utils.helpers import truncate

NAME = "coder"
SYSTEM = ("You are the Coding Agent, a senior Python engineer. Produce correct, readable, commented Python 3 with type hints. "
          "Reply with: a short explanation, then ONE complete script in a ```python block. When debugging, first list the "
          "errors found and why, then the corrected full code. Never include secrets.")


def _code(text: str) -> str:
    m = re.findall(r"```(?:python|py)?\n(.*?)```", text, flags=re.S)
    return max(m, key=len).strip() if m else ""


def run(state: AgentState, st: SubTask) -> dict:
    attached = ""
    for f in state.get("files", []):
        if Path(f["path"]).suffix.lower() in (".py", ".txt", ".md", ".json"):
            attached += f"\n\nATTACHED FILE {f['filename']}:\n{truncate(Path(f['path']).read_text(encoding='utf-8', errors='replace'), 8000)}"
    text = gemini_client.generate(f"{build_context(state, st)}\n\nTASK: {st['description']}{attached}", system=SYSTEM, temperature=0.2)
    code, note = _code(text), ""
    if code:
        try:
            ast.parse(code)
        except SyntaxError as exc:
            fixed = _code(gemini_client.generate(f"This code has a syntax error ({exc}). Return the corrected full code in a ```python block.\n\n{code}", system=SYSTEM, temperature=0.1))
            try:
                ast.parse(fixed)
                code, text = fixed, text + "\n\n_(Syntax error auto-corrected.)_"
            except SyntaxError:
                note = f"\n\n⚠️ The generated code still has a syntax error: {exc}"
    artifacts = []
    if code:
        p = output_path(state["user_id"], f"script_{state['task_id']}_{st['id']}.py")
        p.write_text(code, encoding="utf-8")
        artifacts.append({"path": str(p), "type": "py"})
    return {"output": text + note, "artifacts": artifacts}
