"""Benchmark script comparing HNSW and IVF-PQ provider stubs.

The goal is not absolute performance but deterministically capturing latency and
recall characteristics so regressions can be detected.  The script can be
invoked via ``python -m cli.bench_index_providers`` and prints aggregated
percentiles for latency together with a naive recall@10 comparison for both
providers.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Dict, List, Sequence

from vector_db.index_manager import IndexManager, VectorRecord


@dataclass
class ProviderStats:
    latencies: List[float]
    recall_at_10: float

    @property
    def p50(self) -> float:
        ordered = sorted(self.latencies)
        return ordered[int(len(ordered) * 0.5)]

    @property
    def p95(self) -> float:
        ordered = sorted(self.latencies)
        return ordered[int(len(ordered) * 0.95)]

    @property
    def p99(self) -> float:
        ordered = sorted(self.latencies)
        return ordered[int(len(ordered) * 0.99)]

    @property
    def average(self) -> float:
        return mean(self.latencies) if self.latencies else 0.0


def _generate_dataset(dimension: int, size: int, seed: int = 1234) -> List[VectorRecord]:
    random.seed(seed)
    dataset = []
    for idx in range(size):
        vector = [random.uniform(-1, 1) for _ in range(dimension)]
        dataset.append(
            VectorRecord(
                id=f"vec-{idx}",
                values=vector,
                metadata={"group": idx % 5},
                epoch=1,
            )
        )
    return dataset


def _measure_provider(manager: IndexManager, provider: str, queries: Sequence[Sequence[float]]):
    manager.set_collection_provider("bench", provider)
    latencies: List[float] = []
    correct = 0
    for query in queries:
        start = time.perf_counter()
        results = manager.search_vectors("bench", query, top_k=10, mode="ann")
        latencies.append((time.perf_counter() - start) * 1000.0)
        if results and results[0]["id"] == "vec-0":
            correct += 1
    recall = correct / len(queries)
    return ProviderStats(latencies=latencies, recall_at_10=recall)


def run_benchmark(base_path: Path, dimension: int = 16, dataset_size: int = 128, queries: int = 32) -> Dict[str, ProviderStats]:
    manager = IndexManager(base_path)
    dataset = _generate_dataset(dimension, dataset_size)
    manager.upsert_vectors("bench", dataset, epoch=1)

    query_vectors = [record.values for record in dataset[:queries]]
    results = {}
    for provider in ("hnsw", "ivf_pq"):
        results[provider] = _measure_provider(manager, provider, query_vectors)
    return results


def main() -> None:
    base_path = Path.home() / "mef" / "bench"
    base_path.mkdir(parents=True, exist_ok=True)
    stats = run_benchmark(base_path)

    for name, provider_stats in stats.items():
        print(f"Provider: {name}")
        print(f"  p50: {provider_stats.p50:.4f} ms")
        print(f"  p95: {provider_stats.p95:.4f} ms")
        print(f"  p99: {provider_stats.p99:.4f} ms")
        print(f"  avg: {provider_stats.average:.4f} ms")
        print(f"  recall@10: {provider_stats.recall_at_10:.3f}")


if __name__ == "__main__":
    main()

