import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from scripts.init_assisted_evaluation_workspace import initialize_workspace


ROOT = Path(__file__).resolve().parents[2]


class AssistedEvaluationWorkspaceTests(unittest.TestCase):
    def test_initializes_frozen_empty_500_item_workspace(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            output_dir = temporary / "evaluation"
            chunks = json.loads(
                (ROOT / "fixtures" / "chunks-v1.json").read_text(encoding="utf-8")
            )
            active_chunks = [chunk for chunk in chunks if chunk["is_active"]]
            chunks_path = temporary / "active-chunks.json"
            chunks_path.write_text(json.dumps(active_chunks), encoding="utf-8")
            report = initialize_workspace(
                chunks_path=chunks_path,
                output_dir=output_dir,
                corpus_id="fixture-assisted-source-v1",
                dataset_id="fixture-assisted-evaluation-v1",
                dataset_version="fixture-assisted-v1",
                created_at=datetime.fromisoformat("2026-07-21T12:00:00+08:00"),
            )

            manifest = json.loads(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )
            snapshot = json.loads(
                (output_dir / "source-snapshot-v1.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["target_size"], 500)
            self.assertEqual(manifest["status"], "DATA_COLLECTION")
            self.assertEqual(snapshot["chunk_count"], len(active_chunks))
            self.assertEqual(report["status"], "SOURCE_FROZEN_DATA_COLLECTION_PENDING")
            self.assertFalse(report["engineering_ready"])
            self.assertFalse(report["lock_ready"])
            self.assertEqual((output_dir / "items-v1.jsonl").read_bytes(), b"")
            self.assertEqual((output_dir / "annotations-v1.jsonl").read_bytes(), b"")

    def test_refuses_to_overwrite_existing_workspace(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "evaluation"
            output_dir.mkdir()
            (output_dir / "keep.txt").write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                initialize_workspace(
                    chunks_path=ROOT / "fixtures" / "chunks-v1.json",
                    output_dir=output_dir,
                    corpus_id="fixture-assisted-source-v1",
                    dataset_id="fixture-assisted-evaluation-v1",
                    dataset_version="fixture-assisted-v1",
                    created_at=datetime.fromisoformat("2026-07-21T12:00:00+08:00"),
                )


if __name__ == "__main__":
    unittest.main()
