"""Sandboxed file operations. Every path is resolved inside the user's workspace."""
from __future__ import annotations

import csv
import shutil
import uuid
from pathlib import Path

from backend.config import settings
from utils.helpers import safe_join
from utils.validators import sanitize_filename

MAX_TEXT = 1_000_000


def user_dir(user_id: int, sub: str = "workspace") -> Path:
    p = settings.generated_dir / f"user_{int(user_id)}" / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


def output_path(user_id: int, filename: str) -> Path:
    """A fresh, non-colliding path inside the user's outputs folder."""
    name = sanitize_filename(filename)
    p = user_dir(user_id, "outputs") / name
    if p.exists():
        p = p.with_name(f"{p.stem}_{uuid.uuid4().hex[:6]}{p.suffix}")
    return p


def create_folder(ws: Path, rel: str) -> str:
    safe_join(ws, rel).mkdir(parents=True, exist_ok=True)
    return f"Created folder {rel}"


def write_text(ws: Path, rel: str, content: str, overwrite: bool = False) -> Path:
    p = safe_join(ws, rel)
    if p.exists() and not overwrite:
        raise FileExistsError(f"{rel} already exists (overwriting needs approval)")
    if len(content) > MAX_TEXT:
        raise ValueError("Content too large")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def write_csv(ws: Path, rel: str, rows: list[list]) -> Path:
    p = safe_join(ws, rel)
    if p.exists():
        raise FileExistsError(f"{rel} already exists")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return p


def rename(ws: Path, rel: str, new_rel: str) -> str:
    src, dst = safe_join(ws, rel), safe_join(ws, new_rel)
    if not src.exists():
        raise FileNotFoundError(rel)
    if dst.exists():
        raise FileExistsError(new_rel)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return f"Renamed {rel} -> {new_rel}"


def delete(ws: Path, rel: str) -> str:
    p = safe_join(ws, rel)
    if p == Path(ws).resolve():
        raise PermissionError("Cannot delete the workspace root")
    if not p.exists():
        raise FileNotFoundError(rel)
    shutil.rmtree(p) if p.is_dir() else p.unlink()
    return f"Deleted {rel}"


def list_dir(ws: Path, rel: str = ".") -> str:
    p = safe_join(ws, rel)
    items = sorted(p.iterdir()) if p.is_dir() else []
    return "\n".join(("[dir] " if i.is_dir() else "") + i.name for i in items[:200]) or "(empty)"


def organize_by_extension(ws: Path, rel: str = ".") -> str:
    base = safe_join(ws, rel)
    moved = 0
    for f in [x for x in base.iterdir() if x.is_file()]:
        folder = base / (f.suffix.lower().lstrip(".") or "no_extension")
        folder.mkdir(exist_ok=True)
        if not (folder / f.name).exists():
            f.rename(folder / f.name)
            moved += 1
    return f"Organised {moved} file(s) into extension folders"
