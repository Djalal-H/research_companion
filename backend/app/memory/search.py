"""Deterministic lexical cosine search; not a semantic embedding model."""

import math
import re
from collections import Counter

STOP_WORDS = set("a an and are as at be by for from i in is it of on or our the to we with".split())


def vector(text: str) -> dict[str, float]:
    counts = Counter(t for t in re.findall(r"\w+", text.lower()) if t not in STOP_WORDS)
    norm = math.sqrt(sum(n * n for n in counts.values()))
    return {term: count / norm for term, count in counts.items()} if norm else {}


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    return sum(weight * right.get(term, 0) for term, weight in left.items())
