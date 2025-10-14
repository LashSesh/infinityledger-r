"""
MEF Ledger implementation with hash-chained blocks.
Immutable audit log for TICs with deterministic hashing.
"""

import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
try:
    import jsonschema
except ImportError:  # pragma: no cover - optional dependency
    jsonschema = None

class MEFLedger:
    """
    MEF Ledger system implementing hash-chained blocks.
    B_i = H(tic_i, snapshot_i, B_{i-1})
    """
    
    def __init__(self, ledger_path: str = "C:/MEF/ledger"):
        """
        Initialize MEF Ledger.
        
        Args:
            ledger_path: Directory for ledger storage
        """
        self.ledger_path = Path(ledger_path)
        self.ledger_path.mkdir(parents=True, exist_ok=True)
        
        # Ledger index file
        self.index_file = self.ledger_path / "ledger_index.json"
        self.index = self._load_index()
        
        # Load schema for validation
        schema_path = Path(__file__).parent.parent / "schemas" / "mef_block.json"
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)
        else:
            self.schema = None
        
        # Genesis block hash (if no blocks exist)
        self.genesis_hash = "0" * 64
    
    def _load_index(self) -> Dict[str, Any]:
        """
        Load ledger index from disk.
        
        Returns:
            Ledger index dictionary
        """
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                return json.load(f)
        
        return {
            "blocks": [],
            "current_index": -1,
            "metadata": {
                "created": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
                "version": "1.0.0"
            }
        }
    
    def _save_index(self):
        """Save ledger index to disk."""
        self.index["metadata"]["last_updated"] = datetime.utcnow().isoformat()
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def compute_block_hash(self, block_data: Dict[str, Any]) -> str:
        """
        Compute SHA256 hash of block data.
        
        Args:
            block_data: Block dictionary (without hash field)
            
        Returns:
            Hex string of SHA256 hash
        """
        # Create deterministic string representation
        # Remove hash field if present
        data_to_hash = {k: v for k, v in block_data.items() if k != 'hash'}
        
        # Sort keys for deterministic ordering
        block_str = json.dumps(data_to_hash, sort_keys=True, separators=(',', ':'))
        
        # Compute SHA256
        return hashlib.sha256(block_str.encode()).hexdigest()
    
    def get_last_block(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent block in the ledger.
        
        Returns:
            Last block data or None if ledger is empty
        """
        if self.index["current_index"] < 0:
            return None
        
        block_file = self.ledger_path / f"block_{self.index['current_index']:06d}.mef"
        if block_file.exists():
            with open(block_file, 'r') as f:
                return json.load(f)
        
        return None
    
    def get_last_hash(self) -> str:
        """
        Get hash of the last block.
        
        Returns:
            Hash string or genesis hash if ledger is empty
        """
        last_block = self.get_last_block()
        if last_block:
            return last_block['hash']
        return self.genesis_hash
    
    def compact_tic_data(self, tic: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create compact representation of TIC for ledger storage.
        
        Args:
            tic: Full TIC data
            
        Returns:
            Compact TIC representation
        """
        return {
            "tic_id": tic["tic_id"],
            "seed": tic["seed"],
            "fixpoint_norm": float(sum(x**2 for x in tic["fixpoint"])**0.5),
            "invariants": tic["invariants"],
            "sigma_bar": tic["sigma_bar"],
            "window": tic["window"]
        }
    
    def create_block(self,
                    tic: Dict[str, Any],
                    snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new MEF block.
        
        Args:
            tic: TIC data
            snapshot: Snapshot data
            
        Returns:
            New block dictionary
        """
        # Get next index
        next_index = self.index["current_index"] + 1
        
        # Get previous hash
        previous_hash = self.get_last_hash()
        
        # Compute snapshot hash
        snapshot_str = json.dumps(snapshot, sort_keys=True)
        snapshot_hash = hashlib.sha256(snapshot_str.encode()).hexdigest()
        
        # Create block structure
        block = {
            "index": next_index,
            "previous_hash": previous_hash,
            "timestamp": datetime.utcnow().isoformat(),
            "tic_id": tic["tic_id"],
            "snapshot_hash": snapshot_hash,
            "data": self.compact_tic_data(tic),
            "proof": tic["proof"]
        }
        
        # Compute block hash
        block["hash"] = self.compute_block_hash(block)
        
        # Validate against schema if available
        if self.schema and jsonschema:
            try:
                jsonschema.validate(instance=block, schema=self.schema)
            except jsonschema.exceptions.ValidationError as e:
                print(f"Block schema validation warning: {e}")
        
        return block
    
    def append_block(self, 
                    tic: Dict[str, Any],
                    snapshot: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Append a new block to the ledger.
        
        Args:
            tic: TIC data
            snapshot: Snapshot data
            
        Returns:
            Tuple of (success, block data or error info)
        """
        try:
            # Create new block
            block = self.create_block(tic, snapshot)
            
            # Verify chain integrity before appending
            if not self.verify_chain_integrity():
                return False, {"error": "Chain integrity check failed"}
            
            # Save block to disk
            block_file = self.ledger_path / f"block_{block['index']:06d}.mef"
            with open(block_file, 'w') as f:
                json.dump(block, f, indent=2)
            
            # Update index
            self.index["blocks"].append({
                "index": block["index"],
                "hash": block["hash"],
                "tic_id": block["tic_id"],
                "timestamp": block["timestamp"],
                "file": str(block_file.name)
            })
            self.index["current_index"] = block["index"]
            self._save_index()
            
            return True, block
            
        except Exception as e:
            return False, {"error": str(e)}
    
    def get_block(self, index: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a block by index.
        
        Args:
            index: Block index
            
        Returns:
            Block data or None if not found
        """
        block_file = self.ledger_path / f"block_{index:06d}.mef"
        
        if not block_file.exists():
            return None
        
        with open(block_file, 'r') as f:
            return json.load(f)
    
    def verify_block_hash(self, block: Dict[str, Any]) -> bool:
        """
        Verify that a block's hash is correct.
        
        Args:
            block: Block data
            
        Returns:
            True if hash is valid
        """
        stored_hash = block.get('hash', '')
        computed_hash = self.compute_block_hash(block)
        return stored_hash == computed_hash
    
    def verify_chain_integrity(self, start_index: int = 0) -> bool:
        """
        Verify integrity of the entire chain or from a specific index.
        
        Args:
            start_index: Starting block index for verification
            
        Returns:
            True if chain is valid
        """
        if self.index["current_index"] < 0:
            # Empty ledger is valid
            return True
        
        prev_hash = self.genesis_hash if start_index == 0 else None
        
        for i in range(start_index, self.index["current_index"] + 1):
            block = self.get_block(i)
            
            if not block:
                print(f"Missing block at index {i}")
                return False
            
            # Verify block hash
            if not self.verify_block_hash(block):
                print(f"Invalid hash for block {i}")
                return False
            
            # Verify chain linkage
            if prev_hash is not None and block['previous_hash'] != prev_hash:
                print(f"Chain break at block {i}")
                return False
            
            prev_hash = block['hash']
        
        return True
    
    def get_chain_statistics(self) -> Dict[str, Any]:
        """
        Get ledger chain statistics.
        
        Returns:
            Dictionary with chain metrics
        """
        total_blocks = self.index["current_index"] + 1 if self.index["current_index"] >= 0 else 0
        
        # Calculate chain file size
        total_size = 0
        for block_info in self.index["blocks"]:
            block_file = self.ledger_path / block_info["file"]
            if block_file.exists():
                total_size += block_file.stat().st_size
        
        # Get time range
        if total_blocks > 0:
            first_block = self.get_block(0)
            last_block = self.get_block(self.index["current_index"])
            time_range = {
                "first": first_block["timestamp"] if first_block else None,
                "last": last_block["timestamp"] if last_block else None
            }
        else:
            time_range = {"first": None, "last": None}
        
        return {
            "total_blocks": total_blocks,
            "current_index": self.index["current_index"],
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "time_range": time_range,
            "chain_valid": self.verify_chain_integrity(),
            "metadata": self.index["metadata"]
        }
    
    def export_audit_trail(self, output_file: str = None) -> str:
        """
        Export complete audit trail as JSON.
        
        Args:
            output_file: Output file path (auto-generated if None)
            
        Returns:
            Path to exported audit file
        """
        if output_file is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            output_file = self.ledger_path / f"audit_trail_{timestamp}.json"
        else:
            output_file = Path(output_file)
        
        audit_data = {
            "exported": datetime.utcnow().isoformat(),
            "chain_valid": self.verify_chain_integrity(),
            "statistics": self.get_chain_statistics(),
            "blocks": []
        }
        
        # Include all blocks
        for i in range(self.index["current_index"] + 1):
            block = self.get_block(i)
            if block:
                audit_data["blocks"].append(block)
        
        # Write audit file
        with open(output_file, 'w') as f:
            json.dump(audit_data, f, indent=2)
        
        return str(output_file)
    
    def find_blocks_by_tic(self, tic_id: str) -> List[Dict[str, Any]]:
        """
        Find all blocks containing a specific TIC.
        
        Args:
            tic_id: TIC identifier
            
        Returns:
            List of matching blocks
        """
        matching_blocks = []
        
        for block_info in self.index["blocks"]:
            if block_info.get("tic_id") == tic_id:
                block = self.get_block(block_info["index"])
                if block:
                    matching_blocks.append(block)
        
        return matching_blocks
    
    def get_block_by_hash(self, block_hash: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a block by its hash.
        
        Args:
            block_hash: Block hash
            
        Returns:
            Block data or None if not found
        """
        for block_info in self.index["blocks"]:
            if block_info.get("hash") == block_hash:
                return self.get_block(block_info["index"])
        
        return None