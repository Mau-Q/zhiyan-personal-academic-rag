from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "deploy"
    / "remote"
    / "reranker-validation"
    / "run_fixed_reranker_gate.ps1"
)


class FixedRerankerRemoteScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_repository_root_is_resolved_after_parameter_binding(self) -> None:
        parameter_block = self.script.split("$ErrorActionPreference", maxsplit=1)[0]
        self.assertIn("[string]$RepositoryRoot", parameter_block)
        self.assertNotIn("$PSScriptRoot", parameter_block)
        self.assertIn(
            "Join-Path -Path $PSScriptRoot -ChildPath '..\\..\\..'",
            self.script,
        )

    def test_untracked_review_material_does_not_block_frozen_gate(self) -> None:
        self.assertIn(
            "git status --porcelain --untracked-files=no",
            self.script,
        )
        self.assertIn(
            "no tracked or staged changes",
            self.script,
        )

    def test_model_and_frozen_input_digests_remain_pinned(self) -> None:
        self.assertIn(
            "f9dd638f0b27b57667d99b01f83ca4dbb3c82983911a1ef31a4601c7b890eaec",
            self.script,
        )
        for input_name in (
            "config",
            "manifest",
            "chunks",
            "candidates",
            "document_catalog",
        ):
            self.assertRegex(self.script, rf"(?m)^        {input_name} = '[0-9a-f]{{64}}'$")


if __name__ == "__main__":
    unittest.main()
