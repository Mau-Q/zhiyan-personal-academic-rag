import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.evaluation.formal_corpus import (
    AnnotationRecordV1,
    EvaluationItemV1,
    validate_corpus,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "evaluation" / "formal"
MANIFEST_PATH = FIXTURE_DIR / "fixture-manifest-v1.json"


def write_jsonl(path: Path, records: list[dict]) -> str:
    payload = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FormalCorpusTests(unittest.TestCase):
    def test_public_fixture_is_valid_but_truthfully_not_lock_ready(self):
        report = validate_corpus(MANIFEST_PATH)

        self.assertEqual(report["target_size"], 500)
        self.assertEqual(report["item_count"], 4)
        self.assertEqual(report["primary_item_count"], 4)
        self.assertEqual(report["online_hard_case_count"], 0)
        self.assertEqual(report["annotation_record_count"], 12)
        self.assertFalse(report["lock_ready"])
        self.assertFalse(report["engineering_ready"])
        self.assertEqual(report["engineering_target_size"], 500)
        self.assertTrue(any("below target_size" in value for value in report["blockers"]))

    def test_online_hard_cases_do_not_count_toward_primary_target(self):
        report = validate_corpus(MANIFEST_PATH)

        self.assertEqual(report["primary_item_count"], report["item_count"])
        self.assertTrue(
            any("primary_item_count 4" in value for value in report["blockers"])
        )

    def test_acceptance_item_must_be_blind_holdout(self):
        payload = json.loads(
            (FIXTURE_DIR / "fixture-items-v1.jsonl").read_text(encoding="utf-8").splitlines()[3]
        )
        payload["blind_holdout"] = False
        with self.assertRaisesRegex(ValueError, "acceptance items must be blind_holdout"):
            EvaluationItemV1.model_validate(payload)

    def test_gpt_annotation_requires_reproducible_model_identity(self):
        payload = json.loads(
            (ROOT / "contracts" / "examples" / "retrieval-annotation-record-v1.json")
            .read_text(encoding="utf-8")
        )
        AnnotationRecordV1.model_validate(payload)
        payload["model_identity"] = None
        with self.assertRaisesRegex(ValueError, "GPT annotations require"):
            AnnotationRecordV1.model_validate(payload)

    def test_low_risk_item_can_use_single_gpt_assisted_review(self):
        payload = json.loads(
            (FIXTURE_DIR / "fixture-items-v1.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        payload.update(
            {
                "annotation_status": "GPT_ASSISTED",
                "annotation_record_ids": ["ann.fixture.answerable.gpt"],
                "final_annotation_id": None,
                "agreement_score": None,
            }
        )
        EvaluationItemV1.model_validate(payload)

    def test_consensus_does_not_require_adjudication_but_conflict_does(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            items = [
                json.loads(line)
                for line in (FIXTURE_DIR / "fixture-items-v1.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            annotations = [
                json.loads(line)
                for line in (FIXTURE_DIR / "fixture-annotations-v1.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            question_id = items[0]["question_id"]
            final_id = items[0]["final_annotation_id"]
            items[0]["annotation_status"] = "DOUBLE_ANNOTATED"
            items[0]["annotation_record_ids"] = items[0]["annotation_record_ids"][:2]
            items[0]["final_annotation_id"] = None
            annotations = [
                record for record in annotations if record["annotation_id"] != final_id
            ]
            manifest["items_path"] = "items.jsonl"
            manifest["annotation_records_path"] = "annotations.jsonl"
            manifest["items_sha256"] = write_jsonl(temporary / "items.jsonl", items)
            manifest["annotation_records_sha256"] = write_jsonl(
                temporary / "annotations.jsonl", annotations
            )
            manifest_path = temporary / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = validate_corpus(manifest_path)
            self.assertFalse(
                any(
                    question_id in blocker and "adjudication" in blocker
                    for blocker in report["blockers"]
                )
            )

            for record in annotations[:2]:
                record.update(
                    {
                        "actor_type": "GPT",
                        "model_identity": "same-model",
                        "prompt_version": "judge-v1",
                        "temperature": 0.0,
                    }
                )
            manifest["annotation_records_sha256"] = write_jsonl(
                temporary / "annotations.jsonl", annotations
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report = validate_corpus(manifest_path)
            self.assertTrue(
                any(
                    question_id in blocker and "two independent reviewers" in blocker
                    for blocker in report["blockers"]
                )
            )

            items[0]["agreement_score"] = 0.5
            manifest["items_sha256"] = write_jsonl(temporary / "items.jsonl", items)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report = validate_corpus(manifest_path)
            self.assertTrue(
                any(
                    question_id in blocker and "conflict requiring adjudication" in blocker
                    for blocker in report["blockers"]
                )
            )

    def test_hash_drift_and_cross_split_leakage_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            items = [
                json.loads(line)
                for line in (FIXTURE_DIR / "fixture-items-v1.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            annotations = (FIXTURE_DIR / "fixture-annotations-v1.jsonl").read_bytes()
            (temporary / "annotations.jsonl").write_bytes(annotations)
            manifest["items_path"] = "items.jsonl"
            manifest["annotation_records_path"] = "annotations.jsonl"
            manifest["annotation_records_sha256"] = hashlib.sha256(annotations).hexdigest()
            write_jsonl(temporary / "items.jsonl", items)
            manifest["items_sha256"] = "0" * 64
            manifest_path = temporary / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "items SHA-256"):
                validate_corpus(manifest_path)

            items[3]["leakage_group_id"] = items[0]["leakage_group_id"]
            manifest["items_sha256"] = write_jsonl(temporary / "items.jsonl", items)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "leakage groups"):
                validate_corpus(manifest_path)

    def test_require_lock_ready_returns_one_for_incomplete_fixture(self):
        completed = subprocess.run(
            [
                "python3",
                "-m",
                "backend.evaluation.formal_corpus",
                "--manifest",
                str(MANIFEST_PATH),
                "--require-lock-ready",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn('"lock_ready": false', completed.stdout)

    def test_require_engineering_ready_returns_one_for_incomplete_fixture(self):
        completed = subprocess.run(
            [
                "python3",
                "-m",
                "backend.evaluation.formal_corpus",
                "--manifest",
                str(MANIFEST_PATH),
                "--require-engineering-ready",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn('"engineering_ready": false', completed.stdout)

    def test_generated_contracts_are_current(self):
        completed = subprocess.run(
            ["python3", "scripts/export_evaluation_contracts.py", "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
