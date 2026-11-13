"""Markdown -> DOCX / PDF / MD export."""
from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape


def _runs(par, text: str) -> None:
    for i, chunk in enumerate(re.split(r"\*\*", text)):
        if chunk:
            par.add_run(re.sub(r"[`*_]", "", chunk) if i % 2 == 0 else chunk).bold = i % 2 == 1


def to_docx(md: str, path: Path) -> Path:
    from docx import Document

    doc = Document()
    for raw in md.splitlines():
        s = raw.rstrip()
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            doc.add_heading(m.group(2), len(m.group(1)) - 1 if len(m.group(1)) == 1 else len(m.group(1)))
        elif re.match(r"^\s*[-*]\s+", s):
            _runs(doc.add_paragraph(style="List Bullet"), re.sub(r"^\s*[-*]\s+", "", s))
        elif re.match(r"^\s*\d+\.\s+", s):
            _runs(doc.add_paragraph(style="List Number"), re.sub(r"^\s*\d+\.\s+", "", s))
        elif s.strip():
            _runs(doc.add_paragraph(), s)
    doc.save(str(path))
    return path


def to_pdf(md: str, path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()

    def inline(t: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(re.sub(r"[`]", "", t)))

    story = []
    for raw in md.splitlines():
        s = raw.rstrip()
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            story.append(Paragraph(inline(m.group(2)), styles[f"Heading{len(m.group(1))}"]))
        elif re.match(r"^\s*[-*]\s+", s):
            story.append(Paragraph("&bull; " + inline(re.sub(r"^\s*[-*]\s+", "", s)), styles["BodyText"]))
        elif s.strip():
            story.append(Paragraph(inline(s), styles["BodyText"]))
        else:
            story.append(Spacer(1, 6))
    SimpleDocTemplate(str(path), pagesize=A4).build(story or [Paragraph(" ", styles["BodyText"])])
    return path


def export(md: str, stem: str, formats: list[str], out_path_fn) -> list[dict]:
    """Write requested formats; `out_path_fn(filename)` returns a unique destination path."""
    out = []
    for fmt in formats:
        p = out_path_fn(f"{stem}.{fmt}")
        {"docx": to_docx, "pdf": to_pdf, "md": lambda m, q: (q.write_text(m, encoding="utf-8"), q)[1]}[fmt](md, p)
        out.append({"path": str(p), "type": fmt})
    return out
