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

    def test_tracked_text_hash_accepts_equivalent_windows_checkout(self) -> None:
        self.assertIn("function Get-LfCanonicalTextSha256", self.text)
        self.assertGreaterEqual(
            self.text.count("Get-LfCanonicalTextSha256 -LiteralPath"),
            2,
        )
        self.assertIn("NLI_TEXT_LINE_ENDING_INVALID", self.text)

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
            "diagnostic_pair_count",
            "diagnostic_sha256",
        ):
            self.assertIn(token, self.text)
        self.assertNotIn("premise =", self.text)
        self.assertNotIn("hypothesis =", self.text)

    def test_diagnostic_replay_preserves_first_report_and_exports_hashes_only(self) -> None:
        for token in (
            "[switch]$DiagnosticReplay",
            "phase4-multilingual-nli-private-diagnostic-v1",
            "--diagnostic-output",
            "private-predictions-v1.jsonl",
            "contains_raw_question_claim_or_chunk_ids",
            "NLI_PRIVATE_DIAGNOSTIC_HASH_DRIFT",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
