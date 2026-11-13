"""Input validation helpers."""
from __future__ import annotations

import re
from pathlib import Path

from backend.config import settings

ALLOWED_UPLOAD_EXT = {".csv", ".xlsx", ".xls", ".txt", ".md", ".json", ".pdf", ".docx", ".py"}
_MAGIC = {".xlsx": b"PK", ".docx": b"PK", ".pdf": b"%PDF", ".xls": b"\xd0\xcf\x11\xe0"}


def validate_username(u: str) -> str:
    u = (u or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", u):
        raise ValueError("Username must be 3-32 characters: letters, digits, . _ -")
    return u


def validate_email(e: str) -> str:
    e = (e or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) or len(e) > 120:
        raise ValueError("Invalid email address")
    return e


def validate_password(p: str) -> str:
    if len(p or "") < 8 or not re.search(r"[A-Za-z]", p) or not re.search(r"\d", p):
        raise ValueError("Password must be at least 8 characters and contain a letter and a digit")
    if len(p) > 128:
        raise ValueError("Password too long")
    return p


def sanitize_filename(name: str) -> str:
    name = Path((name or "").replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._")
    return name[:100] or "file"


def validate_upload(filename: str, data: bytes) -> str:
    """Return the sanitised filename or raise ValueError."""
    clean = sanitize_filename(filename)
    ext = Path(clean).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise ValueError(f"File type '{ext or 'unknown'}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXT))}")
    if not data:
        raise ValueError("Uploaded file is empty")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"File exceeds the {settings.max_upload_mb} MB limit")
    magic = _MAGIC.get(ext)
    if magic and not data.startswith(magic):
        raise ValueError("File content does not match its extension")
    return clean
