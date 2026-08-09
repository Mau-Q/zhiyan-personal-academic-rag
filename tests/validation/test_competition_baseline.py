from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "machine/competition/rag_competition_baseline.json"
SCHEMA_PATH = ROOT / "contracts/schemas/competition-baseline-v1.schema.json"


class CompetitionBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_baseline_matches_strict_schema(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.baseline)

    def test_dual_commit_provenance_is_not_conflated(self) -> None:
        provenance = self.baseline["provenance"]
        self.assertEqual(
            provenance["real_reproduction_source"],
            "d775dab706c2a05d5b838f644b77b257961a4549",
        )
        self.assertEqual(
            provenance["repository_head"],
            "fd5a517b56ba619ca461e262a5ea1a8ac8b9ac7b",
        )
        self.assertNotEqual(
            provenance["real_reproduction_source"],
            provenance["repository_head"],
        )
        self.assertEqual(provenance["runtime_equivalence"], "PASS")

    def test_frozen_artifact_and_scenario_identity(self) -> None:
        self.assertEqual(self.baseline["status"], "FROZEN")
        self.assertEqual(self.baseline["owner_scope_status"], "DONE_ENOUGH")
        self.assertEqual(
            self.baseline["artifacts"]["redacted_results_sha256"],
            "3e309bed036f4a5ad3f1d45cbd9d5abad256ce0db217c2ae3afa3c71fb9bc4fb",
        )
        self.assertEqual(
            self.baseline["competition_scenarios"]["results"],
            {
                "COMP-QA-001": "PASS",
                "COMP-EVIDENCESET-001": "PASS",
                "COMP-FAIL-CLOSED-001": "PASS",
            },
        )
        self.assertEqual(
            self.baseline["competition_scenarios"]["evidence_set_mode"],
            "AUDIT_ONLY",
        )

    def test_closeout_preserves_partial_and_deferred_work(self) -> None:
        self.assertEqual(
            self.baseline["preserved_boundaries"],
            {
                "phase_3": "PARTIAL_NO_PROMOTION",
                "phase_3_optimization": "STOP",
                "phase_4": "PARTIAL_AUDIT_ONLY",
                "performance_300_ms": "KNOWN_DEFERRED_DEBT",
            },
        )
        self.assertEqual(
            self.baseline["strategy_handoff"],
            ["NO_NEW_RAG_ENGINEERING_WORK", "NO_AUTOMATIC_NEXT_TASK"],
        )


if __name__ == "__main__":
    unittest.main()
