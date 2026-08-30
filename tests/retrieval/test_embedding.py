from __future__ import annotations

import unittest

from backend.retrieval.embedding import (
    OllamaEmbeddingProvider,
    _LEGACY_SINGLE_INPUT_MAX_CHARS,
)


class RecordingOllamaEmbeddingProvider(OllamaEmbeddingProvider):
    def __init__(self) -> None:
        super().__init__(model="bge-m3:latest")
        self.requests: list[tuple[str, dict[str, object]]] = []

    def _request(self, path, payload=None):
        assert payload is not None
        self.requests.append((path, payload))
        if path == "/api/embeddings":
            return {"embedding": [1.0, 2.0]}
        return {
            "embeddings": [[1.0, 2.0] for _ in payload["input"]],
        }


class OllamaEmbeddingProviderTests(unittest.TestCase):
    def test_short_single_input_uses_legacy_single_embedding_endpoint(self) -> None:
        provider = RecordingOllamaEmbeddingProvider()

        vectors = provider.embed(["short query"])

        self.assertEqual(vectors, [[1.0, 2.0]])
        self.assertEqual(provider.requests[0][0], "/api/embeddings")
        self.assertEqual(provider.requests[0][1]["prompt"], "short query")
        self.assertEqual(provider.requests[0][1]["keep_alive"], "10m")

    def test_long_single_input_keeps_truncating_batch_endpoint(self) -> None:
        provider = RecordingOllamaEmbeddingProvider()
        text = "x" * (_LEGACY_SINGLE_INPUT_MAX_CHARS + 1)

        provider.embed([text])

        self.assertEqual(provider.requests[0][0], "/api/embed")
        self.assertEqual(provider.requests[0][1]["input"], [text])
        self.assertEqual(provider.requests[0][1]["truncate"], True)
        self.assertEqual(provider.requests[0][1]["keep_alive"], "10m")

    def test_batch_input_keeps_batch_embedding_endpoint(self) -> None:
        provider = RecordingOllamaEmbeddingProvider()

        provider.embed(["first", "second"])

        self.assertEqual(provider.requests[0][0], "/api/embed")
        self.assertEqual(provider.requests[0][1]["input"], ["first", "second"])
        self.assertEqual(provider.requests[0][1]["keep_alive"], "10m")


if __name__ == "__main__":
    unittest.main()
