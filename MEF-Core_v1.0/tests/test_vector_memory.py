"""Tests for vector persistence and manifest replication."""

from pathlib import Path

from src.vector_db.index_manager import IndexManager, VectorRecord
from src.vector_db.manifest_store import ManifestStore


class StubS3Client:
    """Collect uploaded artefacts for assertion in tests."""

    def __init__(self) -> None:
        self.uploads = []

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.uploads.append((filename, bucket, key))


def test_vector_state_persists_across_restart(tmp_path):
    base_path = tmp_path / "vector_db"
    manager = IndexManager(base_path)

    manager.upsert_vectors(
        "memory",
        [
            VectorRecord(
                id="vec-1",
                values=[0.1, 0.2, 0.3],
                metadata={"label": "alpha"},
                epoch=1,
            )
        ],
        indexes={"faiss": {"size": 1}},
    )

    state = manager.get_collection_state("memory")
    assert "vec-1" in state.vectors
    assert state.vectors["vec-1"]["epoch"] == 1
    assert state.indexes["faiss"]["size"] == 1

    # Simulate restart by constructing a new manager with the same path
    restarted_manager = IndexManager(base_path)
    restarted_state = restarted_manager.get_collection_state("memory")
    assert restarted_state.vectors == state.vectors
    assert restarted_state.indexes["faiss"]["size"] == 1

    # Ensure deletions are also persisted
    restarted_manager.delete_vectors("memory", ["vec-1"], epoch=2)
    post_delete_manager = IndexManager(base_path)
    post_state = post_delete_manager.get_collection_state("memory")
    assert "vec-1" not in post_state.vectors
    assert post_state.indexes.get("deletion_epochs") == [2]


def test_manifest_store_syncs_to_s3(tmp_path):
    base_path = tmp_path / "vector_db"
    manager = IndexManager(base_path)
    manager.upsert_vectors(
        "memory",
        [
            VectorRecord(
                id="vec-2",
                values=[0.5, 0.4, 0.3],
                metadata={"label": "beta"},
                epoch=3,
            )
        ],
    )

    manifest_store = ManifestStore(
        base_path,
        persistence_config={
            "provider": "s3",
            "bucket": "test-bucket",
            "prefix": "indexes",
        },
        s3_client=StubS3Client(),
    )

    version_dir = manifest_store.persist_state(
        "memory", manager.get_collection_state("memory"), epoch=3
    )
    assert version_dir.exists()

    manifest = manifest_store.get_manifest()
    assert manifest.collections["memory"]["latest_epoch"] == 3

    uploads = manifest_store._s3_client.uploads  # type: ignore[attr-defined]
    assert uploads, "Expected uploads to S3"

    filenames = {Path(name).name for name, *_ in uploads}
    assert "index.json" in filenames

    keys = {key for *_, key in uploads}
    assert "indexes/memory/v3/index.json" in keys

