"""Research Agent: Tavily search + Gemini synthesis with numbered source references."""
from __future__ import annotations

from agents.agent_state import AgentError, AgentState, SubTask, build_context
from integrations import gemini_client, tavily_client

NAME = "researcher"
SYSTEM = ("You are the Research Agent. Use ONLY the provided search results. Extract key findings, note disagreements "
          "between sources, cite with [n] markers, and never invent facts. Output concise Markdown: ## Key Findings, ## Details.")


def run(state: AgentState, st: SubTask) -> dict:
    results = tavily_client.search(st["description"][:380], max_results=6)
    if not results:
        raise AgentError("The search returned no results")
    sources = "\n\n".join(f"[{i}] {r['title']} ({r['url']})\n{r['content'][:900]}" for i, r in enumerate(results, 1))
    prompt = f"{build_context(state, st)}\n\nRESEARCH TASK: {st['description']}\n\nSEARCH RESULTS:\n{sources}"
    summary = gemini_client.generate(prompt, system=SYSTEM)
    refs = "\n".join(f"[{i}] {r['title']} - {r['url']}" for i, r in enumerate(results, 1))
    return {"output": f"{summary}\n\n**Sources**\n{refs}", "artifacts": []}
