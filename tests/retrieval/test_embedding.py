from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.retrieval.embedding import (
    EmbeddingServiceError,
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


class FakeHttpResponse:
    def __init__(self, payload: bytes, *, status: int = 200, will_close: bool = False):
        self.payload = payload
        self.status = status
        self.will_close = will_close

    def read(self):
        return self.payload

    def getheader(self, name, default=None):
        del name
        return default


class FakeHttpConnection:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.closed = False

    def request(self, method, path, *, body, headers):
        self.requests.append((method, path, body, headers))

    def getresponse(self):
        return next(self.responses)

    def close(self):
        self.closed = True


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

    def test_http_connection_is_reused_and_closed_explicitly(self) -> None:
        connection = FakeHttpConnection(
            [
                FakeHttpResponse(b'{"models": []}'),
                FakeHttpResponse(b'{"version": "test"}'),
            ]
        )
        with patch(
            "backend.retrieval.embedding.http.client.HTTPConnection",
            return_value=connection,
        ) as connection_factory:
            provider = OllamaEmbeddingProvider()
            self.assertEqual(provider._request("/api/tags"), {"models": []})
            self.assertEqual(provider._request("/api/version"), {"version": "test"})
            provider.close()

        connection_factory.assert_called_once_with(
            "127.0.0.1", 11434, timeout=120.0
        )
        self.assertEqual(
            [(method, path) for method, path, _, _ in connection.requests],
            [("GET", "/api/tags"), ("GET", "/api/version")],
        )
        self.assertTrue(connection.closed)

    def test_http_connection_is_replaced_after_server_close(self) -> None:
        first = FakeHttpConnection([FakeHttpResponse(b'{"ok": true}', will_close=True)])
        second = FakeHttpConnection([FakeHttpResponse(b'{"ok": true}')])
        with patch(
            "backend.retrieval.embedding.http.client.HTTPConnection",
            side_effect=[first, second],
        ) as connection_factory:
            provider = OllamaEmbeddingProvider()
            provider._request("/api/first")
            provider._request("/api/second")

        self.assertEqual(connection_factory.call_count, 2)
        self.assertTrue(first.closed)
        self.assertEqual(second.requests[0][1], "/api/second")

    def test_http_status_failure_discards_the_reusable_connection(self) -> None:
        connection = FakeHttpConnection([FakeHttpResponse(b"busy", status=503)])
        with patch(
            "backend.retrieval.embedding.http.client.HTTPConnection",
            return_value=connection,
        ):
            provider = OllamaEmbeddingProvider()
            with self.assertRaisesRegex(EmbeddingServiceError, "HTTP 503"):
                provider._request("/api/embed")

        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
