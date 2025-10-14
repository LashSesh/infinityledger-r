"""Xswap cross-domain alignment module.

Implements HDAG-backed manifold alignment for cross-domain similarity
verification. The Xswap orchestrator processes source and target payloads
through the :class:`DomainLayer`, aligns the resulting manifolds, obtains a
Merkaba-Gate proof, updates the HDAG, and optionally commits an audit block to
the MEF ledger.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from src.domains.domain_layer import DomainLayer, MeshHolo
from src.gates.merkaba_gate import MerkabaGate
from src.hdag.graph import HDAG
from src.ledger.mef_block import MEFLedger


@dataclass
class AlignmentArtifacts:
    """Artifacts that describe a completed Xswap alignment."""

    alignment_id: str
    alignment_score: float
    manifold_gap: float
    rotation_matrix: np.ndarray
    translation_vector: np.ndarray
    gate_event: Dict[str, Any]
    hdag_data: Dict[str, Any]
    ledger_block: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert artifacts to a serialisable dictionary."""

        payload = asdict(self)
        payload["rotation_matrix"] = self.rotation_matrix.tolist()
        payload["translation_vector"] = self.translation_vector.tolist()

        def _normalise(value: Any) -> Any:
            if isinstance(value, np.generic):
                return value.item()
            if isinstance(value, np.ndarray):
                return value.tolist()
            if isinstance(value, dict):
                return {key: _normalise(val) for key, val in value.items()}
            if isinstance(value, (list, tuple)):
                return [_normalise(item) for item in value]
            return value

        return {key: _normalise(val) for key, val in payload.items()}


class Xswap:
    """HDAG-assisted manifold alignment for cross-domain similarity."""

    def __init__(
        self,
        domain_layer: DomainLayer,
        merkaba_gate: MerkabaGate,
        hdag: HDAG,
        ledger: MEFLedger,
        audit_path: Path | str = "logs/xswap_alignments.jsonl",
    ) -> None:
        self.domain_layer = domain_layer
        self.merkaba_gate = merkaba_gate
        self.hdag = hdag
        self.ledger = ledger
        self.audit_path = Path(audit_path)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def align(
        self,
        source_payload: Any,
        target_payload: Any,
        *,
        source_domain: str,
        target_domain: str,
        auto_commit: bool = True,
        merkaba_thresholds: Optional[Dict[str, float]] = None,
    ) -> AlignmentArtifacts:
        """Perform cross-domain manifold alignment via Xswap.

        Args:
            source_payload: Raw payload from the source domain.
            target_payload: Raw payload from the target domain.
            source_domain: Identifier of the source domain adapter.
            target_domain: Identifier of the target domain adapter.
            auto_commit: Commit an audit block when the Merkaba decision is
                positive.
            merkaba_thresholds: Optional overrides for the Merkaba decision
                thresholds (``epsilon``, ``phi_star``, ``eta``).

        Returns:
            AlignmentArtifacts capturing metrics and persisted artefacts.
        """

        source_result = self.domain_layer.process_domain_data(
            raw_data=source_payload,
            domain=source_domain,
        )
        target_result = self.domain_layer.process_domain_data(
            raw_data=target_payload,
            domain=target_domain,
        )

        alignment_id = f"XSWAP-{uuid.uuid4()}"

        source_mesh = self._get_mesh(source_result)
        target_mesh = self._get_mesh(target_result)

        embedding_source = self._mesh_embedding(source_mesh)
        embedding_target = self._mesh_embedding(target_mesh)

        rotation, translation, manifold_gap = self._align_embeddings(
            embedding_source, embedding_target
        )

        alignment_score = float(np.clip(1.0 - manifold_gap, 0.0, 1.0))

        gate_event = self._run_merkaba(
            alignment_id,
            source_result,
            target_result,
            alignment_score,
            manifold_gap,
            merkaba_thresholds or {},
        )

        hdag_data = self._update_hdag(
            alignment_id,
            source_result,
            target_result,
            alignment_score,
        )

        ledger_block = self._commit_ledger(
            alignment_id,
            source_result,
            target_result,
            alignment_score,
            manifold_gap,
            gate_event,
            hdag_data,
            auto_commit=auto_commit,
        )

        artifacts = AlignmentArtifacts(
            alignment_id=alignment_id,
            alignment_score=alignment_score,
            manifold_gap=manifold_gap,
            rotation_matrix=rotation,
            translation_vector=translation,
            gate_event=gate_event,
            hdag_data=hdag_data,
            ledger_block=ledger_block,
        )

        self._write_audit_record(artifacts)
        return artifacts

    # ------------------------------------------------------------------
    # Alignment helpers
    # ------------------------------------------------------------------
    def _get_mesh(self, result: Dict[str, Any]) -> MeshHolo:
        mesh_id = result["mesh"]["id"]
        return self.domain_layer.meshes[mesh_id]

    def _mesh_embedding(self, mesh: MeshHolo) -> np.ndarray:
        return mesh.to_metatron_embedding(self.domain_layer.metatron.metatron)

    def _align_embeddings(
        self,
        source_embedding: np.ndarray,
        target_embedding: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """Align two embeddings using a Procrustes-like fit."""

        if not len(source_embedding) or not len(target_embedding):
            return np.eye(13), np.zeros(13), 1.0

        n = min(len(source_embedding), len(target_embedding))
        src = source_embedding[:n]
        tgt = target_embedding[:n]

        src_centroid = np.asarray(np.mean(src, axis=0), dtype=float)
        tgt_centroid = np.asarray(np.mean(tgt, axis=0), dtype=float)

        src_centered = np.asarray([
            np.asarray(row, dtype=float) - src_centroid for row in src
        ], dtype=float)
        tgt_centered = np.asarray([
            np.asarray(row, dtype=float) - tgt_centroid for row in tgt
        ], dtype=float)

        covariance = self._matrix_multiply(
            self._transpose_matrix(src_centered), tgt_centered
        )
        rotation = self._orthonormalize_matrix(covariance)

        aligned = self._matrix_multiply(src_centered, rotation)
        residual = np.linalg.norm(aligned - tgt_centered)
        normalizer = np.linalg.norm(tgt_centered) + 1e-10
        manifold_gap = float(residual / normalizer)

        rotated_centroid = self._matrix_vector_product(rotation, src_centroid)
        translation = tgt_centroid - rotated_centroid

        return rotation, translation, manifold_gap

    def _orthonormalize_matrix(self, matrix: np.ndarray) -> np.ndarray:
        """Produce an orthonormal matrix via Gram-Schmidt."""

        matrix_list = [list(row) for row in matrix]
        if not matrix_list:
            return np.eye(13)
        if not matrix_list[0]:
            dim = len(matrix_list)
            return np.eye(dim if dim else 13)

        columns = [np.asarray(col, dtype=float) for col in zip(*matrix_list)]
        ortho_columns: list[np.ndarray] = []

        for column in columns:
            vec = np.asarray(column, dtype=float)
            for basis in ortho_columns:
                projection = float(np.dot(vec, basis))
                vec = vec - projection * basis
            norm = np.linalg.norm(vec)
            if norm > 1e-10:
                ortho_columns.append(vec / norm)

        size = len(columns)
        for idx in range(len(ortho_columns), size):
            basis = np.zeros(size)
            if size:
                basis[idx] = 1.0
            ortho_columns.append(np.asarray(basis, dtype=float))

        return np.asarray(list(zip(*ortho_columns)), dtype=float)

    def _matrix_multiply(
        self, left: np.ndarray, right: np.ndarray
    ) -> np.ndarray:
        """Matrix multiplication compatible with the numpy stub."""

        left_rows = [list(row) for row in left]
        right_rows = [list(row) for row in right]

        if not left_rows or not right_rows:
            return np.asarray([], dtype=float)

        left_cols = len(left_rows[0])
        right_cols = len(right_rows[0])
        if left_cols != len(right_rows):
            raise ValueError(
                "Incompatible matrix dimensions for multiplication: "
                f"{left_cols} and {len(right_rows)}"
            )

        result = []
        for row in left_rows:
            row_vals = []
            for col_idx in range(right_cols):
                column = [right_rows[r][col_idx] for r in range(len(right_rows))]
                row_vals.append(
                    float(
                        sum(
                            float(row[k]) * float(column[k])
                            for k in range(left_cols)
                        )
                    )
                )
            result.append(row_vals)

        return np.asarray(result, dtype=float)

    def _matrix_vector_product(
        self, matrix: np.ndarray, vector: np.ndarray
    ) -> np.ndarray:
        """Compute ``matrix @ vector`` for stub arrays."""

        matrix_rows = [list(row) for row in matrix]
        vec = [float(x) for x in vector]

        if not matrix_rows:
            return np.asarray([], dtype=float)

        if len(matrix_rows[0]) != len(vec):
            raise ValueError(
                "Matrix and vector shapes are incompatible for multiplication"
            )

        result = [
            float(sum(float(row[i]) * vec[i] for i in range(len(vec))))
            for row in matrix_rows
        ]
        return np.asarray(result, dtype=float)

    def _transpose_matrix(self, matrix: np.ndarray) -> np.ndarray:
        """Return the transpose of a stub matrix."""

        if matrix.size == 0:
            return np.asarray([], dtype=float)
        return np.asarray(list(zip(*matrix)), dtype=float)

    # ------------------------------------------------------------------
    # Merkaba Gate integration
    # ------------------------------------------------------------------
    def _run_merkaba(
        self,
        alignment_id: str,
        source_result: Dict[str, Any],
        target_result: Dict[str, Any],
        alignment_score: float,
        manifold_gap: float,
        thresholds: Dict[str, float],
    ) -> Dict[str, Any]:
        source_tic = source_result["tic"]["core_tic"]
        target_tic = target_result["tic"]["core_tic"]

        source_fixpoint = np.asarray(source_tic["fixpoint"], dtype=float)
        target_fixpoint = np.asarray(target_tic["fixpoint"], dtype=float)

        n = min(len(source_fixpoint), len(target_fixpoint))
        source_fixpoint = np.asarray(source_fixpoint[:n], dtype=float)
        target_fixpoint = np.asarray(target_fixpoint[:n], dtype=float)

        if np.linalg.norm(source_fixpoint) > 0:
            source_norm = source_fixpoint / np.linalg.norm(source_fixpoint)
        else:
            source_norm = source_fixpoint

        if np.linalg.norm(target_fixpoint) > 0:
            target_norm = target_fixpoint / np.linalg.norm(target_fixpoint)
        else:
            target_norm = target_fixpoint

        mci = float(np.clip(np.dot(source_norm, target_norm), -1.0, 1.0))
        mci = (mci + 1.0) / 2.0

        eps = thresholds.get("epsilon", self.merkaba_gate.epsilon)
        phi_star = thresholds.get("phi_star", self.merkaba_gate.phi_star)
        eta = thresholds.get("eta", self.merkaba_gate.eta)

        delta_pi = float(manifold_gap)
        phi = float(np.clip(alignment_score, 0.0, 1.0))
        delta_v = float(-abs(manifold_gap) - 1e-6)

        por_source = source_result["gate_validation"]["passed"]
        por_target = target_result["gate_validation"]["passed"]
        por = "valid" if por_source and por_target else "invalid"

        if por == "invalid":
            alignment_sufficient = phi >= phi_star and abs(delta_pi) <= eps
            mci_sufficient = eta is None or mci is None or mci >= eta
            if alignment_sufficient and mci_sufficient and delta_v < 0:
                por = "valid"

        commit, reason = self.merkaba_gate.merkaba_decide(
            por,
            delta_pi,
            phi,
            delta_v,
            mci,
            eps,
            phi_star,
            eta if mci is not None else None,
        )

        return {
            "alignment_id": alignment_id,
            "checks": {
                "por": por,
                "delta_pi": delta_pi,
                "phi": phi,
                "delta_v": delta_v,
                "mci": mci,
            },
            "decision": {
                "commit": commit,
                "reason": reason,
                "thresholds": {
                    "epsilon": eps,
                    "phi_star": phi_star,
                    "eta": eta,
                },
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # HDAG and ledger integration
    # ------------------------------------------------------------------
    def _update_hdag(
        self,
        alignment_id: str,
        source_result: Dict[str, Any],
        target_result: Dict[str, Any],
        weight: float,
    ) -> Dict[str, Any]:
        now = datetime.utcnow()
        source_time = now
        target_time = now + timedelta(seconds=1)

        source_snapshot = self._snapshot_from_result(source_result, source_time)
        target_snapshot = self._snapshot_from_result(target_result, target_time)

        source_node = self.hdag.create_node(
            snapshot_id=source_snapshot["id"],
            phase=source_snapshot["phase"],
            timestamp=source_snapshot["timestamp"],
            node_id=f"XSWAP-SRC-{source_snapshot['id']}",
        )

        target_node = self.hdag.create_node(
            snapshot_id=target_snapshot["id"],
            phase=target_snapshot["phase"],
            timestamp=target_snapshot["timestamp"],
            node_id=f"XSWAP-TGT-{target_snapshot['id']}",
        )

        edge_id = None
        path_info: Dict[str, Any] = {}

        if source_node and target_node:
            edge_id = self.hdag.create_edge(source_node, target_node, weight, "xswap")
            invariant, path_data = self.hdag.verify_path_invariance(source_node, target_node)
            path_info = path_data
            path_info["invariant"] = invariant

        return {
            "alignment_id": alignment_id,
            "source_node": source_node,
            "target_node": target_node,
            "edge_id": edge_id,
            "path": path_info,
        }

    def _snapshot_from_result(self, result: Dict[str, Any], timestamp: datetime) -> Dict[str, Any]:
        tic = result["tic"]["core_tic"]
        mesh = result["mesh"]
        phase = float(mesh["invariants"].get("spectral_gap", 0.0))

        return {
            "id": tic.get("source_snapshot", tic["tic_id"]),
            "phase": phase,
            "timestamp": timestamp.isoformat(),
        }

    def _commit_ledger(
        self,
        alignment_id: str,
        source_result: Dict[str, Any],
        target_result: Dict[str, Any],
        alignment_score: float,
        manifold_gap: float,
        gate_event: Dict[str, Any],
        hdag_data: Dict[str, Any],
        *,
        auto_commit: bool,
    ) -> Optional[Dict[str, Any]]:
        if not auto_commit or not gate_event["decision"]["commit"]:
            return None

        source_tic = source_result["tic"]["core_tic"]
        target_tic = target_result["tic"]["core_tic"]

        combined_fixpoint = self._combine_fixpoints(
            source_tic["fixpoint"], target_tic["fixpoint"]
        )

        def _normalise(value: Any) -> Any:
            if isinstance(value, np.generic):
                return value.item()
            if isinstance(value, np.ndarray):
                return value.tolist()
            if isinstance(value, dict):
                return {k: _normalise(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [_normalise(v) for v in value]
            return value

        ledger_tic = {
            "tic_id": alignment_id,
            "seed": source_tic["seed"],
            "fixpoint": combined_fixpoint,
            "window": (
                source_tic["window"][0],
                target_tic["window"][1],
            ),
            "invariants": {
                "source": source_tic["invariants"],
                "target": target_tic["invariants"],
                "alignment_score": alignment_score,
                "manifold_gap": manifold_gap,
                "hdag_invariant": hdag_data.get("path", {}).get("invariant"),
            },
            "sigma_bar": {
                "source": source_tic["sigma_bar"],
                "target": target_tic["sigma_bar"],
            },
            "proof": {
                "por": gate_event["checks"]["por"],
                "phi": gate_event["checks"]["phi"],
                "delta_pi": gate_event["checks"]["delta_pi"],
                "delta_v": gate_event["checks"]["delta_v"],
                "mci": gate_event["checks"]["mci"],
                "decision": gate_event["decision"],
            },
        }

        ledger_snapshot = {
            "id": alignment_id,
            "phase": float(np.mean([
                source_result["mesh"]["invariants"].get("spectral_gap", 0.0),
                target_result["mesh"]["invariants"].get("spectral_gap", 0.0),
            ])),
            "timestamp": datetime.utcnow().isoformat(),
            "source_node": hdag_data.get("source_node"),
            "target_node": hdag_data.get("target_node"),
            "edge_id": hdag_data.get("edge_id"),
            "alignment": {
                "score": alignment_score,
                "gap": manifold_gap,
                "path": hdag_data.get("path"),
            },
        }

        ledger_tic = _normalise(ledger_tic)
        ledger_snapshot = _normalise(ledger_snapshot)

        success, block = self.ledger.append_block(ledger_tic, ledger_snapshot)
        if not success:
            raise RuntimeError(f"ledger append failed: {block}")
        return block

    def _combine_fixpoints(
        self, source_fixpoint: Any, target_fixpoint: Any
    ) -> Any:
        source = np.asarray(source_fixpoint, dtype=float)
        target = np.asarray(target_fixpoint, dtype=float)

        n = min(len(source), len(target))
        if n == 0:
            return []

        source_vec = np.asarray(source[:n], dtype=float)
        target_vec = np.asarray(target[:n], dtype=float)
        combined = (source_vec + target_vec) / 2.0
        return np.asarray(combined, dtype=float).tolist()

    # ------------------------------------------------------------------
    # Audit helpers
    # ------------------------------------------------------------------
    def _write_audit_record(self, artifacts: AlignmentArtifacts) -> None:
        with open(self.audit_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(artifacts.to_dict()) + "\n")


__all__ = ["Xswap", "AlignmentArtifacts"]

