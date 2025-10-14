"""Driver implementations used by the benchmark compare runner."""

from .base import DriverUnavailable, UpsertItem, Vector, VectorStoreDriver
from .elastic_driver import ElasticDriver
from .faiss_baseline import FaissBaselineDriver
from .mef_driver import MEFDriver
from .milvus_driver import MilvusDriver
from .pinecone_driver import PineconeDriver
from .qdrant_driver import QdrantDriver
from .weaviate_driver import WeaviateDriver

DRIVER_REGISTRY = {
    "mef": MEFDriver,
    "faiss": FaissBaselineDriver,
    "qdrant": QdrantDriver,
    "milvus": MilvusDriver,
    "weaviate": WeaviateDriver,
    "elastic": ElasticDriver,
    "pinecone": PineconeDriver,
}

__all__ = [
    "DRIVER_REGISTRY",
    "DriverUnavailable",
    "UpsertItem",
    "Vector",
    "VectorStoreDriver",
    "ElasticDriver",
    "FaissBaselineDriver",
    "MEFDriver",
    "MilvusDriver",
    "PineconeDriver",
    "QdrantDriver",
    "WeaviateDriver",
]
