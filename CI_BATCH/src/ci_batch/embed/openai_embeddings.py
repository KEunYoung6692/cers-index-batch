"""
OpenAI embedding client wrapper for CI_BATCH.
"""

from __future__ import annotations

import os

from openai import OpenAI


class OpenAIChunkEmbedder:
    def __init__(
        self,
        *,
        api_key_env: str,
        model: str,
        dimensions: int | None = None,
    ) -> None:
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise RuntimeError(f"Environment variable {api_key_env} is required for OpenAI embeddings")

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            kwargs = {
                "model": self._model,
                "input": texts,
            }
            if self._dimensions is not None:
                kwargs["dimensions"] = self._dimensions

            response = self._client.embeddings.create(**kwargs)
            return [item.embedding for item in response.data]
        except Exception as exc:
            raise RuntimeError(f"OpenAI embedding request failed: {exc}") from exc
