"""
Local Qdrant integration for retrieval chunk indexing.
"""

from __future__ import annotations

from pathlib import Path
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models


class LocalQdrantChunkStore:
    def __init__(self, *, storage_path: Path, collection_name: str) -> None:
        self._storage_path = storage_path
        self._collection_name = collection_name
        self._client = QdrantClient(path=str(storage_path))

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def collection_exists(self) -> bool:
        return self._client.collection_exists(self._collection_name)

    def ensure_collection(self, vector_size: int) -> None:
        if self.collection_exists():
            return
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )

    def upsert_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> int:
        if not chunks:
            return 0
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        self.ensure_collection(len(embeddings[0]))
        points = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"]))
            payload = {
                "chunk_id": chunk["chunk_id"],
                "document_key": chunk["document_key"],
                "company_name": chunk.get("company_name"),
                "report_year": chunk.get("report_year"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "page_keys": chunk.get("page_keys") or [],
                "evidence_keys": chunk.get("evidence_keys") or [],
                "chunk_type": chunk.get("chunk_type"),
                "section_hint": chunk.get("section_hint"),
                "content": chunk.get("content"),
                "metadata": chunk.get("metadata") or {},
            }
            points.append(models.PointStruct(id=point_id, vector=embedding, payload=payload))

        self._client.upsert(collection_name=self._collection_name, points=points)
        return len(points)

    def search(
        self,
        *,
        query_vector: list[float],
        document_key: str | None = None,
        limit: int = 8,
    ) -> list[dict]:
        query_filter = None
        if document_key is not None:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_key",
                        match=models.MatchValue(value=document_key),
                    )
                ]
            )

        results = self._client.search(
            collection_name=self._collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            {
                "id": result.id,
                "score": result.score,
                "payload": dict(result.payload or {}),
            }
            for result in results
        ]
