"""Gemini REST client (no heavy SDK). API key is read from the environment only."""
from __future__ import annotations

import threading
import time
from typing import Any

import requests

from backend.config import settings
from utils.helpers import extract_json
from utils.logger import get_logger

logger = get_logger("gemini")
_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_stats = {"calls": 0, "errors": 0, "prompt_tokens": 0, "output_tokens": 0}
_lock = threading.Lock()


class GeminiError(RuntimeError):
    pass


def usage_stats() -> dict[str, int]:
    with _lock:
        return dict(_stats)


def is_configured() -> bool:
    return bool(settings.gemini_api_key)


def generate(prompt: str, system: str | None = None, json_mode: bool = False, temperature: float = 0.4, max_output_tokens: int = 4096) -> str:
    if not settings.gemini_api_key:
        raise GeminiError("GEMINI_API_KEY is not configured (set it in .env)")
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_output_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    last: Exception | None = None
    for attempt in range(3):
        try:
            r = requests.post(
                _URL.format(model=settings.gemini_model),
                headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
                json=body,
                timeout=settings.llm_timeout,
            )
        except requests.RequestException as exc:
            last = GeminiError(f"Network error contacting Gemini ({type(exc).__name__}). Check your internet connection.")
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code in (400, 401, 403, 404):
            with _lock:
                _stats["errors"] += 1
            raise GeminiError(f"Gemini rejected the request (HTTP {r.status_code}). Check GEMINI_API_KEY and GEMINI_MODEL.")
        if r.status_code in (429, 500, 502, 503, 504):
            last = GeminiError(f"Gemini temporarily unavailable (HTTP {r.status_code})")
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise GeminiError(f"Unexpected Gemini response (HTTP {r.status_code})")
        data = r.json()
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise GeminiError("Gemini returned no content (possibly blocked by safety filters)")
        usage = data.get("usageMetadata", {})
        with _lock:
            _stats["calls"] += 1
            _stats["prompt_tokens"] += usage.get("promptTokenCount", 0)
            _stats["output_tokens"] += usage.get("candidatesTokenCount", 0)
        return text
    with _lock:
        _stats["errors"] += 1
    raise last or GeminiError("Gemini request failed")


def generate_json(prompt: str, system: str | None = None, temperature: float = 0.2) -> Any:
    last: Exception | None = None
    for _ in range(2):
        text = generate(prompt, system=system, json_mode=True, temperature=temperature)
        try:
            return extract_json(text)
        except ValueError as exc:
            last = exc
            prompt += "\n\nReturn ONLY valid JSON."
    raise GeminiError(f"Model did not return valid JSON: {last}")
