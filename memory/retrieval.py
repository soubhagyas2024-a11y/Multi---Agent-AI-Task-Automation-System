"""Lightweight keyword relevance ranking for memories (no embeddings needed)."""
from __future__ import annotations

import math
import re

_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "i", "my", "me", "it", "this", "that", "please", "can", "you"}


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOP and len(t) > 1}


def rank(items: list, query: str, k: int = 5, key=lambda m: m.memory_content) -> list:
    q = tokens(query)
    scored = []
    for idx, it in enumerate(items):
        t = tokens(key(it))
        overlap = len(q & t)
        if overlap:
            scored.append((overlap / math.sqrt(len(t) + 1), -idx, it))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [s[2] for s in scored[:k]]
