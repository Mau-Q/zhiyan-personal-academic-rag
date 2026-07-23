from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "deploy"
    / "remote"
    / "reranker-validation"
    / "run_online_reranker_gate.ps1"
)


class OnlineRerankerRemoteScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_repository_and_cuda_identity_are_checked_before_mutation(self) -> None:
        self.assertIn("git status --porcelain --untracked-files=no", self.script)
        self.assertIn("git fetch origin main", self.script)
        self.assertIn("Remote HEAD must equal origin/main", self.script)
        self.assertIn("torch.__version__ == '2.13.0+cu126'", self.script)
        self.assertIn("torch.version.cuda == '12.6'", self.script)
        self.assertIn("'RTX 4090' in torch.cuda.get_device_name(0)", self.script)
        self.assertLess(
            self.script.index("Pinned RTX 4090 CUDA preflight"),
            self.script.index("RUN_ISOLATED_STAGE1_CANARY"),
        )

    def test_private_inputs_are_verified_without_entering_summary(self) -> None:
        for label in (
            "Private PDF path",
            "Expected PDF SHA-256",
            "Private academic question-suite path",
            "Expected question-suite SHA-256",
            "Exact document title",
        ):
            self.assertIn(label, self.script)
        self.assertGreaterEqual(self.script.count("Get-FileHash -LiteralPath"), 3)
        summary = self.script.split("[ordered]@{", maxsplit=1)[1]
        self.assertNotIn("documentTitle", summary)
        self.assertNotIn("pdfPath", summary)
        self.assertNotIn("questionSuitePath", summary)

    def test_fixed_inputs_can_be_passed_once_and_database_secret_is_prompted(self) -> None:
        for parameter in (
            "[string]$PdfPath",
            "[string]$ExpectedPdfSha256",
            "[string]$QuestionSuitePath",
            "[string]$ExpectedQuestionSuiteSha256",
            "[string]$DocumentTitle",
            "[string]$RunId",
        ):
            self.assertIn(parameter, self.script)
        self.assertIn("-AsSecureString", self.script)
        self.assertIn("SecureStringToBSTR", self.script)
        self.assertIn("ZeroFreeBSTR", self.script)
        self.assertIn("[Uri]::EscapeDataString", self.script)
        self.assertIn("$databaseUrlCreatedByScript", self.script)
        self.assertIn(
            "Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue",
            self.script,
        )
        self.assertNotIn("Write-Output $env:DATABASE_URL", self.script)
        self.assertNotIn("Write-Host $env:DATABASE_URL", self.script)

    def test_gate_disables_generation_and_requires_combined_p95(self) -> None:
        self.assertIn(
            "online-fixed-cross-encoder-windows-rtx4090-v1.json",
            self.script,
        )
        self.assertIn("'--online-reranker-latency-repetitions'", self.script)
        self.assertNotIn("'--generation-model'", self.script)
        self.assertIn("sample_count -lt 30", self.script)
        self.assertIn("combined_retrieval_latency_ms_p95 -gt 300", self.script)
        self.assertIn("fallback_count -ne 0", self.script)
        self.assertIn("candidate_set_expanded -ne $false", self.script)

    def test_summary_is_sanitized_and_lifecycle_closed(self) -> None:
        for field in (
            "head_commit",
            "model_revision",
            "model_snapshot_sha256",
            "sample_count",
            "applied_count",
            "base_retrieval_latency_ms_p95",
            "combined_retrieval_latency_ms_p95",
            "reranker_latency_ms_p95",
            "fallback_count",
            "candidate_set_expanded",
            "candidate_bound_violated",
            "base_retrieval_stage_status",
            "base_retrieval_stage_sample_count",
            "ready_route_resolution_latency_ms_p95",
            "chunk_snapshot_latency_ms_p95",
            "elasticsearch_validation_work_latency_ms_p95",
            "elasticsearch_query_work_latency_ms_p95",
            "elasticsearch_total_work_latency_ms_p95",
            "milvus_validation_work_latency_ms_p95",
            "query_embedding_work_latency_ms_p95",
            "milvus_ann_search_work_latency_ms_p95",
            "milvus_total_work_latency_ms_p95",
            "backend_parallel_wall_latency_ms_p95",
            "ready_revalidation_latency_ms_p95",
            "rrf_fusion_latency_ms_p95",
            "retriever_total_latency_ms_p95",
            "cleanup_jobs_succeeded",
            "inactive_answer_api_status",
            "report_sha256",
            "stable_error_code",
        ):
            self.assertRegex(self.script, rf"(?m)^        {field} = ")
        self.assertIn("$pythonExitCode -ne 0", self.script)
        self.assertIn("$report.status -ne 'FAIL'", self.script)
        self.assertIn(
            "$report.online_reranker.base_retrieval_stages.status -ne 'PASS'",
            self.script,
        )


if __name__ == "__main__":
    unittest.main()
