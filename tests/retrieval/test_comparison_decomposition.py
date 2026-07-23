from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.retrieval.comparison_decomposition import (
    RESERVED_SWITCH,
    BilateralComparisonQueryDecomposer,
    ComparisonDecompositionObservation,
    load_bilateral_comparison_config,
    remap_document_identities,
    switch_enabled,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = (
    ROOT
    / "evaluation"
    / "phase3"
    / "bilateral-comparison-query-decomposition-v1.json"
)
ALPHA_ID = "document_alpha"
BETA_ID = "document_beta"


def synthetic_config_path(directory: Path) -> Path:
    path = directory / "comparison-config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": (
                    "bilateral_comparison_query_decomposition_config_v1"
                ),
                "variable_id": "BILATERAL_COMPARISON_QUERY_DECOMPOSITION_V1",
                "default_enabled": False,
                "failure_policy": "FALLBACK_TO_ORIGINAL_QUERY",
                "comparison_markers": ["比较", "差异", "不同", "compare"],
                "transition_markers": ["同时", "另外", "meanwhile"],
                "document_identities": [
                    {
                        "document_id": ALPHA_ID,
                        "aliases": ["AlphaStudy", "Alpha Study"],
                    },
                    {
                        "document_id": BETA_ID,
                        "aliases": ["BetaBench", "Beta Benchmark"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


class BilateralComparisonConfigTests(unittest.TestCase):
    def test_tracked_config_is_strict_and_default_off(self):
        config = load_bilateral_comparison_config(CONFIG_PATH)

        self.assertFalse(config.default_enabled)
        self.assertEqual(len(config.document_identities), 3)

    def test_switch_is_default_off_and_rejects_ambiguous_values(self):
        self.assertFalse(switch_enabled({}))
        self.assertTrue(switch_enabled({RESERVED_SWITCH: "true"}))
        self.assertFalse(switch_enabled({RESERVED_SWITCH: "0"}))
        with self.assertRaisesRegex(ValueError, RESERVED_SWITCH):
            switch_enabled({RESERVED_SWITCH: "enabled"})

    def test_ambiguous_aliases_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = synthetic_config_path(Path(directory))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["document_identities"][1]["aliases"].append("AlphaStudy")
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "aliases are ambiguous"):
                load_bilateral_comparison_config(path)

    def test_source_aliases_can_be_bound_to_exact_runtime_document_ids(self):
        config = load_bilateral_comparison_config(CONFIG_PATH)
        mapping = {
            identity.document_id: f"runtime_{index}"
            for index, identity in enumerate(config.document_identities, 1)
        }

        remapped = remap_document_identities(config, mapping)

        self.assertEqual(
            [identity.document_id for identity in remapped.document_identities],
            list(mapping.values()),
        )
        self.assertIn("SciNet", remapped.document_identities[0].aliases)
        with self.assertRaisesRegex(ValueError, "runtime identity map"):
            remap_document_identities(
                config,
                {next(iter(mapping)): "runtime_only"},
            )


class BilateralComparisonQueryDecomposerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = load_bilateral_comparison_config(
            synthetic_config_path(Path(self.directory.name))
        )

    def decomposer(self, *, enabled=True, observations=None):
        observer = observations.append if observations is not None else None
        return BilateralComparisonQueryDecomposer(
            config=self.config,
            enabled=enabled,
            observer=observer,
        )

    def test_two_named_sides_receive_distinct_queries_by_identity_not_route_order(self):
        question = (
            "AlphaStudy 的 Method-A 与 BetaBench 的 Metric-B"
            "在证据验证严格性上有何不同？请比较两者的上下文要求。"
        )

        plan = self.decomposer().plan(
            question,
            document_ids=[BETA_ID, ALPHA_ID],
        )

        self.assertEqual(plan.status, "APPLIED")
        self.assertIn("AlphaStudy 的 Method-A", plan.queries[ALPHA_ID])
        self.assertNotIn("BetaBench", plan.queries[ALPHA_ID])
        self.assertIn("BetaBench 的 Metric-B", plan.queries[BETA_ID])
        self.assertNotIn("AlphaStudy", plan.queries[BETA_ID])
        self.assertIn("证据验证严格性", plan.queries[ALPHA_ID])
        self.assertIn("上下文要求", plan.queries[BETA_ID])

    def test_transition_anchors_named_side_and_assigns_leading_side_to_other_route(self):
        question = (
            "模型甲与模型乙在关系识别指标上的表现有何差异？"
            "同时，请结合 BetaBench 说明多轮交互的结构性失败模式。"
        )

        plan = self.decomposer().plan(
            question,
            document_ids=[ALPHA_ID, BETA_ID],
        )

        self.assertEqual(plan.status, "APPLIED")
        self.assertIn("关系识别指标", plan.queries[ALPHA_ID])
        self.assertNotIn("BetaBench", plan.queries[ALPHA_ID])
        self.assertIn("BetaBench", plan.queries[BETA_ID])
        self.assertNotIn("模型甲与模型乙", plan.queries[BETA_ID])

    def test_disabled_or_unproven_requests_fall_back_to_original_query(self):
        question = "总结 AlphaStudy 的主要结论。"
        disabled = self.decomposer(enabled=False).plan(
            question,
            document_ids=[ALPHA_ID, BETA_ID],
        )
        unproven = self.decomposer().plan(
            question,
            document_ids=[ALPHA_ID, BETA_ID],
        )
        one_route = self.decomposer().plan(
            "比较 AlphaStudy 与 BetaBench 的方法。",
            document_ids=[ALPHA_ID],
        )

        self.assertEqual(disabled.status, "DISABLED")
        self.assertEqual(unproven.status, "FALLBACK")
        self.assertEqual(one_route.status, "FALLBACK")
        self.assertEqual(
            disabled.queries,
            {ALPHA_ID: question, BETA_ID: question},
        )
        self.assertEqual(
            unproven.queries,
            {ALPHA_ID: question, BETA_ID: question},
        )

    def test_observation_contains_status_and_latency_but_no_query_text(self):
        observations: list[ComparisonDecompositionObservation] = []
        question = "AlphaStudy 与 BetaBench 在风险评分上有何不同？"

        plan = self.decomposer(observations=observations).plan(
            question,
            document_ids=[ALPHA_ID, BETA_ID],
        )

        self.assertEqual(plan.status, "APPLIED")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].route_count, 2)
        self.assertGreaterEqual(observations[0].decomposition_latency_ms, 0)
        self.assertNotIn(question, repr(observations[0]))


if __name__ == "__main__":
    unittest.main()
