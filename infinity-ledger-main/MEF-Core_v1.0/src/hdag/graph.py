"""
HDAG (Hyperdimensional Directed Acyclic Graph) implementation.
Couples linear event time with spiral phases while maintaining path invariance.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Set
import numpy as np
import hashlib
from collections import deque

class HDAG:
    """
    Hyperdimensional DAG coupling linear time with spiral phases.
    Ensures path invariance and topological ordering.
    """
    
    def __init__(self, store_path: str = "C:/MEF/store"):
        """
        Initialize HDAG.
        
        Args:
            store_path: Storage directory path
        """
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        # HDAG storage file
        self.hdag_file = self.store_path / "hdag.json"
        
        # Load or initialize graph
        self.graph = self._load_graph()
        
        # Caches for performance
        self._topological_order_cache = None
        self._path_invariants_cache = {}
    
    def _load_graph(self) -> Dict[str, Any]:
        """
        Load HDAG from disk.
        
        Returns:
            Graph structure
        """
        if self.hdag_file.exists():
            with open(self.hdag_file, 'r') as f:
                return json.load(f)
        
        return {
            "nodes": {},
            "edges": {},
            "metadata": {
                "created": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
                "version": "1.0.0"
            }
        }
    
    def _save_graph(self):
        """Save HDAG to disk."""
        self.graph["metadata"]["last_updated"] = datetime.utcnow().isoformat()
        with open(self.hdag_file, 'w') as f:
            json.dump(self.graph, f, indent=2)
        
        # Invalidate caches
        self._topological_order_cache = None
        self._path_invariants_cache.clear()
    
    def create_node(self,
                   snapshot_id: str,
                   phase: float,
                   timestamp: Optional[str] = None,
                   node_id: Optional[str] = None) -> str:
        """
        Create a new HDAG node.
        
        Args:
            snapshot_id: Associated snapshot UUID
            phase: Spiral phase parameter
            timestamp: ISO timestamp (auto-generated if None)
            
        Returns:
            Node ID
        """
        node_id = node_id or f"N-{snapshot_id}"
        
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()
        
        node = {
            "id": node_id,
            "snapshot_id": snapshot_id,
            "phase": phase,
            "time": timestamp
        }
        
        self.graph["nodes"][node_id] = node
        self._save_graph()

        return node_id

    def _ensure_node(self, snapshot: Dict[str, Any]) -> str:
        node_id = snapshot.get("hdag_node")
        if node_id and node_id in self.graph["nodes"]:
            return node_id
        node_id = self.create_node(
            snapshot["id"],
            snapshot["phase"],
            snapshot.get("timestamp"),
            node_id=node_id
        )
        snapshot["hdag_node"] = node_id
        return node_id
    
    def create_edge(self,
                   from_node: str,
                   to_node: str,
                   weight: float,
                   cause: str = "transform") -> str:
        """
        Create an edge between nodes.
        
        Args:
            from_node: Source node ID
            to_node: Target node ID
            weight: Edge weight (typically Phi value)
            cause: Transformation cause
            
        Returns:
            Edge ID or None if edge would create cycle
        """
        # Check nodes exist
        if from_node not in self.graph["nodes"] or to_node not in self.graph["nodes"]:
            raise ValueError(f"Node not found: {from_node} or {to_node}")
        
        # Check temporal ordering
        time_from = datetime.fromisoformat(self.graph["nodes"][from_node]["time"])
        time_to = datetime.fromisoformat(self.graph["nodes"][to_node]["time"])
        
        if time_from >= time_to:
            raise ValueError(f"Invalid temporal ordering: {time_from} >= {time_to}")
        
        # Check for cycle
        if self._would_create_cycle(from_node, to_node):
            return None
        
        edge_id = f"E-{uuid.uuid4()}"
        
        edge = {
            "id": edge_id,
            "from": from_node,
            "to": to_node,
            "weight": weight,
            "cause": cause
        }
        
        self.graph["edges"][edge_id] = edge
        self._save_graph()
        
        return edge_id
    
    def _would_create_cycle(self, from_node: str, to_node: str) -> bool:
        """
        Check if adding edge would create a cycle.
        
        Args:
            from_node: Source node
            to_node: Target node
            
        Returns:
            True if edge would create cycle
        """
        # DFS to check if we can reach from_node from to_node
        visited = set()
        stack = [to_node]
        
        while stack:
            current = stack.pop()
            
            if current == from_node:
                return True
            
            if current in visited:
                continue
            
            visited.add(current)
            
            # Find outgoing edges
            for edge in self.graph["edges"].values():
                if edge["from"] == current:
                    stack.append(edge["to"])
        
        return False
    
    def get_topological_order(self) -> List[str]:
        """
        Get topological ordering of nodes.
        
        Returns:
            List of node IDs in topological order
        """
        if self._topological_order_cache is not None:
            return self._topological_order_cache
        
        # Build adjacency list
        adj_list = {node_id: [] for node_id in self.graph["nodes"]}
        in_degree = {node_id: 0 for node_id in self.graph["nodes"]}
        
        for edge in self.graph["edges"].values():
            adj_list[edge["from"]].append(edge["to"])
            in_degree[edge["to"]] += 1
        
        # Kahn's algorithm
        queue = deque([node for node, degree in in_degree.items() if degree == 0])
        topo_order = []
        
        while queue:
            node = queue.popleft()
            topo_order.append(node)
            
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        if len(topo_order) != len(self.graph["nodes"]):
            # Cycle detected
            return []
        
        self._topological_order_cache = topo_order
        return topo_order
    
    def compute_phi(self, node1_id: str, node2_id: str) -> float:
        """
        Compute order parameter Phi between two nodes.
        
        Args:
            node1_id: First node ID
            node2_id: Second node ID
            
        Returns:
            Phi value
        """
        node1 = self.graph["nodes"].get(node1_id)
        node2 = self.graph["nodes"].get(node2_id)
        
        if not node1 or not node2:
            return 0.0
        
        # Phi based on phase difference and time difference
        phase_diff = abs(node2["phase"] - node1["phase"])
        
        time1 = datetime.fromisoformat(node1["time"])
        time2 = datetime.fromisoformat(node2["time"])
        time_diff = abs((time2 - time1).total_seconds())
        
        # Normalize
        phase_factor = np.exp(-phase_diff / (2 * np.pi))
        time_factor = 1.0 / (1 + time_diff / 3600)  # Hour scale
        
        phi = phase_factor * time_factor
        
        return float(phi)
    
    def update_hdag(self, 
                   snapshot_i: Dict[str, Any],
                   snapshot_j: Dict[str, Any]) -> Optional[str]:
        """
        Update HDAG with new snapshot transition.
        
        Args:
            snapshot_i: Earlier snapshot
            snapshot_j: Later snapshot
            
        Returns:
            Edge ID or None if update failed
        """
        # Create or find nodes first
        node_i_id = self._ensure_node(snapshot_i)
        node_j_id = self._ensure_node(snapshot_j)

        # Verify temporal ordering
        time_i = datetime.fromisoformat(snapshot_i["timestamp"])
        time_j = datetime.fromisoformat(snapshot_j["timestamp"])

        if time_i >= time_j:
            return None

        # Compute weight
        weight = self.compute_phi(node_i_id, node_j_id)

        # Create edge
        edge_id = self.create_edge(node_i_id, node_j_id, weight, "transform")
        
        return edge_id
    
    def verify_path_invariance(self, 
                              start_node: str,
                              end_node: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify path invariance between two nodes.
        
        Args:
            start_node: Starting node ID
            end_node: Ending node ID
            
        Returns:
            Tuple of (is_invariant, path_data)
        """
        # Find all paths from start to end
        paths = self._find_all_paths(start_node, end_node)
        
        if not paths:
            return False, {"error": "No path exists", "paths": []}
        
        # Compute path weights
        path_weights = []
        for path in paths:
            weight = self._compute_path_weight(path)
            path_weights.append(weight)
        
        # Check invariance (all paths should have similar weight)
        if path_weights:
            mean_weight = np.mean(path_weights)
            std_weight = np.std(path_weights)
            
            # Invariance criterion: low variance
            is_invariant = std_weight / (mean_weight + 1e-10) < 0.1
        else:
            is_invariant = False
        
        return is_invariant, {
            "paths": paths,
            "weights": path_weights,
            "mean_weight": float(mean_weight) if path_weights else 0,
            "std_weight": float(std_weight) if path_weights else 0,
            "invariant": is_invariant
        }
    
    def _find_all_paths(self, 
                       start: str, 
                       end: str,
                       max_paths: int = 10) -> List[List[str]]:
        """
        Find all paths between two nodes (limited).
        
        Args:
            start: Start node ID
            end: End node ID
            max_paths: Maximum number of paths to find
            
        Returns:
            List of paths (each path is a list of node IDs)
        """
        if start == end:
            return [[start]]
        
        paths = []
        stack = [(start, [start])]
        
        while stack and len(paths) < max_paths:
            node, path = stack.pop()
            
            # Find outgoing edges
            for edge in self.graph["edges"].values():
                if edge["from"] == node:
                    next_node = edge["to"]
                    
                    if next_node not in path:  # Avoid cycles
                        new_path = path + [next_node]
                        
                        if next_node == end:
                            paths.append(new_path)
                        else:
                            stack.append((next_node, new_path))
        
        return paths
    
    def _compute_path_weight(self, path: List[str]) -> float:
        """
        Compute aggregate weight of a path.
        
        Args:
            path: List of node IDs
            
        Returns:
            Path weight
        """
        if len(path) < 2:
            return 0.0
        
        total_weight = 0.0
        
        for i in range(len(path) - 1):
            # Find edge between consecutive nodes
            for edge in self.graph["edges"].values():
                if edge["from"] == path[i] and edge["to"] == path[i + 1]:
                    total_weight += edge["weight"]
                    break
        
        return total_weight
    
    def get_node_ancestors(self, node_id: str) -> Set[str]:
        """
        Get all ancestor nodes.
        
        Args:
            node_id: Target node ID
            
        Returns:
            Set of ancestor node IDs
        """
        ancestors = set()
        stack = [node_id]
        
        while stack:
            current = stack.pop()
            
            for edge in self.graph["edges"].values():
                if edge["to"] == current and edge["from"] not in ancestors:
                    ancestors.add(edge["from"])
                    stack.append(edge["from"])
        
        return ancestors
    
    def get_node_descendants(self, node_id: str) -> Set[str]:
        """
        Get all descendant nodes.
        
        Args:
            node_id: Source node ID
            
        Returns:
            Set of descendant node IDs
        """
        descendants = set()
        stack = [node_id]
        
        while stack:
            current = stack.pop()
            
            for edge in self.graph["edges"].values():
                if edge["from"] == current and edge["to"] not in descendants:
                    descendants.add(edge["to"])
                    stack.append(edge["to"])
        
        return descendants
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get HDAG statistics.
        
        Returns:
            Dictionary with graph metrics
        """
        num_nodes = len(self.graph["nodes"])
        num_edges = len(self.graph["edges"])
        
        # Compute connectivity
        if num_nodes > 0:
            max_edges = num_nodes * (num_nodes - 1) / 2
            connectivity = num_edges / max_edges if max_edges > 0 else 0
        else:
            connectivity = 0
        
        # Check for cycles
        topo_order = self.get_topological_order()
        is_acyclic = len(topo_order) == num_nodes
        
        return {
            "nodes": num_nodes,
            "edges": num_edges,
            "connectivity": float(connectivity),
            "is_acyclic": is_acyclic,
            "metadata": self.graph["metadata"]
        }
    
    def export_graph(self, format: str = "json") -> str:
        """
        Export graph in specified format.
        
        Args:
            format: Export format ("json" or "dot")
            
        Returns:
            Exported graph string
        """
        if format == "json":
            return json.dumps(self.graph, indent=2)
        
        elif format == "dot":
            # GraphViz DOT format
            lines = ["digraph HDAG {"]
            
            # Add nodes
            for node_id, node in self.graph["nodes"].items():
                label = f"{node_id}\\nφ={node['phase']:.2f}"
                lines.append(f'  "{node_id}" [label="{label}"];')
            
            # Add edges
            for edge in self.graph["edges"].values():
                weight_label = f"{edge['weight']:.2f}"
                lines.append(f'  "{edge["from"]}" -> "{edge["to"]}" [label="{weight_label}"];')
            
            lines.append("}")
            return "\n".join(lines)
        
        else:
            raise ValueError(f"Unsupported format: {format}")