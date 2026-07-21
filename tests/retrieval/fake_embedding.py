from __future__ import annotations

from collections.abc import Sequence

from backend.retrieval.embedding import EmbeddingModelIdentity


class FakeEmbeddingProvider:
    def __init__(self, *, digest: str = "sha256:test-embedding-v1"):
        self.digest = digest

    def identity(self) -> EmbeddingModelIdentity:
        return EmbeddingModelIdentity(
            provider="test",
            model="semantic-fixture-v1",
            digest=self.digest,
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    @staticmethod
    def _embed(text: str) -> list[float]:
        lowered = text.lower()
        if "quantum" in lowered or "entanglement" in lowered:
            return [0.0, 0.0, 1.0, 0.0]
        if any(word in lowered for word in ("ocean", "temperature", "botany")):
            return [0.0, 1.0, 0.0, 0.0]
        if any(word in lowered for word in ("obsolete", "deprecated")):
            return [0.0, 0.0, 0.0, 1.0]
        if any(word in lowered for word in ("rerank", "authorization")):
            return [0.8, 0.0, 0.0, 0.2]
        return [1.0, 0.0, 0.0, 0.0]
