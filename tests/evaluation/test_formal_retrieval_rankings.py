from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from backend.retrieval.embedding import EmbeddingModelIdentity
from scripts.run_formal_retrieval_rankings import (
    CachedEmbeddingProvider,
    _record,
    load_config,
)


class _Provider:
    def identity(self) -> EmbeddingModelIdentity:
        return EmbeddingModelIdentity("fixture", "fixture-v1", "abc")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class FormalRetrievalRankingTests(unittest.TestCase):
    def test_cached_provider_reuses_preloaded_vectors(self) -> None:
        provider = CachedEmbeddingProvider(_Provider(), ["a", "bb"])
        self.assertEqual(provider.embed(["bb", "a"]), [[2.0], [1.0]])
        with self.assertRaisesRegex(ValueError, "not preloaded"):
            provider.embed(["missing"])

    def test_empty_result_is_no_evidence(self) -> None:
        record = _record(
            run_id="run.1",
            dataset_version="dataset.1",
            question_id="question.1",
            backend="fixture",
            top_k=3,
            latency_ms=1.0,
            chunks=[],
        )
        self.assertEqual(record.decision, "NO_EVIDENCE")

    def test_loads_frozen_four_way_config(self) -> None:
        config = {
            "schema_version": "formal_local_retrieval_config_v1",
            "backends": [
                "lexical_overlap",
                "sqlite_fts5",
                "local_vector",
                "local_rrf",
            ],
            "top_k": 50,
            "metric_k_values": [3, 5, 10, 20, 50],
            "embedding_model": "bge-m3:latest",
            "embedding_model_digest": "a" * 64,
            "vector_min_score": 0.5,
            "rrf_candidate_k": 20,
            "rrf_k": 60,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            self.assertEqual(load_config(path), config)


if __name__ == "__main__":
    unittest.main()
