from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "deploy/remote/phase4-nli-validation/run_phase4_multilingual_nli_gate.ps1"
)


class Phase4MultilingualNliRemoteScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_paths_are_initialized_after_parameter_binding(self) -> None:
        param_end = self.text.index("$ErrorActionPreference")
        for token in ("$PSScriptRoot", "Resolve-Path", "$RepositoryRoot = Join-Path"):
            self.assertGreater(self.text.index(token), param_end)

    def test_public_repository_and_private_input_fail_closed(self) -> None:
        for token in (
            "git status --porcelain --untracked-files=no",
            "git fetch origin main",
            "$headCommit -ne $originCommit",
            "EF3FC1288FD78CD886793959C886C0AC2CE62AB822D556FA8527EE7C58E53B18",
            "13B7DDFB0185BA03F251664366D5AB28A0CAE64ADDA9EF9A57DA563BE0AE2C6E",
            "NLI_IMPORT_DIRECTORY_EXISTS_WITHOUT_EXACT_INPUT",
        ):
            self.assertIn(token, self.text)
        self.assertLess(
            self.text.index("NLI_PRIVATE_PACKAGE_HASH_DRIFT"),
            self.text.index("Expand-Archive"),
        )

    def test_cuda_model_and_runner_are_frozen(self) -> None:
        for token in (
            "2.13.0+cu126",
            "https://download.pytorch.org/whl/cu126",
            "RTX 4090",
            "torch.ones((32, 32), device=\"cuda\")",
            "b5113eb38ab63efdd7f280f8c144ea8b13f978ce",
            "7E973B42BF69D9475C065D4DEB04745659BADF94CE054FD1DE0F9CC1CAEEAFD5",
            "run_phase4_multilingual_nli_gate.py",
            "--config-sha256",
            "--private-input",
            "--model-cache",
        ):
            self.assertIn(token, self.text)

    def test_summary_is_sanitized_and_online_remains_disabled(self) -> None:
        for token in (
            "candidate_supported_retention",
            "human_finalized_positive_retention",
            "component_latency_ms_p95",
            "quality_decision",
            "truncated_pair_count",
            "online_enforcement_enabled = $false",
            "stable_error_code = 'NONE'",
            "NOT_MEASURABLE_NO_HUMAN_ADJUDICATED_NEGATIVES",
        ):
            self.assertIn(token, self.text)
        self.assertNotIn("premise =", self.text)
        self.assertNotIn("hypothesis =", self.text)


if __name__ == "__main__":
    unittest.main()
