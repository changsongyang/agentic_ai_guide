"""Deterministic, dependency-free smoke fixtures used by book examples."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping, Sequence


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must be non-empty and have equal dimensions")
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(numerator / (left_norm * right_norm))


def offline_vector_search(
    query: Sequence[float],
    documents: Iterable[Mapping[str, Any]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Rank in-memory vectors by cosine similarity, then by stable document ID."""

    if top_k < 0:
        raise ValueError("top_k must be non-negative")
    matches = [
        {
            "id": str(document["id"]),
            "text": document.get("text", ""),
            "score": _cosine_similarity(query, document["vector"]),
        }
        for document in documents
    ]
    matches.sort(key=lambda match: (-match["score"], match["id"]))
    return matches[:top_k]


def run_tool_loop(
    calls: Iterable[Mapping[str, Any]],
    tools: Mapping[str, Callable[..., Any]],
) -> dict[str, Any]:
    """Execute a scripted tool loop and require an explicit finish action."""

    observations: list[dict[str, Any]] = []
    for call in calls:
        name = str(call["tool"])
        arguments = dict(call.get("arguments", {}))
        if name == "finish":
            if "answer" not in arguments:
                raise ValueError("finish requires an answer")
            return {
                "answer": arguments["answer"],
                "observations": tuple(observations),
            }
        if name not in tools:
            raise KeyError(f"unknown tool: {name}")
        observations.append({"tool": name, "result": tools[name](**arguments)})
    raise RuntimeError("tool loop ended without an explicit finish action")


def sample_cost(
    events: Iterable[Mapping[str, Any]],
    *,
    input_usd_per_million: Decimal,
    output_usd_per_million: Decimal,
) -> Decimal:
    """Calculate sampled model and tool cost without binary floating-point drift."""

    million = Decimal(1_000_000)
    total = Decimal("0")
    for event in events:
        total += Decimal(str(event.get("input_tokens", 0))) * input_usd_per_million / million
        total += Decimal(str(event.get("output_tokens", 0))) * output_usd_per_million / million
        total += Decimal(str(event.get("tool_cost_usd", "0")))
    return total
