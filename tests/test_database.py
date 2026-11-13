from backend.database import init_db, session_scope
from backend.models import Agent, User
from memory.memory_manager import MemoryManager


def test_init_seeds_agents(client):
    init_db()
    with session_scope() as db:
        assert db.query(Agent).count() == 9


def _mk(name):
    with session_scope() as db:
        u = User(username=name, email=f"{name}@x.io", password_hash="x")
        db.add(u)
        db.flush()
        return u.id


def test_memory_is_user_scoped(client):
    a, b = _mk("mem_a"), _mk("mem_b")
    mid = MemoryManager.add(a, "I prefer concise answers", "preference")
    assert MemoryManager.search(a, "concise")
    assert MemoryManager.search(b, "concise") == []
    assert not MemoryManager.delete(b, mid)
    assert MemoryManager.delete(a, mid)
