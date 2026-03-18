"""
Create OpenAI embeddings for retrieval chunks and index them into local Qdrant.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_batch.common.jsonl import read_jsonl, write_jsonl
from ci_batch.common.run_context import make_run_context, write_manifest
from ci_batch.common.settings import load_settings
from ci_batch.common.storage import manifests_dir, qdrant_dir, run_partition_dir
from ci_batch.embed.openai_embeddings import OpenAIChunkEmbedder
from ci_batch.vectordb.qdrant_store import LocalQdrantChunkStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed retrieval chunks and index them into local Qdrant")
    parser.add_argument("--chunks-manifest", required=True, help="Path to retrieval chunks manifest JSONL")
    parser.add_argument("--run-date", default=None, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--registrar", default=None, help="Registrar override")
    parser.add_argument("--document-key", default=None, help="Index chunks for a single document")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of chunks to index")
    return parser.parse_args()


def batch_items(rows: list[dict], batch_size: int) -> list[list[dict]]:
    return [rows[index:index + batch_size] for index in range(0, len(rows), batch_size)]


def main() -> int:
    args = parse_args()
    settings = load_settings()
    registrar = args.registrar or settings.registrar
    context = make_run_context(
        batch_name="index_chunks",
        ci_batch_root=settings.ci_batch_root,
        run_date=args.run_date,
    )

    manifest_path = Path(args.chunks_manifest)
    chunks = read_jsonl(manifest_path)
    if args.document_key:
        chunks = [chunk for chunk in chunks if chunk.get("document_key") == args.document_key]
    if args.limit is not None:
        chunks = chunks[: args.limit]

    embedder = OpenAIChunkEmbedder(
        api_key_env=settings.openai_api_key_env,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    store = LocalQdrantChunkStore(
        storage_path=qdrant_dir(settings.ci_batch_root),
        collection_name=settings.vector_db_collection,
    )

    indexed_count = 0
    for batch in batch_items(chunks, settings.embedding_batch_size):
        texts = [chunk["content"] for chunk in batch]
        embeddings = embedder.embed_texts(texts)
        indexed_count += store.upsert_chunks(batch, embeddings)

    manifests_partition = run_partition_dir(manifests_dir(settings.ci_batch_root), context.run_date)
    index_manifest_path = manifests_partition / f"{context.run_id}_indexed_chunks.jsonl"
    indexed_rows = [
        {
            "chunk_id": chunk["chunk_id"],
            "document_key": chunk["document_key"],
            "collection_name": store.collection_name,
            "embedding_model": settings.embedding_model,
            "registrar": registrar,
        }
        for chunk in chunks
    ]
    write_jsonl(index_manifest_path, indexed_rows)

    write_manifest(
        context,
        extra={
            "chunks_manifest_path": str(manifest_path.resolve()),
            "index_manifest_path": str(index_manifest_path),
            "collection_name": store.collection_name,
            "embedding_model": settings.embedding_model,
            "requested_chunks": len(chunks),
            "indexed_chunks": indexed_count,
        },
    )

    print(
        json.dumps(
            {
                "run_id": context.run_id,
                "run_date": context.run_date,
                "collection_name": store.collection_name,
                "embedding_model": settings.embedding_model,
                "requested_chunks": len(chunks),
                "indexed_chunks": indexed_count,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
