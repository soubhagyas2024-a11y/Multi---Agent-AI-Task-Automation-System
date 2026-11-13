"""Upload validation/storage and access-controlled file lookup."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from automation.file_automation import user_dir
from backend.config import settings
from backend.models import GeneratedFile, User
from utils.helpers import safe_join
from utils.validators import validate_upload


def save_upload(db: Session, user: User, upload: UploadFile) -> GeneratedFile:
    data = upload.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        name = validate_upload(upload.filename or "", data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    dest = safe_join(user_dir(user.id, "uploads"), f"{uuid.uuid4().hex[:8]}_{name}")
    dest.write_bytes(data)
    f = GeneratedFile(user_id=user.id, filename=name, file_path=str(dest), file_type=Path(name).suffix.lstrip(".").lower(), kind="upload")
    db.add(f)
    db.commit()
    return f


def get_file_for_user(db: Session, user: User, file_id: int) -> tuple[GeneratedFile, Path]:
    f = db.get(GeneratedFile, file_id)
    if not f or (f.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "File not found")
    try:
        p = safe_join(settings.generated_dir, str(Path(f.file_path).resolve().relative_to(settings.generated_dir)))
    except (ValueError, PermissionError):
        raise HTTPException(403, "File path not allowed")
    if not p.is_file():
        raise HTTPException(404, "File no longer exists on disk")
    return f, p
