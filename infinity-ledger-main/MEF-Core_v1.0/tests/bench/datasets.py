"""Synthetic datasets and helpers for quality and benchmark runs."""

from __future__ import annotations

import math
import random
from typing import Iterable, Iterator, List, Sequence, Tuple


def generate_spiral_points(count: int, *, dim: int = 5, seed: int = 123) -> List[List[float]]:
    """Generate ``count`` deterministic spiral vectors in ``dim`` dimensions."""

    rng = random.Random(seed)
    points: List[List[float]] = []
    for index in range(count):
        theta = index * 0.017 + rng.random() * 1e-4
        vector = [math.cos(theta + j * 0.1) * (1 + j * 0.05) for j in range(dim - 1)]
        vector.append(theta)
        points.append([float(value) for value in vector])
    return points


def build_spiral_corpus(count: int, *, seed: int = 123) -> Tuple[List[str], List[List[float]]]:
    """Return deterministic IDs and vectors for the spiral benchmark corpus."""

    vectors = generate_spiral_points(count, seed=seed)
    ids = [f"spiral-{index:06d}" for index in range(count)]
    return ids, vectors


def iter_records(ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> Iterator[dict]:
    """Yield payload dictionaries suitable for bulk ingestion APIs."""

    for index, (identifier, vector) in enumerate(zip(ids, vectors)):
        yield {
            "id": identifier,
            "vector": [float(value) for value in vector],
            "metadata": {"source": "bench", "index": index},
        }


def chunked(records: Iterable[dict], size: int) -> Iterator[List[dict]]:
    """Yield ``records`` in batches of ``size`` (last chunk may be smaller)."""

    batch: List[dict] = []
    for record in records:
        batch.append(record)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def generate_query_vectors(
    points: Sequence[Sequence[float]], *, count: int = 200, seed: int = 321
) -> List[List[float]]:
    """Create jittered query vectors derived from the provided corpus."""

    rng = random.Random(seed)
    if not points:
        return []
    queries: List[List[float]] = []
    for _ in range(count):
        base = list(rng.choice(points))
        jitter = [rng.gauss(0, 0.01) for _ in base]
        queries.append([a + b for a, b in zip(base, jitter)])
    return queries


def brute_force_top_k(
    query: Sequence[float],
    corpus: Sequence[Sequence[float]],
    *,
    k: int,
    metric: str = "cosine",
) -> List[Tuple[int, float]]:
    """Return the indices of the top-k corpus entries for ``query``."""

    if metric.lower() in {"l2", "l2sq"}:
        scorer = negative_l2_squared
    else:
        scorer = cosine_similarity

    scored = []
    for idx, vector in enumerate(corpus):
        score = scorer(query, vector)
        scored.append((idx, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored[:k]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def negative_l2_squared(a: Sequence[float], b: Sequence[float]) -> float:
    return -sum((x - y) ** 2 for x, y in zip(a, b))
