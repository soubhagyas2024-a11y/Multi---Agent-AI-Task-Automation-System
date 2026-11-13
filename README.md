# Multi---Agent-AI-Task-Automation-System

# AgentFlow AI – Multi-Agent AI Task Automation System

Natural-language instructions → Coordinator → Planner → specialised agents (parallel where possible) → Verification → final answer, with SQLite persistence, memory, approvals, scheduling and a dark Streamlit dashboard.

## Quick start (Windows / VS Code)
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        &:: then edit .env: GEMINI_API_KEY (required), TAVILY_API_KEY (for research)
run_backend.bat               &:: terminal 1 -> http://127.0.0.1:8000/docs
run_frontend.bat              &:: terminal 2 -> http://localhost:8501
```
Register in the UI – **the first account becomes admin**. Try the sample tasks in *AI Workspace* and `sample_data/sales_demo.csv` in *Data Analysis*.
Run tests: `python -m pytest -q` (the LLM is stubbed; no API keys needed).

## Architecture
```
Streamlit UI ──HTTP/JWT──> FastAPI ──> TaskEngine (thread pool) ──> LangGraph
                              │                                      coordinator → planner → execute_layer ⟲ → verify → finalize → memory
                              │                                                            │ (parallel subtasks via ThreadPool)
                           SQLite (SQLAlchemy) <── task_service ◄── agents: researcher · data_analyst · coder · writer · executor · verifier · memory
                              │                                         └─ integrations: Gemini (REST) · Tavily (REST)
                         APScheduler (scheduled tasks/workflows)
```
**Agent communication**: agents never talk to each other directly. They share the typed `AgentState` (`agents/agent_state.py`): every subtask receives the objective, recalled memory, the *outputs of the subtasks it depends on*, and verifier feedback (`build_context`). Independent subtasks run in parallel; dependent ones wait. Conditional edges: loop while subtasks are ready → verify → optional single corrective round → finalize. Bounded by retry limits, `verify_rounds`, task timeout and LangGraph's recursion limit.

**Execution workflow**: submit → permission check → intent/memory (coordinator) → plan (LLM, validated; heuristic fallback) → layers of subtasks (retries with backoff) → verification (deterministic + LLM) → final response → DB + memory summary.
Statuses: `pending, running, awaiting_approval, paused, completed, failed, cancelled`. Pause/approval/resume re-enter the same graph with persisted subtask state.

## Database (SQLite)
`users, agents, tasks, subtasks, execution_logs, memories, scheduled_tasks, generated_files` as specified, plus `workflows`; a few helper columns were added (e.g. `tasks.plan_json`, `generated_files.kind`). Every user-owned query is filtered by `user_id`.

## API (see /docs)
`/auth/{register,login,logout,me}` · `/tasks` (`create, list, {id}, {id}/execute|cancel|pause|resume|approve, DELETE, schedule…`) · `/agents` (`enable/disable` admin) · `/workflow` (`create, list, {id}, execute, history`) · `/memory` · `/analytics/{overview,tasks,agents,activity,live}` · `/files` (`upload, list, {id}/download`) · `/admin/{users,logs,usage,system}`.

## Dashboard ↔ backend
Overview, AI Workspace, Agent Management, Task Automation (scheduler tab), Workflow Builder, Research, Data Analysis, Code Assistant, Documents, Task History, AI Memory, Analytics (+ admin tabs), Settings – every control calls a real endpoint. Task Automation lives in `1_workspace.py` (`VIEW="automation"`).

## Security
PBKDF2-SHA256 hashed passwords, JWT sessions with logout revocation, admin/user roles, per-user file/task/memory isolation, upload extension/size/magic-byte validation, `safe_join` path-traversal guard, per-user + per-IP rate limits, API keys only in `.env`. The Execution Agent **never runs shell commands**; delete/organise/overwrite/run-Python require explicit user approval; sending email, purchases and publishing are unsupported by design. Python runs through an AST allow-list + isolated interpreter + timeout – this is best-effort, **not a hardened sandbox** (use a container for untrusted multi-tenant use).

## Known limitations
- Needs valid Gemini (and Tavily) keys for real runs; without them tasks fail with a clear message.
- Rate-limit counters, token revocation list and API-usage counters are in-memory (reset on restart; single-process).
- Pause takes effect between execution layers. Scheduler times are UTC.
- PDF export uses ReportLab's base fonts (non-Latin text may not render).
- The workflow editor is a Plotly + form implementation, not a drag-and-drop canvas.

## Layout
`frontend/` Streamlit UI · `backend/` FastAPI, models, auth, services · `agents/` one module per agent · `workflows/` LangGraph graph/nodes/routing/builder · `integrations/` Gemini, Tavily · `automation/` engine, file/document/code execution · `memory/` · `utils/` · `tests/`.
