"""Tavily web-search client."""
from __future__ import annotations

import requests

from backend.config import settings


class TavilyError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.tavily_api_key)


def search(query: str, max_results: int = 5, depth: str = "basic") -> list[dict]:
    if not settings.tavily_api_key:
        raise TavilyError("TAVILY_API_KEY is not configured (set it in .env)")
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={"query": query[:400], "max_results": max_results, "search_depth": depth},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise TavilyError(f"Network error contacting Tavily ({type(exc).__name__})")
    if r.status_code in (401, 403):
        raise TavilyError("Tavily rejected the API key")
    if r.status_code != 200:
        raise TavilyError(f"Tavily error (HTTP {r.status_code})")
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "content": x.get("content", "")} for x in r.json().get("results", [])]
