from __future__ import annotations

import tempfile
import unittest
import zipfile
from hashlib import sha256
from pathlib import Path

from scripts.build_fixed_reranker_input_package import build_package


class FixedRerankerInputPackageTests(unittest.TestCase):
    def test_package_is_deterministic_exact_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            members = {
                "runtime/private/a.json": b'{"a":1}\n',
                "runtime/private/b.jsonl": b'{"b":2}\n',
            }
            expected = {}
            for relative_path, value in members.items():
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
                expected[relative_path] = sha256(value).hexdigest()

            first = root / "first.zip"
            second = root / "second.zip"
            first_report = build_package(
                repository_root=root,
                output_path=first,
                expected_files=expected,
            )
            second_report = build_package(
                repository_root=root,
                output_path=second,
                expected_files=expected,
            )

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_report["package_sha256"], second_report["package_sha256"])
            self.assertEqual(
                first_report["boundary"],
                "PRIVATE_IGNORED_RUNTIME_HANDOFF_NOT_FOR_GIT",
            )
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), sorted(members))
                for relative_path, value in members.items():
                    self.assertEqual(archive.read(relative_path), value)

    def test_source_digest_drift_fails_before_package_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "runtime/private/input.json"
            source.parent.mkdir(parents=True)
            source.write_text("{}\n", encoding="utf-8")
            output = root / "output.zip"

            with self.assertRaisesRegex(ValueError, "digest drifted"):
                build_package(
                    repository_root=root,
                    output_path=output,
                    expected_files={
                        "runtime/private/input.json": "0" * 64,
                    },
                )
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
