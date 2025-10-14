"""Deterministic Ledger⇔Spiral coupling utilities.

This module implements the add-ons described by the 5D Spiral coupling
specification.  It exposes a small stateful engine that can be used by the API
layer and directly in tests to realise the following behaviours:

* inject ledger events as spiral resonance seeds and HDAG nodes
* synchronise HDAG edges by evaluating resonance against a configured threshold
* navigate the spiral by selecting the best candidate step based on a
  configurable resonance metric
* condense history windows into Temporal Information Crystals (TICs) while
  exposing invariants and a pipeline proof derived from the executed VM steps
* query the condensed TIC catalogue using the same resonance functional

All calculations are deterministic – the same input, version and configuration
lead to identical artefacts.  State is persisted to disk in canonical JSON form
so that restarts reproduce the previous HDAG head, TIC catalogue and pipeline
proof material.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ISO_EPOCH = datetime(1970, 1, 1)


@dataclass(frozen=True)
class SpiralParameters:
    """Parameters controlling the spiral projection."""

    a: float = float(os.getenv("SPIRAL_A", "1.0"))
    b: float = float(os.getenv("SPIRAL_B", "0.5"))
    c: float = float(os.getenv("SPIRAL_C", "0.1"))
    theta_step: float = float(os.getenv("THETA_STEP", "0.017"))
    alpha: float = float(os.getenv("COUPLING_ALPHA", "0.3"))
    beta: float = float(os.getenv("COUPLING_BETA", "0.3"))

    def coordinates(self, theta: float) -> List[float]:
        """Compute the 5D spiral coordinates for a given angle."""

        return [
            float(self.a * math.cos(theta)),
            float(self.a * math.sin(theta)),
            float(self.b * math.cos(2.0 * theta)),
            float(self.b * math.sin(2.0 * theta)),
            float(self.c * theta),
        ]


@dataclass(frozen=True)
class ResonanceMetric:
    """Configuration of the resonance functional."""

    metric: str = os.getenv("F_METRIC", "cosine").lower()

    def score(self, x: Sequence[float], y: Sequence[float]) -> float:
        if self.metric == "l2sq":
            return -float(sum((xi - yi) ** 2 for xi, yi in zip(x, y)))

        # default to cosine similarity and guard against degenerate norms
        dot = sum(xi * yi for xi, yi in zip(x, y))
        norm_x = math.sqrt(sum(xi * xi for xi in x))
        norm_y = math.sqrt(sum(yi * yi for yi in y))
        if norm_x == 0.0 or norm_y == 0.0:
            return 0.0
        return float(dot / (norm_x * norm_y))


def _stable_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _uuid5(namespace: uuid.UUID, name: str) -> str:
    return str(uuid.uuid5(namespace, name))


class SpiralCouplingEngine:
    """Stateful engine that materialises coupling, navigation and TIC logic."""

    def __init__(
        self,
        base_path: Optional[Path] = None,
        *,
        params: Optional[SpiralParameters] = None,
        resonance: Optional[ResonanceMetric] = None,
        eps_pi: float = float(os.getenv("EPS_PI", os.getenv("MEF_EPS_PI", "0.001"))),
        zk_mu: float = float(os.getenv("ZK_MU", "0.5")),
    ) -> None:
        self.base_path = Path(base_path or Path.home() / "mef" / "coupling")
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.state_path = self.base_path / "coupling_state.json"
        self.params = params or SpiralParameters()
        self.resonance = resonance or ResonanceMetric()
        self.eps_pi = eps_pi
        self.zk_mu = zk_mu
        self._lock = threading.RLock()
        self._state = self._load_state()

    # ------------------------------------------------------------------
    # public API
    def inject_seed(self, event: Mapping[str, Any]) -> Dict[str, Any]:
        """Create a resonance seed for a ledger event and persist it."""

        canonical_event = _stable_json(event)
        event_hash = _sha256_bytes(canonical_event)

        with self._lock:
            counter = self._state.setdefault("event_counter", 0)
            theta = counter * self.params.theta_step
            coords = self.params.coordinates(theta)
            self._state["event_counter"] = counter + 1

            seed_material = {
                "event_hash": event_hash,
                "theta": theta,
                "coords": coords,
            }
            seed_id = _uuid5(uuid.NAMESPACE_URL, f"seed:{event_hash}:{theta:.12f}")
            hdag_node_id = _uuid5(uuid.NAMESPACE_URL, f"hdag:{event_hash}:{theta:.12f}")
            timestamp = ISO_EPOCH + timedelta(milliseconds=counter)

            seeds = self._state.setdefault("seeds", {})
            seeds[seed_id] = {
                "event": json.loads(canonical_event.decode("utf-8")),
                "event_hash": event_hash,
                "theta": theta,
                "coords": coords,
                "hdag_node_id": hdag_node_id,
                "timestamp": timestamp.isoformat() + "Z",
            }

            nodes = self._state.setdefault("hdag", {}).setdefault("nodes", {})
            nodes[hdag_node_id] = {
                "id": hdag_node_id,
                "seed_id": seed_id,
                "tensor": coords,
                "theta": theta,
                "event_hash": event_hash,
                "index": counter,
                "timestamp": timestamp.isoformat() + "Z",
            }

            step_hash = self._register_step(
                "SPIRAL_WRITE",
                {
                    "seed_id": seed_id,
                    "hdag_node_id": hdag_node_id,
                    "theta": theta,
                    "x5": coords,
                    "event_hash": event_hash,
                },
            )
            self._state.setdefault("pending_steps", []).append(step_hash)
            self._persist_state()

            return {
                "seed_id": seed_id,
                "hdag_node_id": hdag_node_id,
                "resonance_seed": {
                    "theta": theta,
                    "x5": coords,
                },
            }

    def sync_hdag(self, threshold: float) -> Dict[str, Any]:
        """Create HDAG edges when resonance exceeds the provided threshold."""

        with self._lock:
            graph = self._state.setdefault("hdag", {})
            nodes = graph.setdefault("nodes", {})
            edges: List[Dict[str, Any]] = graph.setdefault("edges", [])
            existing = {(edge["from"], edge["to"]) for edge in edges}

            ordered_nodes = sorted(nodes.values(), key=lambda item: item["index"])
            added = 0

            for i, source in enumerate(ordered_nodes):
                for target in ordered_nodes[i + 1 :]:
                    key = (source["id"], target["id"])
                    if key in existing:
                        continue
                    score = self.resonance.score(source["tensor"], target["tensor"])
                    if score <= threshold:
                        continue
                    edge_payload = {
                        "from": source["id"],
                        "to": target["id"],
                        "weight": score,
                    }
                    edges.append(edge_payload)
                    existing.add(key)
                    added += 1

            graph["edges"] = sorted(edges, key=lambda item: (item["from"], item["to"]))
            graph["head"] = self._compute_hdag_head(graph)
            self._persist_state()

            return {
                "edges_added": added,
                "hdag_head": graph["head"],
            }

    def navigate_spiral(
        self,
        theta_current: float,
        candidates: Sequence[float],
        *,
        params: Optional[Mapping[str, float]] = None,
    ) -> Dict[str, Any]:
        """Select the next theta that maximises resonance."""

        if not candidates:
            raise ValueError("candidates must not be empty")

        local_params = self._override_params(params)
        current_coords = local_params.coordinates(theta_current)

        best_theta: Optional[float] = None
        best_score = -math.inf
        for candidate in sorted(candidates):
            coords = local_params.coordinates(candidate)
            score = self.resonance.score(current_coords, coords)
            if score > best_score or (math.isclose(score, best_score) and (best_theta is None or candidate < best_theta)):
                best_score = score
                best_theta = candidate

        assert best_theta is not None  # for type-checkers

        step_hash = self._register_step(
            "SPIRAL_NAV",
            {
                "theta_current": theta_current,
                "theta_next": best_theta,
                "candidates": list(sorted(candidates)),
                "score": best_score,
            },
        )
        with self._lock:
            self._state.setdefault("pending_steps", []).append(step_hash)
            self._persist_state()

        return {
            "theta_next": best_theta,
            "score": best_score,
        }

    def condense_histories(
        self,
        histories: Sequence[Sequence[float]],
        *,
        mode: str = "argmax_sumF",
    ) -> Dict[str, Any]:
        """Condense a history window into a TIC artefact."""

        if mode != "argmax_sumF":
            raise ValueError("unsupported condensation mode")
        if not histories:
            raise ValueError("histories must not be empty")

        flattened = [list(history) for history in histories]

        best_vector: Optional[List[float]] = None
        best_sum = -math.inf
        for candidate in flattened:
            score = sum(self.resonance.score(candidate, other) for other in flattened)
            if score > best_sum:
                best_sum = score
                best_vector = candidate

        assert best_vector is not None

        scores = [self.resonance.score(best_vector, other) for other in flattened]
        if scores:
            baseline = scores[0]
            delta_pi = max(abs(score - baseline) for score in scores)
            variance = sum((score - sum(scores) / len(scores)) ** 2 for score in scores) / max(len(scores), 1)
            stability = max(0.0, 1.0 - min(1.0, variance))
        else:
            delta_pi = 0.0
            stability = 1.0

        tic_id = _uuid5(uuid.NAMESPACE_URL, _sha256_bytes(_stable_json(best_vector)))

        pending_steps = self._flush_pending_steps()
        seed_steps = self._seed_step_hashes(flattened)
        combined_steps = sorted(set(seed_steps + pending_steps))
        pipeline_steps = list(combined_steps)
        pipeline_proof = self._assemble_pipeline_proof(pipeline_steps)

        invariants = {
            "delta_pi": float(delta_pi),
            "stability": float(stability),
        }

        tic_payload = {
            "tic_id": tic_id,
            "vector": best_vector,
            "argmax_sumF": float(best_sum),
            "invariants": invariants,
            "proof": {
                "pipeline_proof": pipeline_proof,
                "steps": pipeline_steps,
            },
            "meta": {
                "created": self._deterministic_timestamp(tic_id),
                "mode": mode,
                "hdag_head": self._state.get("hdag", {}).get("head"),
            },
        }

        step_hash = self._register_step(
            "SPIRAL_CONDENSE",
            {
                "tic_id": tic_id,
                "argmax_sumF": float(best_sum),
                "invariants": invariants,
            },
        )

        with self._lock:
            tics = self._state.setdefault("tics", {})
            tics[tic_id] = tic_payload
            catalogue = self._state.setdefault("tic_order", [])
            if tic_id not in catalogue:
                catalogue.append(tic_id)
            self._persist_state()

        # include the condensation step in the proof material for transparency
        pipeline_steps.append(step_hash)
        pipeline_proof = self._assemble_pipeline_proof(pipeline_steps)
        tic_payload["proof"]["pipeline_proof"] = pipeline_proof
        tic_payload["proof"]["steps"] = pipeline_steps

        with self._lock:
            tics = self._state.setdefault("tics", {})
            tics[tic_id] = tic_payload
            self._persist_state()

        return tic_payload

    def register_tic(self, tic: Mapping[str, Any], *, persist: bool = True) -> None:
        """Import an externally produced TIC into the coupling catalogue."""

        vector_source = tic.get("vector") or tic.get("fixpoint") or []
        vector = [float(value) for value in vector_source]

        tic_id = str(tic.get("tic_id") or tic.get("id"))
        if not tic_id:
            raise ValueError("tic must include tic_id")

        invariants = json.loads(json.dumps(tic.get("invariants") or {}))
        meta = json.loads(
            json.dumps(
                tic.get("meta")
                or {
                    "source_snapshot": tic.get("source_snapshot"),
                    "seed": tic.get("seed"),
                }
            )
        )
        proof = tic.get("proof") or {}

        payload = {
            "tic_id": tic_id,
            "vector": vector,
            "invariants": invariants,
            "meta": meta,
            "proof": {
                "pipeline_proof": proof.get("pipeline_proof"),
            },
        }

        with self._lock:
            catalogue = self._state.setdefault("tic_order", [])
            tics = self._state.setdefault("tics", {})
            tics[tic_id] = payload
            if tic_id not in catalogue:
                catalogue.append(tic_id)
            if persist:
                self._persist_state()

    def query_tics(self, vector: Sequence[float], k: int) -> List[Dict[str, Any]]:
        if k <= 0:
            raise ValueError("k must be positive")

        with self._lock:
            tics = self._state.get("tics", {})
            catalogue = self._state.get("tic_order", [])
            items = [tics[tic_id] for tic_id in catalogue if tic_id in tics]

        scored = []
        for item in items:
            score = self.resonance.score(vector, item["vector"])
            scored.append(
                {
                    "tic_id": item["tic_id"],
                    "score": float(score),
                    "meta": item.get("meta", {}),
                    "pipeline_proof": item.get("proof", {}).get("pipeline_proof"),
                }
            )

        scored.sort(key=lambda entry: (-entry["score"], entry["tic_id"]))
        return scored[:k]

    def zk_infer(self, x: Any) -> Dict[str, Any]:
        """Return a deterministic ZK stub response."""

        input_hash = _sha256_bytes(_stable_json(x))
        offset_ms = int(input_hash[:12], 16) % 86400000
        timestamp = (ISO_EPOCH + timedelta(milliseconds=offset_ms)).isoformat() + "Z"
        payload = {
            "input_hash": input_hash,
            "timestamp": timestamp,
        }
        proof_stub = {"hash": input_hash, "valid": True}
        reference_vector = self.params.coordinates(0.0)
        output_vector = self.params.coordinates(self.params.theta_step)
        resonance = self.resonance.score(output_vector, reference_vector)
        lzk = (1.0 - resonance) + self.zk_mu * (1.0 - 1.0)
        step_hash = self._register_step(
            "ZK_VERIFY",
            {
                "input_hash": payload["input_hash"],
                "lzk": lzk,
            },
        )
        with self._lock:
            self._state.setdefault("pending_steps", []).append(step_hash)
            self._persist_state()
        return {"y": payload, "proof_stub": proof_stub, "lzk": float(lzk)}

    def get_state_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    # ------------------------------------------------------------------
    # helpers
    def _override_params(self, override: Optional[Mapping[str, float]]) -> SpiralParameters:
        if not override:
            return self.params
        return SpiralParameters(
            a=float(override.get("a", self.params.a)),
            b=float(override.get("b", self.params.b)),
            c=float(override.get("c", self.params.c)),
            theta_step=self.params.theta_step,
            alpha=self.params.alpha,
            beta=self.params.beta,
        )

    def _load_state(self) -> Dict[str, Any]:
        if self.state_path.exists():
            with open(self.state_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        return {
            "event_counter": 0,
            "seeds": {},
            "hdag": {"nodes": {}, "edges": [], "head": None},
            "pending_steps": [],
            "steps": [],
            "tics": {},
            "tic_order": [],
        }

    def _persist_state(self) -> None:
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(self._state, handle, sort_keys=True, indent=2)

    def _register_step(self, step: str, payload: Mapping[str, Any]) -> str:
        material = {
            "step": step,
            "payload": payload,
        }
        step_hash = _sha256_bytes(_stable_json(material))
        with self._lock:
            record = {
                "step": step,
                "payload": json.loads(json.dumps(payload)),
                "hash": step_hash,
                "timestamp": self._deterministic_timestamp(step_hash),
            }
            self._state.setdefault("steps", []).append(record)
            self._persist_state()
        return step_hash

    def _flush_pending_steps(self) -> List[str]:
        with self._lock:
            pending = list(self._state.setdefault("pending_steps", []))
            self._state["pending_steps"] = []
            self._persist_state()
        return pending

    def _assemble_pipeline_proof(self, steps: Sequence[str]) -> str:
        base = self._state.setdefault(
            "pipeline_base",
            {
                "H_embed": "0" * 64,
                "H_solve": "0" * 64,
                "H_gate": "0" * 64,
                "H_index": "0" * 64,
            },
        )
        material = "".join(
            [
                base["H_embed"],
                base["H_solve"],
                base["H_gate"],
                base["H_index"],
                *steps,
            ]
        ).encode("utf-8")
        return _sha256_bytes(material)

    def _compute_hdag_head(self, graph: Mapping[str, Any]) -> str:
        nodes = [
            {
                "id": node_id,
                "theta": data.get("theta"),
                "tensor": data.get("tensor"),
                "index": data.get("index"),
            }
            for node_id, data in sorted(graph.get("nodes", {}).items())
        ]
        edges = [
            {
                "from": edge.get("from"),
                "to": edge.get("to"),
                "weight": edge.get("weight"),
            }
            for edge in graph.get("edges", [])
        ]
        payload = {"nodes": nodes, "edges": edges}
        return _sha256_bytes(_stable_json(payload))

    def _seed_step_hashes(self, histories: Sequence[Sequence[float]]) -> List[str]:
        index = self._state.get("steps", [])
        lookup: Dict[Tuple[str, ...], str] = {}
        for entry in index:
            if entry.get("step") != "SPIRAL_WRITE":
                continue
            coords = entry.get("payload", {}).get("x5")
            if coords is None:
                continue
            key = self._coords_key(coords)
            lookup.setdefault(key, entry.get("hash"))

        seeds: List[str] = []
        for vector in histories:
            key = self._coords_key(vector)
            step_hash = lookup.get(key)
            if step_hash:
                seeds.append(step_hash)
        return seeds

    @staticmethod
    def _coords_key(vector: Sequence[float]) -> Tuple[str, ...]:
        return tuple(f"{float(value):.12f}" for value in vector)

    @staticmethod
    def _deterministic_timestamp(seed: str) -> str:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        offset_ms = int(digest[:12], 16) % 86400000
        return (ISO_EPOCH + timedelta(milliseconds=offset_ms)).isoformat() + "Z"


__all__ = ["SpiralCouplingEngine", "SpiralParameters", "ResonanceMetric"]
