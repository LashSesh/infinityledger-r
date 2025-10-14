"""Tests for recall_eval.py corpus validation logic."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

# Add parent directories to path
import sys
SCRIPT_DIR = Path(__file__).resolve().parent
MEF_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(MEF_ROOT))

from tests.bench import recall_eval


def test_corpus_validation_detects_duplicate_ids() -> None:
    """Test that _load_corpus raises error when duplicate IDs are present."""
    # Create a temporary corpus with duplicate IDs
    ids = np.array(["id-001", "id-002", "id-003", "id-002", "id-005"], dtype="<U10")
    vectors = np.random.randn(5, 5).astype("float32")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        corpus_path = Path(tmpdir) / "corpus.npz"
        np.savez(corpus_path, ids=ids, vectors=vectors)
        
        # Temporarily override the CORPUS_PATH
        original_corpus_path = recall_eval.CORPUS_PATH
        try:
            recall_eval.CORPUS_PATH = corpus_path
            recall_eval.BENCH_POINTS = 5
            
            with pytest.raises(RuntimeError) as exc_info:
                recall_eval._load_corpus()
            
            error_msg = str(exc_info.value)
            assert "duplicate truth_ids" in error_msg.lower()
            assert "data ingestion error" in error_msg.lower()
            assert "datasets.py" in error_msg
        finally:
            recall_eval.CORPUS_PATH = original_corpus_path


def test_corpus_validation_detects_identical_vectors() -> None:
    """Test that _load_corpus raises error when identical vectors are present."""
    # Create a corpus with some identical vectors
    vectors = np.array([
        [1.0, 2.0, 3.0, 4.0, 5.0],
        [2.0, 3.0, 4.0, 5.0, 6.0],
        [1.0, 2.0, 3.0, 4.0, 5.0],  # Duplicate of first
        [3.0, 4.0, 5.0, 6.0, 7.0],
        [2.0, 3.0, 4.0, 5.0, 6.0],  # Duplicate of second
    ], dtype="float32")
    ids = np.array(["id-001", "id-002", "id-003", "id-004", "id-005"], dtype="<U10")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        corpus_path = Path(tmpdir) / "corpus.npz"
        np.savez(corpus_path, ids=ids, vectors=vectors)
        
        original_corpus_path = recall_eval.CORPUS_PATH
        try:
            recall_eval.CORPUS_PATH = corpus_path
            recall_eval.BENCH_POINTS = 5
            
            with pytest.raises(RuntimeError) as exc_info:
                recall_eval._load_corpus()
            
            error_msg = str(exc_info.value)
            assert "identical vectors" in error_msg.lower()
            assert "trivial" in error_msg.lower() or "degenerate" in error_msg.lower()
            assert "sample duplicate vector ids" in error_msg.lower()
        finally:
            recall_eval.CORPUS_PATH = original_corpus_path


def test_corpus_validation_accepts_valid_corpus() -> None:
    """Test that _load_corpus succeeds with valid corpus."""
    # Create a valid corpus with unique IDs and vectors
    vectors = np.random.randn(5, 5).astype("float32")
    # Ensure vectors are different
    for i in range(len(vectors)):
        vectors[i] += i * 0.1
    ids = np.array([f"id-{i:03d}" for i in range(5)], dtype="<U10")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        corpus_path = Path(tmpdir) / "corpus.npz"
        np.savez(corpus_path, ids=ids, vectors=vectors)
        
        original_corpus_path = recall_eval.CORPUS_PATH
        original_bench_report_path = recall_eval.BENCH_REPORT_PATH
        try:
            recall_eval.CORPUS_PATH = corpus_path
            recall_eval.BENCH_POINTS = 5
            # Ensure bench report doesn't exist for this test
            recall_eval.BENCH_REPORT_PATH = Path(tmpdir) / "nonexistent.json"
            
            result = recall_eval._load_corpus()
            
            assert "ids" in result
            assert "vectors" in result
            assert "metric" in result
            assert "normalised" in result
            assert len(result["ids"]) == 5
            assert result["vectors"].shape[0] == 5
        finally:
            recall_eval.CORPUS_PATH = original_corpus_path
            recall_eval.BENCH_REPORT_PATH = original_bench_report_path


def test_select_queries_stratified_sampling() -> None:
    """Test that _select_queries uses stratified sampling for diversity."""
    ids = [f"id-{i:04d}" for i in range(1000)]
    
    # Set EFFECTIVE_Q to a reasonable value for testing
    original_effective_q = recall_eval.EFFECTIVE_Q
    try:
        recall_eval.EFFECTIVE_Q = 10
        indices = recall_eval._select_queries(ids, 1000)
        
        # Should return exactly EFFECTIVE_Q indices
        assert len(indices) == 10
        
        # Indices should be spread across the corpus (stratified sampling)
        # With 10 queries and 1000 items, each segment is ~100 items
        # So indices should be roughly distributed across the range
        sorted_indices = sorted(indices)
        
        # Check that indices span a good range (not all clustered)
        range_span = sorted_indices[-1] - sorted_indices[0]
        # Should span at least 50% of the corpus
        assert range_span >= 500, f"Indices not diverse enough: {sorted_indices}"
        
        # All indices should be unique
        assert len(set(indices)) == len(indices)
        
        # All indices should be valid
        assert all(0 <= idx < 1000 for idx in indices)
    finally:
        recall_eval.EFFECTIVE_Q = original_effective_q


def test_select_queries_deterministic() -> None:
    """Test that _select_queries produces deterministic results with same seed."""
    ids = [f"id-{i:04d}" for i in range(1000)]
    
    original_effective_q = recall_eval.EFFECTIVE_Q
    original_bench_seed = recall_eval.BENCH_SEED
    try:
        recall_eval.EFFECTIVE_Q = 10
        recall_eval.BENCH_SEED = 42
        
        # Run twice with same seed
        indices1 = recall_eval._select_queries(ids, 1000)
        indices2 = recall_eval._select_queries(ids, 1000)
        
        # Should produce identical results
        assert indices1 == indices2
    finally:
        recall_eval.EFFECTIVE_Q = original_effective_q
        recall_eval.BENCH_SEED = original_bench_seed


def test_select_queries_validates_limit() -> None:
    """Test that _select_queries validates limit against available IDs."""
    ids = [f"id-{i:03d}" for i in range(10)]
    
    original_effective_q = recall_eval.EFFECTIVE_Q
    try:
        recall_eval.EFFECTIVE_Q = 5
        
        # Should raise error when limit exceeds available IDs
        with pytest.raises(RuntimeError) as exc_info:
            recall_eval._select_queries(ids, 100)
        
        assert "exceeds available ids" in str(exc_info.value).lower()
    finally:
        recall_eval.EFFECTIVE_Q = original_effective_q


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
