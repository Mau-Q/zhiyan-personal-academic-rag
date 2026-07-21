from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

from backend.evaluation.formal_corpus import EvaluationItemV1
from scripts.prepare_risk_review_package import (
    build_decision_template,
    risk_reasons,
    _write_deterministic_zip,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ITEMS = ROOT / "evaluation" / "formal" / "fixture-items-v1.jsonl"


class PrepareRiskReviewPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.items = [
            EvaluationItemV1.model_validate(json.loads(line))
            for line in FIXTURE_ITEMS.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def test_selects_only_policy_risk_reasons(self) -> None:
        reasons = {item.question_id: risk_reasons(item) for item in self.items}
        self.assertEqual(reasons["fixture.formal.answerable"], [])
        self.assertEqual(
            reasons["fixture.formal.no_evidence"],
            ["NO_EVIDENCE_CONFIRMATION"],
        )
        self.assertEqual(
            reasons["fixture.formal.forbidden"],
            ["SECURITY_BOUNDARY_CONFIRMATION"],
        )
        self.assertEqual(
            reasons["fixture.formal.acceptance"],
            ["ACCEPTANCE_CONFIRMATION"],
        )

    def test_decision_template_prefills_proposal_but_stays_pending(self) -> None:
        entry = {
            "review_id": "review.fixture.1",
            "question_id": "fixture.1",
            "review_reasons": ["EXPERT_REVIEW", "ACCEPTANCE_CONFIRMATION"],
            "required_reviewer_mode": "HUMAN_EXPERT",
            "gpt_proposal": {
                "labels_sha256": "a" * 64,
                "answerability": "ANSWERABLE",
                "expected_route": "HYBRID_QA",
                "chunk_judgments": [],
            },
        }
        decision = build_decision_template(entry)
        self.assertEqual(decision["review_outcome"], "PENDING")
        self.assertEqual(decision["expert_confirmation"], "PENDING")
        self.assertEqual(
            decision["corrected_labels"]["answerability"], "ANSWERABLE"
        )

    def test_zip_has_deterministic_members_and_no_extra_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "review.zip"
            files = {"b.json": b"{}\n", "README.md": b"review\n"}
            created_at = datetime.fromisoformat("2026-07-21T18:00:00+08:00")
            _write_deterministic_zip(path, files, created_at)
            first = path.read_bytes()
            _write_deterministic_zip(path, files, created_at)
            self.assertEqual(path.read_bytes(), first)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(archive.namelist(), ["README.md", "b.json"])


if __name__ == "__main__":
    unittest.main()
