import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.evaluation.formal_corpus import EvaluationItemV1, validate_corpus


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
