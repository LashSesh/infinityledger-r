"""
Spiral Storage management for 5D snapshots.
File-based persistence with indexing and retrieval.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import hashlib

class SpiralStorage:
    """
    Storage backend for Spiral snapshots.
    Manages file-based persistence and indexing.
    """
    
    def __init__(self, store_path: str = "C:/MEF/store"):
        """
        Initialize storage system.
        
        Args:
            store_path: Root directory for storage
        """
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        # Index file for quick lookups
        self.index_file = self.store_path / "index.json"
        self.index = self._load_index()
    
    def _load_index(self) -> Dict[str, Any]:
        """
        Load storage index from disk.
        
        Returns:
            Index dictionary
        """
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                return json.load(f)
        return {
            "snapshots": {},
            "tics": {},
            "metadata": {
                "created": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
                "version": "1.0.0"
            }
        }
    
    def _save_index(self):
        """Save index to disk."""
        self.index["metadata"]["last_updated"] = datetime.utcnow().isoformat()
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def store_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """
        Store a snapshot and update index.
        
        Args:
            snapshot: Snapshot data
            
        Returns:
            File path of stored snapshot
        """
        snapshot_id = snapshot["id"]
        file_path = self.store_path / f"{snapshot_id}.spiral"
        
        # Write snapshot file
        with open(file_path, 'w') as f:
            json.dump(snapshot, f, indent=2)
        
        # Update index
        self.index["snapshots"][snapshot_id] = {
            "id": snapshot_id,
            "timestamp": snapshot["timestamp"],
            "seed": snapshot["seed"],
            "phase": snapshot["phase"],
            "por": snapshot["metrics"]["por"],
            "file": str(file_path.relative_to(self.store_path))
        }
        self._save_index()
        
        return str(file_path)
    
    def retrieve_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a snapshot by ID.
        
        Args:
            snapshot_id: Snapshot UUID
            
        Returns:
            Snapshot data or None
        """
        file_path = self.store_path / f"{snapshot_id}.spiral"
        
        if not file_path.exists():
            return None
        
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def list_snapshots(self, 
                      seed: Optional[str] = None,
                      por_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List snapshots with optional filtering.
        
        Args:
            seed: Filter by seed
            por_filter: Filter by PoR status ("valid" or "invalid")
            
        Returns:
            List of snapshot metadata
        """
        results = []
        
        for snap_id, metadata in self.index["snapshots"].items():
            # Apply filters
            if seed and metadata.get("seed") != seed:
                continue
            if por_filter and metadata.get("por") != por_filter:
                continue
            
            results.append(metadata)
        
        # Sort by timestamp
        results.sort(key=lambda x: x.get("timestamp", ""))
        
        return results
    
    def store_tic(self, tic: Dict[str, Any]) -> str:
        """
        Store a TIC and update index.
        
        Args:
            tic: TIC data
            
        Returns:
            File path of stored TIC
        """
        tic_id = tic["tic_id"]
        file_path = self.store_path / f"{tic_id}.tic"
        
        # Write TIC file
        with open(file_path, 'w') as f:
            json.dump(tic, f, indent=2)
        
        # Update index
        self.index["tics"][tic_id] = {
            "id": tic_id,
            "seed": tic["seed"],
            "source_snapshot": tic["source_snapshot"],
            "window": tic["window"],
            "por": tic["proof"]["por"],
            "file": str(file_path.relative_to(self.store_path))
        }
        self._save_index()
        
        return str(file_path)
    
    def retrieve_tic(self, tic_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a TIC by ID.
        
        Args:
            tic_id: TIC UUID
            
        Returns:
            TIC data or None
        """
        file_path = self.store_path / f"{tic_id}.tic"
        
        if not file_path.exists():
            return None
        
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dictionary with storage metrics
        """
        snapshot_files = list(self.store_path.glob("*.spiral"))
        tic_files = list(self.store_path.glob("*.tic"))
        
        total_size = sum(f.stat().st_size for f in snapshot_files + tic_files)
        
        return {
            "snapshots": {
                "count": len(snapshot_files),
                "indexed": len(self.index.get("snapshots", {}))
            },
            "tics": {
                "count": len(tic_files),
                "indexed": len(self.index.get("tics", {}))
            },
            "storage": {
                "total_files": len(snapshot_files) + len(tic_files),
                "total_size_bytes": total_size,
                "total_size_mb": total_size / (1024 * 1024)
            },
            "metadata": self.index.get("metadata", {})
        }
    
    def verify_integrity(self) -> Dict[str, Any]:
        """
        Verify storage integrity.
        
        Returns:
            Integrity check results
        """
        results = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Check indexed snapshots exist
        for snap_id in self.index.get("snapshots", {}):
            file_path = self.store_path / f"{snap_id}.spiral"
            if not file_path.exists():
                results["errors"].append(f"Missing snapshot file: {snap_id}")
                results["valid"] = False
        
        # Check indexed TICs exist
        for tic_id in self.index.get("tics", {}):
            file_path = self.store_path / f"{tic_id}.tic"
            if not file_path.exists():
                results["errors"].append(f"Missing TIC file: {tic_id}")
                results["valid"] = False
        
        # Check for orphaned files
        for file_path in self.store_path.glob("*.spiral"):
            snap_id = file_path.stem
            if snap_id not in self.index.get("snapshots", {}):
                results["warnings"].append(f"Unindexed snapshot: {snap_id}")
        
        for file_path in self.store_path.glob("*.tic"):
            tic_id = file_path.stem
            if tic_id not in self.index.get("tics", {}):
                results["warnings"].append(f"Unindexed TIC: {tic_id}")
        
        return results
    
    def cleanup_orphaned_files(self) -> int:
        """
        Remove unindexed files.
        
        Returns:
            Number of files removed
        """
        removed_count = 0
        
        # Find and remove orphaned snapshots
        for file_path in self.store_path.glob("*.spiral"):
            snap_id = file_path.stem
            if snap_id not in self.index.get("snapshots", {}):
                file_path.unlink()
                removed_count += 1
        
        # Find and remove orphaned TICs
        for file_path in self.store_path.glob("*.tic"):
            tic_id = file_path.stem
            if tic_id not in self.index.get("tics", {}):
                file_path.unlink()
                removed_count += 1
        
        return removed_count