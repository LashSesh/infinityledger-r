"""End-to-end test for the VectorService gRPC API."""
from pathlib import Path

import asyncio
import grpc

from api.grpc import vector_service_pb2 as pb2
from api.grpc import vector_service_pb2_grpc as pb2_grpc
from api.grpc.vector_server import VectorService
from vector_db.index_manager import IndexManager
from vector_db.manifest_store import ManifestStore


def test_vector_service_lifecycle(tmp_path):
    async def runner() -> None:
        vector_path = tmp_path / "vector_db"
        manifest_path = tmp_path / "manifests"
        manager = IndexManager(vector_path)
        manifest_store = ManifestStore(manifest_path)

        server = grpc.aio.server()
        service = VectorService(index_manager=manager, manifest_store=manifest_store, default_epoch=1)
        pb2_grpc.add_VectorServiceServicer_to_server(service, server)
        port = server.add_insecure_port("127.0.0.1:0")

        await server.start()
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        stub = pb2_grpc.VectorServiceStub(channel)

        async def upsert_stream():
            records = [
                pb2.VectorRecord(collection="memory", id="vec-1", values=[0.1, 0.2, 0.3], epoch=1),
                pb2.VectorRecord(collection="memory", id="vec-2", values=[0.2, 0.4, 0.6], epoch=1),
            ]
            for record in records:
                yield record

        upsert_response = await stub.Upsert(upsert_stream())
        assert upsert_response.updates[0].collection == "memory"
        assert upsert_response.updates[0].upserted == 2

        query_response = await stub.Query(
            pb2.QueryRequest(collection="memory", vector=[0.1, 0.2, 0.3], top_k=2)
        )
        assert len(query_response.results) == 2
        assert {result.id for result in query_response.results} == {"vec-1", "vec-2"}

        delete_response = await stub.Delete(pb2.DeleteRequest(collection="memory", ids=["vec-1"], epoch=2))
        assert delete_response.deleted == 1

        seal_response = await stub.Seal(pb2.SealRequest(collection="memory", epoch=3))
        path = Path(seal_response.path)
        assert seal_response.ok
        assert path.exists()

        switch_response = await stub.Switch(pb2.SwitchRequest(collection="memory", epoch=3))
        assert switch_response.ok
        manifest = manifest_store.get_manifest()
        assert manifest.collections["memory"]["active_epoch"] == 3

        await channel.close()
        await server.stop(None)
        await server.wait_for_termination()

    asyncio.run(runner())
