from fastapi import APIRouter, Depends, HTTPException

from backend import auth
from backend.models import Memory, User
from backend.schemas import MemoryIn
from memory.memory_manager import MemoryManager

router = APIRouter(prefix="/memory", tags=["memory"])


def _out(m: Memory) -> dict:
    return {"id": m.id, "memory_content": m.memory_content, "memory_category": m.memory_category, "created_at": m.created_at.isoformat()}


@router.get("")
def list_memories(q: str | None = None, category: str | None = None, user: User = Depends(auth.get_current_user)):
    return [_out(m) for m in MemoryManager.list(user.id, category=category, q=q)]


@router.post("", status_code=201)
def add_memory(p: MemoryIn, user: User = Depends(auth.rate_limited)):
    mid = MemoryManager.add(user.id, p.content, p.category)
    return {"id": mid, "detail": "Saved"}


@router.put("/{memory_id}")
def update_memory(memory_id: int, p: MemoryIn, user: User = Depends(auth.get_current_user)):
    if not MemoryManager.update(user.id, memory_id, p.content):
        raise HTTPException(404, "Memory not found")
    return {"detail": "Updated"}


@router.delete("/{memory_id}")
def delete_memory(memory_id: int, user: User = Depends(auth.get_current_user)):
    if not MemoryManager.delete(user.id, memory_id):
        raise HTTPException(404, "Memory not found")
    return {"detail": "Deleted"}
