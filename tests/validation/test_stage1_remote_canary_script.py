from __future__ import annotations

import subprocess
import sys
import unittest

from scripts.run_stage1_remote_canary import (
    EXPECTED_CLEANUP_JOBS,
    REPORT_SCHEMA_VERSION,
    build_parser,
)


class Stage1RemoteCanaryScriptTests(unittest.TestCase):
    def test_v2_contract_includes_runtime_storage_and_three_cleanup_jobs(self):
        args = build_parser().parse_args(
            [
                "--pdf",
                "runtime/canary.pdf",
                "--expected-sha256",
                "0" * 64,
                "--run-id",
                "canary_001",
                "--confirm",
                "RUN_ISOLATED_STAGE1_CANARY",
                "--output",
                "runtime/report.json",
            ]
        )

        self.assertEqual(REPORT_SCHEMA_VERSION, "stage1_remote_canary_report_v2")
        self.assertEqual(EXPECTED_CLEANUP_JOBS, 3)
        self.assertEqual(str(args.pdf_object_root), "runtime/stage1-pdf-objects")

    def test_mutation_requires_exact_confirmation_before_pdf_or_services(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_stage1_remote_canary.py",
                "--pdf",
                "does-not-exist.pdf",
                "--expected-sha256",
                "0" * 64,
                "--run-id",
                "canary_001",
                "--confirm",
                "NO",
                "--output",
                "runtime/should-not-exist.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("EXPLICIT_CONFIRMATION_REQUIRED", result.stderr)
        self.assertNotIn("does-not-exist", result.stderr)


if __name__ == "__main__":
    unittest.main()
