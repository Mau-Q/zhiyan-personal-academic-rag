from __future__ import annotations

import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from backend.evaluation.reranker import (
    build_decision,
    build_passage,
    directory_sha256,
    load_config,
    rerank_result,
)
from backend.evaluation.retrieval_metrics import RetrievalRankingResultV1
from scripts.run_fixed_reranker_gate import _portable_text_sha256, _sha256


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "evaluation/reranker/fixed-cross-encoder-v1.json"
WINDOWS_CONFIG = (
    ROOT / "evaluation/reranker/fixed-cross-encoder-windows-rtx4090-v1.json"
)


class FakeScorer:
    def __init__(self, scores: list[float], lengths: list[int]):
        self.scores = scores
        self.lengths = lengths
        self.calls = 0

    def token_lengths(self, pairs: list[tuple[str, str]]) -> list[int]:
        self.calls += 1
        return self.lengths[: len(pairs)]

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls += 1
        return self.scores[: len(pairs)]


def source_result(decision: str = "EVIDENCE_FOUND") -> RetrievalRankingResultV1:
    candidates = (
        [
            {
                "rank": 1,
                "chunk_id": "chunk_1",
                "document_id": "doc_arxiv_1_1",
                "score": None,
            },
            {
                "rank": 2,
                "chunk_id": "chunk_2",
                "document_id": "doc_arxiv_1_1",
                "score": None,
            },
        ]
        if decision == "EVIDENCE_FOUND"
        else []
    )
    return RetrievalRankingResultV1.model_validate(
        {
            "schema_version": "retrieval_ranking_result_v1",
            "run_id": "source",
            "dataset_version": "dataset",
            "question_id": "question",
            "backend": "local_rrf",
            "top_k": 50,
            "decision": decision,
            "latency_ms": 10.0,
            "candidates": candidates,
        }
    )


class FixedRerankerTests(unittest.TestCase):
    def test_config_is_frozen_and_valid(self) -> None:
        config = load_config(CONFIG)
        self.assertEqual(config.candidate_top_k, 20)
        self.assertEqual(config.output_top_k, 20)
        self.assertEqual(config.evaluation_splits, ("test",))
        self.assertEqual(config.model["trust_remote_code"], False)
        self.assertEqual(len(config.model["revision"]), 40)

    def test_config_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            value = json.loads(CONFIG.read_text())
            value["unexpected"] = True
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "fields"):
                load_config(path)

    def test_config_rejects_invalid_metric_shape_as_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            value = json.loads(CONFIG.read_text())
            value["metric_k_values"] = "5,10"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "metric K"):
                load_config(path)

    def test_windows_config_changes_only_run_identity_and_device(self) -> None:
        local = json.loads(CONFIG.read_text())
        windows = json.loads(WINDOWS_CONFIG.read_text())
        windows["run_id"] = local["run_id"]
        windows["model"]["device"] = local["model"]["device"]
        self.assertEqual(windows, local)

    def test_passage_includes_frozen_title_section_and_text(self) -> None:
        passage = build_passage(
            {
                "document_id": "doc_arxiv_1_1",
                "section_path": "1 Introduction",
                "text": "Evidence text.",
            },
            {"doc_arxiv_1_1": "Paper Title"},
        )
        self.assertEqual(
            passage,
            "Title: Paper Title\nSection: 1 Introduction\nEvidence text.",
        )

    def test_rerank_is_score_descending_and_tie_stable(self) -> None:
        config = load_config(CONFIG)
        chunks = {
            "chunk_1": {
                "document_id": "doc_arxiv_1_1",
                "section_path": "A",
                "text": "First",
            },
            "chunk_2": {
                "document_id": "doc_arxiv_1_1",
                "section_path": "B",
                "text": "Second",
            },
        }
        scorer = FakeScorer([0.1, 0.9], [400, 600])
        observation = rerank_result(
            source=source_result(),
            question="Question?",
            chunks_by_id=chunks,
            document_titles={"doc_arxiv_1_1": "Title"},
            config=config,
            scorer=scorer,
        )
        self.assertEqual(
            [candidate.chunk_id for candidate in observation.result.candidates],
            ["chunk_2", "chunk_1"],
        )
        self.assertEqual(
            {candidate.chunk_id for candidate in observation.result.candidates},
            {"chunk_1", "chunk_2"},
        )
        self.assertEqual(observation.pair_count, 2)
        self.assertEqual(observation.truncated_pair_count, 1)
        self.assertGreaterEqual(observation.result.latency_ms, 10.0)

    def test_non_evidence_decision_never_calls_model(self) -> None:
        config = load_config(CONFIG)
        scorer = FakeScorer([], [])
        observation = rerank_result(
            source=source_result("FORBIDDEN"),
            question="Question?",
            chunks_by_id={},
            document_titles={},
            config=config,
            scorer=scorer,
        )
        self.assertEqual(observation.result.decision, "FORBIDDEN")
        self.assertEqual(observation.result.backend, "fixed_cross_encoder")
        self.assertEqual(scorer.calls, 0)

    def test_directory_digest_binds_paths_and_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a").mkdir()
            (root / "a/model.bin").write_bytes(b"one")
            first = directory_sha256(root)
            (root / "a/model.bin").write_bytes(b"two")
            second = directory_sha256(root)
            self.assertNotEqual(first, second)

    def test_directory_digest_uses_portable_case_sensitive_relative_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_bytes(b"readme")
            (root / "assets").mkdir()
            (root / "assets/model.bin").write_bytes(b"model")

            digest = sha256()
            for relative_path, value in (
                ("README.md", b"readme"),
                ("assets/model.bin", b"model"),
            ):
                encoded_path = relative_path.encode("utf-8")
                digest.update(len(encoded_path).to_bytes(8, "big"))
                digest.update(encoded_path)
                digest.update(sha256(value).digest())

            self.assertEqual(directory_sha256(root), digest.hexdigest())

    def test_tracked_text_digest_normalizes_windows_newlines_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lf_path = root / "lf.json"
            crlf_path = root / "crlf.json"
            lf_path.write_bytes(b'{\n  "value": true\n}\n')
            crlf_path.write_bytes(b'{\r\n  "value": true\r\n}\r\n')

            self.assertEqual(
                _portable_text_sha256(lf_path),
                _portable_text_sha256(crlf_path),
            )
            self.assertNotEqual(_sha256(lf_path), _sha256(crlf_path))

    def test_decision_falls_back_when_relative_gain_is_too_small(self) -> None:
        config = load_config(CONFIG)
        by_type = {
            name: {"eligible_count": 10, "ndcg@10": 0.5}
            for name in config.decision_policy["critical_question_types"]
        }
        report = {
            "runs": {
                "local_rrf": {
                    "metrics": {"ndcg@10": 0.5, "precision@5": 0.3},
                    "by_question_type": by_type,
                },
                "fixed_cross_encoder": {
                    "metrics": {"ndcg@10": 0.52, "precision@5": 0.31},
                    "by_question_type": by_type,
                },
            }
        }
        decision = build_decision(metrics_report=report, config=config)
        self.assertEqual(decision["decision"], "FALLBACK_TO_LOCAL_RRF")


if __name__ == "__main__":
    unittest.main()
