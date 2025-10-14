"""Asynchronous gRPC server exposing vector memory operations."""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from typing import AsyncIterable, Dict, Iterable, List, Optional

import grpc
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct

from vector_db.index_manager import IndexManager, VectorRecord
from vector_db.manifest_store import ManifestStore

from . import vector_service_pb2 as pb2
from . import vector_service_pb2_grpc as pb2_grpc


def _struct_to_dict(struct: Optional[Struct]) -> Dict[str, object]:
    if struct is None:
        return {}
    return json_format.MessageToDict(struct, preserving_proto_field_name=True)


def _dict_to_struct(payload: Optional[Dict[str, object]]) -> Struct:
    struct = Struct()
    if payload:
        struct.update(payload)
    return struct


def _cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if len(a_list) != len(b_list):
        raise ValueError("Vector dimensions do not match")

    dot = sum(x * y for x, y in zip(a_list, b_list))
    norm_a = math.sqrt(sum(x * x for x in a_list))
    norm_b = math.sqrt(sum(y * y for y in b_list))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorService(pb2_grpc.VectorServiceServicer):
    """Implementation of the VectorService gRPC contract."""

    def __init__(
        self,
        index_manager: Optional[IndexManager] = None,
        manifest_store: Optional[ManifestStore] = None,
        *,
        default_epoch: int = 0,
    ) -> None:
        self._index_manager = index_manager or IndexManager()
        self._manifest_store = manifest_store or ManifestStore(self._index_manager.base_path)
        self._default_epoch = default_epoch

    # ------------------------------------------------------------------
    async def Upsert(
        self,
        request_iterator: AsyncIterable[pb2.VectorRecord],
        context: grpc.aio.ServicerContext,
    ) -> pb2.UpsertResult:  # type: ignore[override]
        records_by_collection: Dict[str, List[VectorRecord]] = defaultdict(list)
        counts: Dict[str, int] = defaultdict(int)

        async for request in request_iterator:
            collection = request.collection or ""
            if not collection:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "collection is required")

            if not request.id:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id is required")

            metadata = _struct_to_dict(request.metadata)
            record_epoch = request.epoch if request.epoch != 0 else self._default_epoch
            vector = list(request.values)
            if not vector:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "vector values are required")

            record = VectorRecord(
                id=request.id,
                values=vector,
                metadata=metadata,
                epoch=record_epoch,
            )
            records_by_collection[collection].append(record)
            counts[collection] += 1

        updates = []
        for collection, records in records_by_collection.items():
            epoch = records[0].epoch if records else self._default_epoch
            self._index_manager.upsert_vectors(collection, records, epoch=epoch)
            updates.append(
                pb2.CollectionUpdate(
                    collection=collection,
                    upserted=counts[collection],
                    epoch=epoch if epoch is not None else 0,
                )
            )

        return pb2.UpsertResult(updates=updates)

    async def Query(self, request: pb2.QueryRequest, context: grpc.aio.ServicerContext) -> pb2.QueryResponse:  # type: ignore[override]
        collection = request.collection or ""
        if not collection:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "collection is required")

        state = self._index_manager.get_collection_state(collection)
        if not state.vectors:
            return pb2.QueryResponse()

        query_vector: Optional[List[float]] = None
        if request.vector:
            query_vector = list(request.vector)
        elif request.vector_id:
            stored = state.vectors.get(request.vector_id)
            if stored is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "vector_id not found")
            query_vector = list(stored.get("vector", []))

        if not query_vector:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "vector or vector_id must be provided")

        top_k = int(request.top_k or 5)
        if top_k <= 0:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "top_k must be positive")

        loop = asyncio.get_running_loop()

        try:
            ranked = await loop.run_in_executor(
                None,
                lambda: self._index_manager.search_vectors(
                    collection,
                    query_vector,
                    top_k=top_k,
                ),
            )
        except ValueError as exc:  # propagate dimensionality issues from providers
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        results = [
            pb2.QueryResult(
                id=item.get("id", ""),
                score=float(item.get("score", 0.0)),
                metadata=_dict_to_struct(item.get("metadata", {})),
                epoch=int(item.get("epoch", 0) or 0),
            )
            for item in ranked[:top_k]
        ]

        return pb2.QueryResponse(results=results)

    async def Delete(self, request: pb2.DeleteRequest, context: grpc.aio.ServicerContext) -> pb2.DeleteResult:  # type: ignore[override]
        collection = request.collection or ""
        if not collection:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "collection is required")

        state = self._index_manager.get_collection_state(collection)
        before = len(state.vectors)
        epoch = request.epoch if request.epoch != 0 else None
        self._index_manager.delete_vectors(collection, request.ids, epoch=epoch)
        after_state = self._index_manager.get_collection_state(collection)
        deleted = before - len(after_state.vectors)
        return pb2.DeleteResult(deleted=deleted if deleted >= 0 else 0)

    async def Seal(self, request: pb2.SealRequest, context: grpc.aio.ServicerContext) -> pb2.SealResult:  # type: ignore[override]
        collection = request.collection or ""
        if not collection:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "collection is required")

        state = self._index_manager.get_collection_state(collection)
        epoch = int(request.epoch)
        if epoch <= 0:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "epoch must be positive")
        version_dir = self._manifest_store.persist_state(collection, state, epoch=epoch)
        return pb2.SealResult(ok=True, path=str(version_dir))

    async def Switch(self, request: pb2.SwitchRequest, context: grpc.aio.ServicerContext) -> pb2.SwitchResult:  # type: ignore[override]
        collection = request.collection or ""
        if not collection:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "collection is required")

        epoch = int(request.epoch)
        if epoch <= 0:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "epoch must be positive")
        self._manifest_store.set_active_epoch(collection, epoch)
        return pb2.SwitchResult(ok=True)


async def serve(
    host: str = "0.0.0.0",
    port: int = 50051,
    *,
    index_manager: Optional[IndexManager] = None,
    manifest_store: Optional[ManifestStore] = None,
    default_epoch: int = 0,
) -> None:
    """Start the VectorService gRPC server and run until cancelled."""

    server = grpc.aio.server()
    service = VectorService(index_manager=index_manager, manifest_store=manifest_store, default_epoch=default_epoch)
    pb2_grpc.add_VectorServiceServicer_to_server(service, server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        await server.stop(0)


def run_sync(host: str = "0.0.0.0", port: int = 50051) -> None:
    """Blocking helper to start the gRPC server."""

    asyncio.run(serve(host=host, port=port))
