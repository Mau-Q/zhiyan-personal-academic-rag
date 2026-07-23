from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from backend.retrieval.online import OnlineVisibilityUnavailableError
from backend.retrieval.online_reranker import (
    OnlineFixedCrossEncoderReranker,
    StaticDocumentTitleProvider,
    load_online_reranker_config,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = (
    ROOT
    / "evaluation"
    / "reranker"
    / "online-fixed-cross-encoder-windows-rtx4090-v1.json"
)
QUALITY_CONFIG_PATH = (
    ROOT
    / "evaluation"
    / "reranker"
    / "fixed-cross-encoder-windows-rtx4090-v1.json"
)
OWNER_ID = "owner_001"


def candidate(position: int, *, owner_id: str = OWNER_ID) -> dict[str, object]:
    return {
        "chunk_id": f"chunk_{position:03d}",
        "document_id": "document_001",
        "version_id": "version_001",
        "tenant_id": owner_id,
        "is_active": True,
        "section_path": "Method",
        "text": f"Evidence {position}",
        "page_start": position,
        "page_end": position,
    }


class RecordingScorer:
    def __init__(
        self,
        scores: list[float],
        *,
        failure: Exception | None = None,
    ) -> None:
        self.scores = scores
        self.failure = failure
        self.calls: list[list[tuple[str, str]]] = []

    def score(self, pairs):
        self.calls.append(list(pairs))
        if self.failure is not None:
            raise self.failure
        return self.scores


class OnlineFixedCrossEncoderRerankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_online_reranker_config(CONFIG_PATH)
        self.titles = StaticDocumentTitleProvider(
            {"document_001": "Frozen Paper Title"}
        )

    def test_online_config_matches_frozen_quality_model_identity(self) -> None:
        quality = json.loads(QUALITY_CONFIG_PATH.read_text(encoding="utf-8"))
        expected_model = dict(quality["model"])
        expected_model["snapshot_sha256"] = (
            "f9dd638f0b27b57667d99b01f83ca4dbb3c82983911a1ef31a4601c7b890eaec"
        )

        self.assertEqual(dict(self.config.model), expected_model)
        self.assertEqual(self.config.candidate_top_k, 20)
        self.assertEqual(
            self.config.failure_policy,
            "FALLBACK_TO_AUTHORIZED_RRF",
        )

    def test_reranks_only_authorized_candidates_with_frozen_template(self) -> None:
        scorer = RecordingScorer([0.1, 0.9, 0.4])
        reranker = OnlineFixedCrossEncoderReranker(
            config=self.config,
            scorer=scorer,
            title_provider=self.titles,
        )
        values = [candidate(1), candidate(2), candidate(3)]

        outcome = reranker.rerank(
            "What is the method?",
            values,
            owner_id=OWNER_ID,
            document_ids=["document_001"],
            top_k=2,
        )

        self.assertEqual(outcome.status, "APPLIED")
        self.assertEqual(
            [chunk["chunk_id"] for chunk in outcome.chunks],
            ["chunk_002", "chunk_003"],
        )
        self.assertEqual(
            {chunk["chunk_id"] for chunk in outcome.chunks},
            {"chunk_002", "chunk_003"},
        )
        self.assertEqual(
            scorer.calls[0][0],
            (
                "What is the method?",
                "Title: Frozen Paper Title\nSection: Method\nEvidence 1",
            ),
        )

    def test_equal_scores_preserve_authorized_rrf_order(self) -> None:
        scorer = RecordingScorer([0.5, 0.5, 0.5])
        reranker = OnlineFixedCrossEncoderReranker(
            config=self.config,
            scorer=scorer,
            title_provider=self.titles,
        )

        outcome = reranker.rerank(
            "Question",
            [candidate(3), candidate(1), candidate(2)],
            owner_id=OWNER_ID,
            document_ids=[],
            top_k=3,
        )

        self.assertEqual(
            [chunk["chunk_id"] for chunk in outcome.chunks],
            ["chunk_003", "chunk_001", "chunk_002"],
        )

    def test_model_or_title_failure_falls_back_to_authorized_rrf(self) -> None:
        failures = (
            (
                RecordingScorer([], failure=RuntimeError("private model error")),
                self.titles,
                "MODEL_SCORING_UNAVAILABLE",
            ),
            (
                RecordingScorer([0.1, 0.2, 0.3]),
                StaticDocumentTitleProvider({"document_other": "Other"}),
                "TITLE_OR_TEMPLATE_UNAVAILABLE",
            ),
            (
                RecordingScorer([0.1, math.nan, 0.3]),
                self.titles,
                "MODEL_SCORE_INVALID",
            ),
        )
        for scorer, titles, expected_code in failures:
            with self.subTest(expected_code=expected_code):
                reranker = OnlineFixedCrossEncoderReranker(
                    config=self.config,
                    scorer=scorer,
                    title_provider=titles,
                )
                outcome = reranker.rerank(
                    "Question",
                    [candidate(1), candidate(2), candidate(3)],
                    owner_id=OWNER_ID,
                    document_ids=["document_001"],
                    top_k=2,
                )
                self.assertEqual(outcome.status, "FALLBACK")
                self.assertEqual(outcome.failure_code, expected_code)
                self.assertEqual(
                    [chunk["chunk_id"] for chunk in outcome.chunks],
                    ["chunk_001", "chunk_002"],
                )

    def test_candidate_identity_violation_never_uses_fallback(self) -> None:
        reranker = OnlineFixedCrossEncoderReranker(
            config=self.config,
            scorer=RecordingScorer([1.0]),
            title_provider=self.titles,
        )

        with self.assertRaisesRegex(
            OnlineVisibilityUnavailableError,
            "authorized READY identity",
        ):
            reranker.rerank(
                "Question",
                [candidate(1, owner_id="owner_other")],
                owner_id=OWNER_ID,
                document_ids=["document_001"],
                top_k=1,
            )

    def test_no_evidence_does_not_call_model(self) -> None:
        scorer = RecordingScorer([])
        reranker = OnlineFixedCrossEncoderReranker(
            config=self.config,
            scorer=scorer,
            title_provider=self.titles,
        )

        outcome = reranker.rerank(
            "Question",
            [],
            owner_id=OWNER_ID,
            document_ids=["document_001"],
            top_k=3,
        )

        self.assertEqual(outcome.status, "NO_EVIDENCE")
        self.assertEqual(scorer.calls, [])
