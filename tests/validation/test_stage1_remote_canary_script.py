from __future__ import annotations

import subprocess
import sys
import unittest


class Stage1RemoteCanaryScriptTests(unittest.TestCase):
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
