import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="agentflow_test_")
os.environ.update({"DATABASE_URL": f"sqlite:///{Path(_tmp, 'test.db').as_posix()}", "GENERATED_DIR": str(Path(_tmp, "gen")),
                   "LOGS_DIR": str(Path(_tmp, "logs")), "DISABLE_SCHEDULER": "1", "GEMINI_API_KEY": "test-key",
                   "SECRET_KEY": "test-secret-key-test-secret-key-1234", "MAX_RETRIES": "1"})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from integrations import gemini_client  # noqa: E402


def fake_generate(prompt, system=None, json_mode=False, temperature=0.4, max_output_tokens=4096):
    s = system or ""
    if "Planner Agent" in s:
        if "DELETE-TEST" in prompt:
            return json.dumps({"objective": "cleanup", "subtasks": [{"id": "t1", "agent": "executor", "description": "delete old.txt", "depends_on": []}]})
        return json.dumps({"objective": "Make a report", "subtasks": [
            {"id": "t1", "agent": "writer", "description": "Write a short intro", "depends_on": []},
            {"id": "t2", "agent": "coder", "description": "Write a hello function", "depends_on": []},
            {"id": "t3", "agent": "writer", "description": "Write a pdf report combining everything", "depends_on": ["t1", "t2"]}]})
    if "Verification Agent" in s:
        return json.dumps({"passed": True, "issues": [], "retry": [], "feedback": {}})
    if "Execution Agent" in s:
        return json.dumps({"actions": [{"action": "write_text", "path": "old.txt", "content": "x"}, {"action": "delete", "path": "old.txt"}]})
    if "Coding Agent" in s:
        return "Here you go:\n```python\ndef hello():\n    return 'hi'\n```"
    if "Coordinator" in s:
        return "FINAL ANSWER"
    time.sleep(0.05)
    return "# Title\n\nSome **bold** content.\n\n- item"


@pytest.fixture(scope="session", autouse=True)
def _patch_llm():
    gemini_client.generate = fake_generate
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(__import__("backend.main", fromlist=["app"]).app) as c:
        yield c


def register(client, name):
    r = client.post("/auth/register", json={"username": name, "email": f"{name}@example.com", "password": "Passw0rd123"})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def wait_for(client, h, tid, states=("completed", "failed", "cancelled", "awaiting_approval", "paused"), timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        t = client.get(f"/tasks/{tid}", headers=h).json()
        if t["task_status"] in states:
            return t
        time.sleep(0.2)
    raise AssertionError("timeout waiting for task")
