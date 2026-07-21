import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.evaluation.retrieval_metrics import (
    RetrievalRankingResultV1,
    build_metrics_report,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "evaluation" / "formal"
MANIFEST_PATH = FIXTURE_DIR / "fixture-manifest-v1.json"
LEXICAL_PATH = FIXTURE_DIR / "fixture-rankings-lexical-v1.jsonl"
RRF_PATH = FIXTURE_DIR / "fixture-rankings-rrf-v1.jsonl"


class RetrievalMetricsTests(unittest.TestCase):
    def test_public_fixture_compares_ranking_and_refusal_metrics(self):
        report = build_metrics_report(
            MANIFEST_PATH,
            {"lexical_overlap": LEXICAL_PATH, "local_rrf": RRF_PATH},
            split="dev",
            k_values=[3],
        )

        lexical = report["runs"]["lexical_overlap"]["metrics"]
        rrf = report["runs"]["local_rrf"]["metrics"]
        self.assertEqual(lexical["recall@3"], 1.0)
        self.assertEqual(rrf["recall@3"], 1.0)
        self.assertEqual(lexical["mrr@3"], 0.5)
        self.assertEqual(rrf["mrr@3"], 1.0)
        self.assertEqual(lexical["no_answer_detection_recall"], 0.0)
        self.assertEqual(rrf["no_answer_detection_recall"], 1.0)
        self.assertEqual(
            report["comparisons"]["local_rrf"]["vs_lexical_overlap"]["ndcg@3"],
            0.29019,
        )

    def test_missing_run_coverage_is_rejected(self):
        first_line = LEXICAL_PATH.read_text(encoding="utf-8").splitlines()[0]
        with tempfile.TemporaryDirectory() as temporary_directory:
            incomplete = Path(temporary_directory) / "incomplete.jsonl"
            incomplete.write_text(first_line + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "coverage mismatch"):
                build_metrics_report(
                    MANIFEST_PATH,
                    {"lexical_overlap": incomplete},
                    split="dev",
                    k_values=[3],
                )

    def test_invalid_candidate_ranks_are_rejected(self):
        payload = json.loads(LEXICAL_PATH.read_text(encoding="utf-8").splitlines()[0])
        payload["candidates"][0]["rank"] = 2
        with self.assertRaisesRegex(ValueError, "contiguous"):
            RetrievalRankingResultV1.model_validate(payload)

    def test_evidence_found_requires_a_candidate(self):
        payload = json.loads(LEXICAL_PATH.read_text(encoding="utf-8").splitlines()[0])
        payload["candidates"] = []
        with self.assertRaisesRegex(ValueError, "at least one candidate"):
            RetrievalRankingResultV1.model_validate(payload)

    def test_mixed_run_ids_are_rejected(self):
        records = [
            json.loads(line)
            for line in LEXICAL_PATH.read_text(encoding="utf-8").splitlines()
        ]
        records[1]["run_id"] = "another-run"
        with tempfile.TemporaryDirectory() as temporary_directory:
            mixed = Path(temporary_directory) / "mixed.jsonl"
            mixed.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "one run_id"):
                build_metrics_report(
                    MANIFEST_PATH,
                    {"lexical_overlap": mixed},
                    split="dev",
                    k_values=[3],
                )

    def test_acceptance_metrics_require_explicit_unlock(self):
        completed = subprocess.run(
            [
                "python3",
                "-m",
                "backend.evaluation.retrieval_metrics",
                "--manifest",
                str(MANIFEST_PATH),
                "--run",
                f"local_rrf={RRF_PATH}",
                "--split",
                "acceptance",
                "--k",
                "3",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires --allow-acceptance", completed.stderr)


if __name__ == "__main__":
    unittest.main()
