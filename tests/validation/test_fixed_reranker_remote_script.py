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

    def test_cuda_runtime_is_pinned_and_allocated_before_the_gate(self) -> None:
        self.assertIn("$TorchPackage = 'torch==2.13.0+cu126'", self.script)
        self.assertIn(
            "$TorchIndexUrl = 'https://download.pytorch.org/whl/cu126'",
            self.script,
        )
        self.assertIn("Get-Command -Name 'nvidia-smi.exe'", self.script)
        self.assertIn(
            "pip install --force-reinstall --no-deps $TorchPackage --index-url $TorchIndexUrl",
            self.script,
        )
        self.assertIn("torch.version.cuda == '12.6'", self.script)
        self.assertIn("'RTX 4090' in gpu_name", self.script)
        self.assertIn("torch.ones(1, device='cuda')", self.script)
        self.assertLess(
            self.script.index("pip install --force-reinstall --no-deps"),
            self.script.index("pip install -e '.[reranker]'"),
        )

    def test_sanitized_summary_records_cuda_runtime_identity(self) -> None:
        for field in (
            "torch_version",
            "cuda_runtime",
            "gpu_name",
            "nvidia_smi",
        ):
            self.assertRegex(self.script, rf"(?m)^        {field} = ")

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
