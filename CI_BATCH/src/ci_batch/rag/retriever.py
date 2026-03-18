"""
Chunk retrieval helpers for fact structuring.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qdrant_client.http import models

from ci_batch.embed.openai_embeddings import OpenAIChunkEmbedder
from ci_batch.rag.profiles import FactExtractionProfile
from ci_batch.vectordb.qdrant_store import LocalQdrantChunkStore


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: dict[str, Any]
    retrieval_mode: str
    score: float | None = None


def _keyword_score(chunk: dict[str, Any], profile: FactExtractionProfile) -> int:
    text = "\n".join(
        [
            str(chunk.get("content") or ""),
            str(chunk.get("section_hint") or ""),
            str(chunk.get("chunk_type") or ""),
        ]
    ).lower()
    return sum(1 for keyword in profile.keywords if keyword.lower() in text)


def retrieve_chunks_by_keyword(
    chunks: list[dict[str, Any]],
    profile: FactExtractionProfile,
    *,
    document_key: str | None = None,
) -> list[RetrievedChunk]:
    filtered = [
        chunk
        for chunk in chunks
        if (document_key is None or chunk.get("document_key") == document_key)
    ]
    scored = [
        (chunk, _keyword_score(chunk, profile))
        for chunk in filtered
    ]
    matches = [item for item in scored if item[1] > 0]
    matches.sort(key=lambda item: (item[1], item[0].get("page_start") or 0), reverse=True)
    selected = matches[: profile.max_chunks]
    return [RetrievedChunk(chunk=chunk, retrieval_mode="keyword", score=float(score)) for chunk, score in selected]


def retrieve_chunks_by_vector(
    *,
    store: LocalQdrantChunkStore,
    embedder: OpenAIChunkEmbedder,
    profile: FactExtractionProfile,
    document_key: str | None = None,
) -> list[RetrievedChunk]:
    query_vector = embedder.embed_texts([profile.query_text])[0]
    results = store.search(
        query_vector=query_vector,
        document_key=document_key,
        limit=profile.max_chunks,
    )
    return [
        RetrievedChunk(chunk=result["payload"], retrieval_mode="vector", score=result["score"])
        for result in results
    ]


def retrieve_chunks(
    *,
    chunks: list[dict[str, Any]],
    profile: FactExtractionProfile,
    document_key: str | None = None,
    store: LocalQdrantChunkStore | None = None,
    embedder: OpenAIChunkEmbedder | None = None,
) -> list[RetrievedChunk]:
    if store is not None and embedder is not None and store.collection_exists():
        try:
            vector_results = retrieve_chunks_by_vector(
                store=store,
                embedder=embedder,
                profile=profile,
                document_key=document_key,
            )
            if vector_results:
                return vector_results
        except Exception:
            pass
    return retrieve_chunks_by_keyword(chunks, profile, document_key=document_key)
