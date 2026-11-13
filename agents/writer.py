"""Writing Agent: reports, emails, summaries; exports DOCX/PDF/MD."""
from __future__ import annotations

import re

from agents.agent_state import AgentState, SubTask, build_context
from automation import document_automation
from automation.file_automation import output_path
from integrations import gemini_client

NAME = "writer"
SYSTEM = ("You are the Writing Agent. Write clear, professional, well-structured Markdown (start with '# Title', use ## sections, "
          "bullets where useful). Use only facts present in the supplied context; keep source references when provided. "
          "For emails include Subject, greeting and sign-off. Do not claim an email was sent.")


def _formats(desc: str) -> list[str]:
    d = desc.lower()
    f = [x for x, keys in (("pdf", ("pdf",)), ("docx", ("docx", "word"))) if any(k in d for k in keys)]
    if f:
        return f
    return ["docx", "pdf"] if any(k in d for k in ("report", "document", "proposal", "minutes", "whitepaper")) else []


def run(state: AgentState, st: SubTask) -> dict:
    md = gemini_client.generate(f"{build_context(state, st)}\n\nWRITING TASK: {st['description']}", system=SYSTEM, temperature=0.5, max_output_tokens=6000).strip()
    arts: list[dict] = []
    fmts = _formats(st["description"])
    if fmts:
        m = re.search(r"^#\s+(.+)", md, flags=re.M)
        stem = re.sub(r"[^A-Za-z0-9]+", "_", m.group(1) if m else "document").strip("_")[:50] or "document"
        arts = document_automation.export(md, stem, fmts, lambda fn: output_path(state["user_id"], fn))
    return {"output": md, "artifacts": arts}
