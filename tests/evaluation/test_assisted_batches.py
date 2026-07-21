import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_assisted_evaluation_batches import prepare_batches


ROOT = Path(__file__).resolve().parents[2]


class AssistedEvaluationBatchTests(unittest.TestCase):
    def _active_chunk_file(self, directory: Path) -> Path:
        chunks = json.loads(
            (ROOT / "fixtures" / "chunks-v1.json").read_text(encoding="utf-8")
        )
        path = directory / "active-chunks.json"
        path.write_text(
            json.dumps([chunk for chunk in chunks if chunk["is_active"]]),
            encoding="utf-8",
        )
        return path

    def test_prepares_exact_deterministic_500_slot_distribution(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            chunks_path = self._active_chunk_file(temporary)
            first = temporary / "first"
            second = temporary / "second"
            kwargs = {
                "policy_path": ROOT / "evaluation" / "assisted-500-policy-v1.json",
                "chunks_path": chunks_path,
                "prompt_path": ROOT
                / "evaluation"
                / "prompts"
                / "assisted-question-generation-v1.md",
            }
            first_report = prepare_batches(output_dir=first, **kwargs)
            second_report = prepare_batches(output_dir=second, **kwargs)

            self.assertEqual(first_report["slot_count"], 500)
            self.assertEqual(first_report["batch_count"], 50)
            self.assertEqual(first_report["distributions"]["split"], {
                "acceptance": 100,
                "dev": 300,
                "test": 100,
            })
            self.assertEqual(first_report["distributions"]["difficulty"]["hard"], 50)
            self.assertEqual(first_report["slot_sha256"], second_report["slot_sha256"])
            self.assertEqual(
                (first / "slots-v1.jsonl").read_bytes(),
                (second / "slots-v1.jsonl").read_bytes(),
            )

    def test_rejects_policy_whose_quotas_do_not_sum_to_500(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            policy = json.loads(
                (ROOT / "evaluation" / "assisted-500-policy-v1.json")
                .read_text(encoding="utf-8")
            )
            policy["language_quotas"]["zh"] -= 1
            policy_path = temporary / "invalid-policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must sum to target_size"):
                prepare_batches(
                    policy_path=policy_path,
                    chunks_path=self._active_chunk_file(temporary),
                    prompt_path=ROOT
                    / "evaluation"
                    / "prompts"
                    / "assisted-question-generation-v1.md",
                    output_dir=temporary / "output",
                )


if __name__ == "__main__":
    unittest.main()
