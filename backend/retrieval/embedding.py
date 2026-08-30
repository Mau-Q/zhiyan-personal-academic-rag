"""Dependency-free client contract for real local embedding services."""

from __future__ import annotations

import http.client
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Condition
from typing import Any, Protocol
from urllib.parse import urlsplit


_LEGACY_SINGLE_INPUT_MAX_CHARS = 2048
_OLLAMA_KEEP_ALIVE = "10m"


class EmbeddingServiceError(ValueError):
    """Raised when the configured embedding service cannot prove a usable model."""


class _OllamaHttpStatusError(OSError):
    """Keep non-success HTTP responses on the existing fail-closed path."""

    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")


_OllamaConnection = http.client.HTTPConnection | http.client.HTTPSConnection
_OLLAMA_MAX_HTTP_CONNECTIONS = 2


class _ReusableOllamaHttpClient:
    """Bounded, thread-safe, lazy HTTP/1.1 connection reuse for one Ollama origin."""

    def __init__(self, *, base_url: str, timeout_seconds: float):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("embedding base_url must use http or https with a host")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("embedding base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("embedding base_url must not contain a query or fragment")
        self._scheme = parsed.scheme
        self._host = parsed.hostname
        self._port = parsed.port
        self._base_path = parsed.path.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._connections: list[_OllamaConnection] = []
        self._available: list[_OllamaConnection] = []
        self._condition = Condition()
        self._closed = False

    def _new_connection(self) -> _OllamaConnection:
        connection_type = (
            http.client.HTTPSConnection
            if self._scheme == "https"
            else http.client.HTTPConnection
        )
        return connection_type(
            self._host,
            self._port,
            timeout=self._timeout_seconds,
        )

    def _acquire(self) -> _OllamaConnection:
        with self._condition:
            while True:
                if self._closed:
                    raise OSError("Ollama HTTP client is closed")
                if self._available:
                    return self._available.pop()
                if len(self._connections) < _OLLAMA_MAX_HTTP_CONNECTIONS:
                    connection = self._new_connection()
                    self._connections.append(connection)
                    return connection
                self._condition.wait()

    def _release(self, connection: _OllamaConnection, *, discard: bool) -> None:
        close_connection = False
        with self._condition:
            if discard or self._closed:
                self._connections = [
                    candidate
                    for candidate in self._connections
                    if candidate is not connection
                ]
                self._available = [
                    candidate
                    for candidate in self._available
                    if candidate is not connection
                ]
                close_connection = True
            elif not any(candidate is connection for candidate in self._available):
                self._available.append(connection)
            self._condition.notify()
        if close_connection:
            try:
                connection.close()
            except OSError:
                pass

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None,
        headers: dict[str, str],
    ) -> bytes:
        target = f"{self._base_path}{path}"
        if not target.startswith("/"):
            target = f"/{target}"
        connection = self._acquire()
        try:
            connection.request(method, target, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            connection_header = response.getheader("Connection") or ""
            discard = bool(response.will_close) or connection_header.lower() == "close"
            if not 200 <= response.status < 300:
                raise _OllamaHttpStatusError(response.status)
        except (OSError, http.client.HTTPException):
            self._release(connection, discard=True)
            raise
        self._release(connection, discard=discard)
        return raw

    def close(self) -> None:
        with self._condition:
            self._closed = True
            connections = list(self._connections)
            self._connections.clear()
            self._available.clear()
            self._condition.notify_all()
        for connection in connections:
            try:
                connection.close()
            except OSError:
                pass


@dataclass(frozen=True)
class EmbeddingModelIdentity:
    provider: str
    model: str
    digest: str


class EmbeddingProvider(Protocol):
    """Small provider boundary shared by real Ollama and deterministic tests."""

    def identity(self) -> EmbeddingModelIdentity: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OllamaEmbeddingProvider:
    """Call Ollama's local ``/api/embed`` endpoint with an identity-pinned model."""

    def __init__(
        self,
        *,
        model: str = "bge-m3:latest",
        base_url: str = "http://127.0.0.1:11434",
        batch_size: int = 16,
        timeout_seconds: float = 120.0,
    ):
        if not model.strip():
            raise ValueError("embedding model must not be blank")
        if batch_size < 1:
            raise ValueError("embedding batch_size must be at least 1")
        if timeout_seconds <= 0:
            raise ValueError("embedding timeout_seconds must be positive")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds
        self._http_client = _ReusableOllamaHttpClient(
            base_url=self.base_url,
            timeout_seconds=timeout_seconds,
        )

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        method = "GET"
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            method = "POST"
            headers["Content-Type"] = "application/json"
        try:
            raw = self._http_client.request(
                method,
                path,
                body=data,
                headers=headers,
            )
            decoded = json.loads(raw.decode("utf-8"))
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
            raise EmbeddingServiceError(f"Ollama request failed for {path}: {exc}") from exc
        if not isinstance(decoded, dict):
            raise EmbeddingServiceError(f"Ollama returned a non-object response for {path}")
        return decoded

    def close(self) -> None:
        """Close the provider's reusable connection when the host shuts down."""

        self._http_client.close()

    @staticmethod
    def _model_aliases(name: str) -> set[str]:
        aliases = {name}
        if name.endswith(":latest"):
            aliases.add(name.removesuffix(":latest"))
        else:
            aliases.add(f"{name}:latest")
        return aliases

    def identity(self) -> EmbeddingModelIdentity:
        models = self._request("/api/tags").get("models")
        if not isinstance(models, list):
            raise EmbeddingServiceError("Ollama /api/tags response has no models array")
        requested_aliases = self._model_aliases(self.model)
        for item in models:
            if not isinstance(item, dict) or item.get("name") not in requested_aliases:
                continue
            name = item.get("name")
            digest = item.get("digest")
            if not isinstance(name, str) or not isinstance(digest, str) or not digest:
                break
            return EmbeddingModelIdentity(provider="ollama", model=name, digest=digest)
        raise EmbeddingServiceError(f"Ollama model is not installed: {self.model}")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("embedding input texts must be non-blank strings")
        if len(texts) == 1 and len(texts[0]) <= _LEGACY_SINGLE_INPUT_MAX_CHARS:
            return self._embed_single_legacy(texts[0])
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            payload = self._request(
                "/api/embed",
                {
                    "model": self.model,
                    "input": batch,
                    "truncate": True,
                    "keep_alive": _OLLAMA_KEEP_ALIVE,
                },
            )
            embeddings = payload.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise EmbeddingServiceError("Ollama returned an invalid embeddings batch")
            for vector in embeddings:
                vectors.append(self._convert_vector(vector))
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise EmbeddingServiceError("Ollama returned inconsistent embedding dimensions")
        return vectors

    def _embed_single_legacy(self, text: str) -> list[list[float]]:
        """Use Ollama's single-input path after the caller's safe length guard."""

        payload = self._request(
            "/api/embeddings",
            {
                "model": self.model,
                "prompt": text,
                "keep_alive": _OLLAMA_KEEP_ALIVE,
            },
        )
        return [self._convert_vector(payload.get("embedding"))]

    @staticmethod
    def _convert_vector(vector: Any) -> list[float]:
        if not isinstance(vector, list) or not vector:
            raise EmbeddingServiceError("Ollama returned an empty embedding vector")
        try:
            converted = [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise EmbeddingServiceError("Ollama returned an invalid embedding vector") from exc
        if not all(math.isfinite(value) for value in converted):
            raise EmbeddingServiceError("Ollama returned a non-finite embedding value")
        return converted
