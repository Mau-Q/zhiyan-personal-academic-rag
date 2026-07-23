from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.retrieval.comparison_route_coverage import (
    RESERVED_SWITCH,
    BilateralComparisonRouteCoverageSelector,
    RouteCoverageObservation,
    load_bilateral_route_coverage_config,
    route_coverage_switch_enabled,
)
from backend.retrieval.results import RankedChunk


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = (
    ROOT
    / "evaluation"
    / "phase3"
    / "bilateral-comparison-route-coverage-top3-v1.json"
)


def candidate(document_id: str, position: int, rank: int) -> RankedChunk:
    return RankedChunk(
        backend="online_ready_es_milvus_rrf_v1",
        rank=rank,
        score=1.0 / (60 + rank),
        chunk={
            "chunk_id": f"chunk_{document_id}_{position}",
            "document_id": document_id,
        },
    )


class BilateralRouteCoverageConfigTests(unittest.TestCase):
    def test_tracked_config_is_strict_and_default_off(self):
        config = load_bilateral_route_coverage_config(CONFIG_PATH)

        self.assertFalse(config.default_enabled)
        self.assertEqual(config.eligible_route_count, 2)
        self.assertEqual(config.final_top_k, 3)
        self.assertEqual(config.minimum_per_route, 1)

    def test_switch_defaults_off_and_rejects_ambiguous_values(self):
        self.assertFalse(route_coverage_switch_enabled({}))
        self.assertTrue(
            route_coverage_switch_enabled({RESERVED_SWITCH: "true"})
        )
        self.assertFalse(route_coverage_switch_enabled({RESERVED_SWITCH: "0"}))
        with self.assertRaisesRegex(ValueError, RESERVED_SWITCH):
            route_coverage_switch_enabled({RESERVED_SWITCH: "enabled"})

    def test_invalid_bounds_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            payload["final_top_k"] = 4
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "bounds"):
                load_bilateral_route_coverage_config(path)


class BilateralComparisonRouteCoverageSelectorTests(unittest.TestCase):
    def setUp(self):
        self.config = load_bilateral_route_coverage_config(CONFIG_PATH)
        self.candidates = [
            candidate("document_alpha", 1, 1),
            candidate("document_alpha", 2, 2),
            candidate("document_alpha", 3, 3),
            candidate("document_beta", 1, 4),
        ]

    def selector(self, *, enabled=True, observations=None):
        observer = observations.append if observations is not None else None
        return BilateralComparisonRouteCoverageSelector(
            config=self.config,
            enabled=enabled,
            observer=observer,
        )

    def test_selects_each_route_best_then_preserves_original_rrf_order(self):
        plan = self.selector().plan(
            "比较两篇论文的方法差异",
            self.candidates,
            document_ids=["document_alpha", "document_beta"],
            top_k=3,
        )

        self.assertEqual(plan.status, "APPLIED")
        self.assertEqual(
            plan.selected_chunk_ids,
            (
                "chunk_document_alpha_1",
                "chunk_document_alpha_2",
                "chunk_document_beta_1",
            ),
        )

    def test_already_covered_top3_is_unchanged(self):
        candidates = [
            candidate("document_alpha", 1, 1),
            candidate("document_beta", 1, 2),
            candidate("document_alpha", 2, 3),
            candidate("document_beta", 2, 4),
        ]

        plan = self.selector().plan(
            "compare the two papers",
            candidates,
            document_ids=["document_alpha", "document_beta"],
            top_k=3,
        )

        self.assertEqual(
            plan.selected_chunk_ids,
            tuple(item.chunk["chunk_id"] for item in candidates[:3]),
        )

    def test_disabled_or_ineligible_requests_fall_back_to_original_top3(self):
        original = tuple(
            item.chunk["chunk_id"] for item in self.candidates[:3]
        )
        disabled = self.selector(enabled=False).plan(
            "比较两篇论文",
            self.candidates,
            document_ids=["document_alpha", "document_beta"],
            top_k=3,
        )
        not_comparison = self.selector().plan(
            "总结两篇论文",
            self.candidates,
            document_ids=["document_alpha", "document_beta"],
            top_k=3,
        )
        one_route = self.selector().plan(
            "比较论文方法",
            self.candidates,
            document_ids=["document_alpha"],
            top_k=3,
        )

        self.assertEqual(disabled.status, "DISABLED")
        self.assertEqual(not_comparison.status, "FALLBACK")
        self.assertEqual(one_route.status, "FALLBACK")
        self.assertEqual(disabled.selected_chunk_ids, original)
        self.assertEqual(not_comparison.selected_chunk_ids, original)
        self.assertEqual(one_route.selected_chunk_ids, original)

    def test_missing_or_out_of_scope_route_candidate_falls_back(self):
        only_alpha = self.candidates[:3]
        missing = self.selector().plan(
            "比较两篇论文",
            only_alpha,
            document_ids=["document_alpha", "document_beta"],
            top_k=3,
        )
        outside = self.selector().plan(
            "比较两篇论文",
            [
                *self.candidates[:3],
                candidate("document_gamma", 1, 4),
                self.candidates[3],
            ],
            document_ids=["document_alpha", "document_beta"],
            top_k=3,
        )

        self.assertEqual(missing.failure_code, "ROUTE_CANDIDATE_UNAVAILABLE")
        self.assertEqual(outside.failure_code, "CANDIDATE_ROUTE_OUTSIDE_SCOPE")

    def test_observation_is_sanitized_and_records_selection_change(self):
        observations: list[RouteCoverageObservation] = []
        question = "比较两篇论文的方法差异"

        self.selector(observations=observations).plan(
            question,
            self.candidates,
            document_ids=["document_alpha", "document_beta"],
            top_k=3,
        )

        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0].selection_changed)
        self.assertEqual(observations[0].route_count, 2)
        self.assertEqual(observations[0].candidate_count, 4)
        self.assertGreaterEqual(observations[0].selection_latency_ms, 0)
        self.assertNotIn(question, repr(observations[0]))


if __name__ == "__main__":
    unittest.main()
