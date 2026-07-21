"""Dependency-free client contract for real local embedding services."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class EmbeddingServiceError(ValueError):
    """Raised when the configured embedding service cannot prove a usable model."""


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
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("embedding base_url must use http or https")
        if batch_size < 1:
            raise ValueError("embedding batch_size must be at least 1")
        if timeout_seconds <= 0:
            raise ValueError("embedding timeout_seconds must be positive")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        method = "GET"
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            method = "POST"
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise EmbeddingServiceError(f"Ollama request failed for {path}: {exc}") from exc
        if not isinstance(decoded, dict):
            raise EmbeddingServiceError(f"Ollama returned a non-object response for {path}")
        return decoded

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
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            payload = self._request(
                "/api/embed",
                {"model": self.model, "input": batch, "truncate": True},
            )
            embeddings = payload.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise EmbeddingServiceError("Ollama returned an invalid embeddings batch")
            for vector in embeddings:
                if not isinstance(vector, list) or not vector:
                    raise EmbeddingServiceError("Ollama returned an empty embedding vector")
                converted = [float(value) for value in vector]
                if not all(math.isfinite(value) for value in converted):
                    raise EmbeddingServiceError("Ollama returned a non-finite embedding value")
                vectors.append(converted)
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise EmbeddingServiceError("Ollama returned inconsistent embedding dimensions")
        return vectors
