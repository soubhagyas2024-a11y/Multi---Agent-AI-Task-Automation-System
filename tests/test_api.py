import io

from tests.conftest import register, wait_for


def test_auth_and_protection(client):
    assert client.get("/tasks").status_code == 401
    h = register(client, "alice")
    assert client.get("/auth/me", headers=h).json()["role"] == "admin"  # first user
    assert client.post("/auth/register", json={"username": "alice", "email": "a2@example.com", "password": "Passw0rd123"}).status_code == 409
    assert client.post("/auth/login", json={"username": "alice", "password": "wrong"}).status_code == 401
    tok = client.post("/auth/login", json={"username": "alice", "password": "Passw0rd123"}).json()["access_token"]
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_task_lifecycle_multi_agent(client):
    h = register(client, "bob")
    r = client.post("/tasks/create", json={"description": "Write a report about testing"}, headers=h)
    assert r.status_code == 201
    t = wait_for(client, h, r.json()["id"])
    assert t["task_status"] == "completed", t
    assert {s["agent"] for s in t["subtasks"]} == {"writer", "coder"}
    assert t["result"] and t["logs"] and t["files"]
    f = t["files"][0]
    assert client.get(f"/files/{f['id']}/download", headers=h).status_code == 200
    carol = register(client, "carol")
    assert client.get(f"/tasks/{t['id']}", headers=carol).status_code == 404       # privacy
    assert client.get(f"/files/{f['id']}/download", headers=carol).status_code == 404
    assert client.get("/analytics/overview", headers=h).json()["completed"] >= 1
    assert any(a["completed"] for a in client.get("/analytics/agents", headers=h).json())
    assert client.get("/admin/users", headers=carol).status_code == 403
    assert client.delete(f"/tasks/{t['id']}", headers=h).status_code == 200


def test_approval_flow_for_destructive_action(client):
    h = register(client, "dave")
    r = client.post("/tasks/create", json={"description": "DELETE-TEST remove old file"}, headers=h)
    t = wait_for(client, h, r.json()["id"])
    assert t["task_status"] == "awaiting_approval"
    assert t["subtasks"][0]["pending_actions"]
    assert client.post(f"/tasks/{t['id']}/approve", json={"approved": True}, headers=h).status_code == 200
    assert wait_for(client, h, t["id"], ("completed", "failed"))["task_status"] == "completed"


def test_upload_validation_and_memory(client):
    h = register(client, "erin")
    assert client.post("/files/upload", files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")}, headers=h).status_code == 400
    ok = client.post("/files/upload", files={"file": ("d.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")}, headers=h)
    assert ok.status_code == 201
    mid = client.post("/memory", json={"content": "likes tables", "category": "preference"}, headers=h).json()["id"]
    assert len(client.get("/memory?q=tables", headers=h).json()) == 1
    assert client.delete(f"/memory/{mid}", headers=h).status_code == 200


def test_workflow_create_execute_and_agent_admin(client):
    h = register(client, "frank")  # not admin
    nodes = [{"id": "n1", "agent": "writer", "instruction": "write intro"}, {"id": "n2", "agent": "verifier", "instruction": "review"}]
    wf = client.post("/workflow/create", json={"name": "wf", "workflow_type": "sequential", "nodes": nodes}, headers=h)
    assert wf.status_code == 201
    bad = client.post("/workflow/create", json={"name": "x", "nodes": [{"id": "a", "agent": "writer", "depends_on": ["a"]}]}, headers=h)
    assert bad.status_code == 422
    r = client.post(f"/workflow/{wf.json()['id']}/execute", headers=h)
    t = wait_for(client, h, r.json()["id"])
    assert t["task_status"] == "completed" and [s["status"] for s in t["subtasks"]] == ["done", "done"]
    assert client.post("/agents/1/disable", headers=h).status_code == 403


def test_cancel_running_task(client):
    h = register(client, "gina")
    r = client.post("/tasks/create", json={"description": "Write a report about cancellation"}, headers=h)
    client.post(f"/tasks/{r.json()['id']}/cancel", headers=h)
    t = wait_for(client, h, r.json()["id"], ("cancelled", "completed", "failed"))
    assert t["task_status"] in ("cancelled", "completed")
