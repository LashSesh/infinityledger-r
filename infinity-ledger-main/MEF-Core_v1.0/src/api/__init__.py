"""Light‑weight public API helpers used across the test-suite.

The original project exposes a fully fledged FastAPI application.  The
unit tests bundled with the open-source drop, however, only require a
couple of pure-Python helpers that serialise the Metatron cube data
structures.  During the Codex review the module was reduced to merely
export the ASGI application which broke any importers expecting the
former helper functions.  In particular ``src.cube`` imports
``export_nodes_json`` and friends when serialising a cube instance, and
``tests/test_xswap.py`` monkey-patches the same names to keep the import
cheap.  With the stripped-down module those attributes no longer existed
and the import failed during test collection.

To keep the footprint minimal we provide small, dependency-free
implementations of the original helpers.  They only rely on the
``MetatronCubeGraph`` interface and basic Python types which makes them
safe to import in constrained environments.  The FastAPI application is
still exported via ``app`` for anyone wanting to spin up the HTTP
service.
"""

from __future__ import annotations

import json
from typing import Iterable, Mapping

from .server import app

__all__ = [
    "app",
    "main",
    "export_nodes_json",
    "export_edges_json",
    "export_adjacency_json",
    "export_group_json",
    "export_matrices_json",
]


def main() -> None:
    """Run the bundled FastAPI server using ``uvicorn``."""

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


def export_nodes_json(graph: "MetatronCubeGraph") -> str:
    """Serialise the nodes of ``graph`` to a JSON string.

    Parameters
    ----------
    graph:
        Instance providing a ``nodes`` attribute with the canonical node
        definitions.  ``MetatronCubeGraph`` fulfils this contract.
    """

    payload = [
        {
            "index": node.index,
            "label": node.label,
            "type": node.type,
            "coords": list(node.coords),
        }
        for node in getattr(graph, "nodes", [])
    ]
    return json.dumps(payload)


def export_edges_json(graph: "MetatronCubeGraph") -> str:
    """Serialise the undirected edge list of ``graph`` to JSON."""

    payload = [list(edge) for edge in getattr(graph, "edge_weights", {}).keys()]
    return json.dumps(payload)


def export_adjacency_json(graph: "MetatronCubeGraph") -> str:
    """Serialise the adjacency matrix of ``graph`` to JSON."""

    matrix = getattr(graph, "get_adjacency_matrix")()
    payload = matrix.tolist()
    return json.dumps(payload)


def export_group_json(group: Mapping[str, Iterable[int]]) -> str:
    """Serialise an operator group mapping to JSON."""

    payload = {name: list(permutation) for name, permutation in group.items()}
    return json.dumps(payload)


def export_matrices_json(matrices: Mapping[str, Iterable[Iterable[float]]]) -> str:
    """Serialise labelled matrices (e.g. eigenbases) to JSON."""

    payload = {name: [list(row) for row in data] for name, data in matrices.items()}
    return json.dumps(payload)