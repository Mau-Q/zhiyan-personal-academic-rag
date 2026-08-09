from __future__ import annotations

import copy
import unittest
from pathlib import Path

from scripts.adjudicate_phase3_candidate_ladder_report import (
    ReportRejected,
    adjudicate,
)
from scripts.build_phase3_comparison_dev_package import TARGET_IDS, TARGET_IDS_SHA256
from scripts.run_phase3_candidate_ladder_localization import (
    CONFIRMATION,
    DIAGNOSTIC_RUN_ID,
    EXECUTION_BOUNDARY,
    REPORT_SCHEMA_VERSION,
    _classify,
    build_parser,
)


HEAD = "a" * 40
MANIFEST = "b" * 64
REPORT_SHA = "c" * 64
ROOT = Path(__file__).resolve().parents[2]
POWERSHELL_PATH = (
    ROOT
    / "deploy"
    / "remote"
    / "phase3-comparison-validation"
    / "run_phase3_candidate_ladder_localization.ps1"
)


def candidate(
    chunk_id: str,
    document_id: str,
    rank: int,
    score: float,
    *,
    target_match: bool,
    membership=None,
):
    return {
        "rank": rank,
        "score": score,
        "runtime_chunk_id": f"runtime_{chunk_id}",
        "source_chunk_id": chunk_id,
        "runtime_document_id": f"runtime_{document_id}",
        "source_document_id": document_id,
        "page_start": rank,
        "page_end": rank,
        "section_path": "Method",
        "target_match": target_match,
        "target_relevance": 2 if target_match else 0,
        "source_membership": [] if membership is None else membership,
    }


def case_payload(case_id: str):
    documents = ["doc_left", "doc_right"]
    left_membership = [
        {
            "backend": "elasticsearch_bm25",
            "source_document_id": "doc_left",
            "rank": 1,
        }
    ]
    right_membership = [
        {
            "backend": "milvus_dense_bge_m3",
            "source_document_id": "doc_right",
            "rank": 1,
        }
    ]
    left_score = 1 / 61
    right_score = 1 / 61
    backend_ladders = [
        {
            "backend": "elasticsearch_bm25",
            "source_document_id": "doc_left",
            "runtime_document_id": "runtime_doc_left",
            "document_version_id": "version_left",
            "physical_route": "es_left",
            "requested_candidate_k": 20,
            "returned_candidate_count": 1,
            "candidates": [
                candidate(
                    "chunk_left", "doc_left", 1, 4.0, target_match=True
                )
            ],
        },
        {
            "backend": "milvus_dense_bge_m3",
            "source_document_id": "doc_left",
            "runtime_document_id": "runtime_doc_left",
            "document_version_id": "version_left",
            "physical_route": "milvus_left",
            "requested_candidate_k": 20,
            "returned_candidate_count": 0,
            "candidates": [],
        },
        {
            "backend": "elasticsearch_bm25",
            "source_document_id": "doc_right",
            "runtime_document_id": "runtime_doc_right",
            "document_version_id": "version_right",
            "physical_route": "es_right",
            "requested_candidate_k": 20,
            "returned_candidate_count": 0,
            "candidates": [],
        },
        {
            "backend": "milvus_dense_bge_m3",
            "source_document_id": "doc_right",
            "runtime_document_id": "runtime_doc_right",
            "document_version_id": "version_right",
            "physical_route": "milvus_right",
            "requested_candidate_k": 20,
            "returned_candidate_count": 1,
            "candidates": [
                candidate(
                    "chunk_right", "doc_right", 1, 0.9, target_match=True
                )
            ],
        },
    ]
    fused = [
        candidate(
            "chunk_left",
            "doc_left",
            1,
            left_score,
            target_match=True,
            membership=left_membership,
        ),
        candidate(
            "chunk_right",
            "doc_right",
            2,
            right_score,
            target_match=True,
            membership=right_membership,
        ),
    ]
    fused[1]["page_start"] = 1
    fused[1]["page_end"] = 1
    ladder = {
        "configuration": {
            "candidate_k": 20,
            "rrf_k": 60,
            "final_top_k": 3,
            "vector_min_score": 0.5,
            "query_decomposition_enabled": False,
            "route_coverage_enabled": False,
            "reranker_enabled": False,
        },
        "cutoff_boundary": {
            "backend_request_candidate_k": 20,
            "pre_cutoff_ranking_observed": False,
            "returned_candidates_forwarded_to_fusion": True,
            "below_backend_request_boundary": "UNOBSERVED_NOT_INFERRED",
        },
        "backend_ladders": backend_ladders,
        "target_boundaries": [
            {
                "source_chunk_id": "chunk_left",
                "source_document_id": "doc_left",
                "backend_observations": [
                    {
                        "backend": "elasticsearch_bm25",
                        "state": "RETURNED_TO_FUSION",
                        "rank": 1,
                        "returned_but_below_configured_cutoff": False,
                    },
                    {
                        "backend": "milvus_dense_bge_m3",
                        "state": "NOT_OBSERVED_WITHIN_BACKEND_REQUEST_BOUNDARY",
                        "rank": None,
                        "returned_but_below_configured_cutoff": False,
                    },
                ],
                "rrf_rank": 1,
                "final_top3_rank": 1,
            },
            {
                "source_chunk_id": "chunk_right",
                "source_document_id": "doc_right",
                "backend_observations": [
                    {
                        "backend": "elasticsearch_bm25",
                        "state": "NOT_OBSERVED_WITHIN_BACKEND_REQUEST_BOUNDARY",
                        "rank": None,
                        "returned_but_below_configured_cutoff": False,
                    },
                    {
                        "backend": "milvus_dense_bge_m3",
                        "state": "RETURNED_TO_FUSION",
                        "rank": 1,
                        "returned_but_below_configured_cutoff": False,
                    },
                ],
                "rrf_rank": 2,
                "final_top3_rank": 2,
            },
        ],
        "rrf_ladder": fused,
        "final_top3": copy.deepcopy(fused),
    }
    target = {
        "required_documents": documents,
        "relevant": {"chunk_left": {}, "chunk_right": {}},
    }
    return {
        "case_id": case_id,
        "required_source_documents": documents,
        "required_source_chunk_ids": ["chunk_left", "chunk_right"],
        "frozen_bilateral_metric_passed": True,
        "ladder": ladder,
        "classification": _classify(ladder, target),
    }


def valid_report():
    cases = [case_payload(case_id) for case_id in TARGET_IDS]
    classifications = [
        case["classification"]["primary_classification"] for case in cases
    ]
    counts = {
        value: classifications.count(value) for value in sorted(set(classifications))
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "PASS",
        "experiment_decision": "LOCALIZATION_INCONCLUSIVE",
        "execution_boundary": EXECUTION_BOUNDARY,
        "identity": {
            "run_id": DIAGNOSTIC_RUN_ID,
            "source_commit": HEAD,
            "input_manifest_sha256": MANIFEST,
            "cohort": list(TARGET_IDS),
            "cohort_sha256": TARGET_IDS_SHA256,
            "owner_id": f"phase3_candidate_ladder_{DIAGNOSTIC_RUN_ID}",
            "ready_document_count": 3,
            "runtime_chunk_count": 316,
            "document_id_map": {},
            "embedding": {
                "provider": "ollama",
                "model": "bge-m3:latest",
                "digest": "digest",
            },
            "routes": [
                {
                    "source_document_id": f"source_{index}",
                    "runtime_document_id": f"runtime_{index}",
                    "document_version_id": f"version_{index}",
                    "elasticsearch_index": f"es_{index}",
                    "milvus_collection": f"milvus_{index}",
                }
                for index in range(3)
            ],
            "configuration": {
                "candidate_k": 20,
                "rrf_k": 60,
                "final_top_k": 3,
                "query_decomposition_enabled": False,
                "route_coverage_enabled": False,
                "reranker_enabled": False,
            },
        },
        "cases": cases,
        "aggregate": {
            "case_count": 4,
            "primary_classification_counts": counts,
            "scope": "FROZEN_4_DEV_ONLY",
        },
        "split_isolation": {
            "dev": "USED_FROZEN_4_ONLY",
            "test": "NOT_READ_NOT_RUN",
            "acceptance": "NOT_READ_NOT_RUN",
        },
        "behavior_freeze": {
            "retrieval_requests_added": 0,
            "backend_candidate_count_changed": False,
            "retrieval_scoring_changed": False,
            "public_answer_api_schema_changed": False,
            "generation_or_judge_calls": 0,
        },
        "performance_boundary": "NO_300MS_SLO_CONCLUSION_DIAGNOSTIC_METADATA_ONLY",
        "strategy_handoff": "NO_NEXT_ALGORITHM_SELECTED",
        "run_id": DIAGNOSTIC_RUN_ID,
        "head_commit": HEAD,
        "input_manifest_sha256": MANIFEST,
        "cohort_sha256": TARGET_IDS_SHA256,
        "primary_stage": "COMPLETE",
        "cleanup": {
            "status": "PASS",
            "scheduled_versions": 3,
            "jobs_succeeded": 9,
            "jobs_observed": 9,
            "jobs_expected": 9,
            "ready_reconciliation_failed_closed": True,
            "deleted_answer_api_status": 403,
        },
    }


class Phase3CandidateLadderLocalizationTests(unittest.TestCase):
    def test_parser_and_frozen_identity_require_one_versioned_run(self):
        args = build_parser().parse_args(
            [
                "--input-root",
                "runtime/input",
                "--expected-manifest-sha256",
                MANIFEST,
                "--run-id",
                DIAGNOSTIC_RUN_ID,
                "--expected-head-commit",
                HEAD,
                "--confirm",
                CONFIRMATION,
                "--output",
                "runtime/report.json",
            ]
        )
        self.assertEqual(args.run_id, DIAGNOSTIC_RUN_ID)
        self.assertEqual(
            TARGET_IDS_SHA256,
            "3f6e132954a721dea34bed26d75d4c2df84f589f2aab0c0323005b0cdfebccb8",
        )

    def test_classification_keeps_unobserved_cutoff_unknown(self):
        case = case_payload(TARGET_IDS[0])
        classification = case["classification"]
        self.assertEqual(
            classification["primary_classification"],
            "INCONCLUSIVE_WITH_CURRENT_EVIDENCE",
        )
        self.assertEqual(
            classification["candidate_cutoff_classification"],
            "UNAVAILABLE_PRE_CUTOFF_NOT_OBSERVED",
        )

    def test_windows_entry_is_single_run_control_only_and_cleanup_bound(self):
        script = POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn("Target: Windows PowerShell 5.1", script)
        self.assertIn(DIAGNOSTIC_RUN_ID, script)
        self.assertIn(CONFIRMATION, script)
        self.assertIn("$headCommit -ne $originCommit", script)
        self.assertIn("scripts/run_phase3_candidate_ladder_localization.py", script)
        self.assertIn("scripts/adjudicate_phase3_candidate_ladder_report.py", script)
        self.assertIn("$env:PHASE3_COMPARISON_DECOMPOSITION_ENABLED = 'false'", script)
        self.assertIn("$env:PHASE3_COMPARISON_ROUTE_COVERAGE_ENABLED = 'false'", script)
        self.assertIn("Remove-Item -LiteralPath $inputRoot -Recurse -Force", script)
        self.assertIn("-AsSecureString", script)
        self.assertNotIn("qwen", script.casefold())
        self.assertNotIn("judge", script.casefold())

    def test_adjudicator_recomputes_rrf_and_accepts_inconclusive_report(self):
        result = adjudicate(
            valid_report(),
            expected_head_commit=HEAD,
            expected_input_manifest_sha256=MANIFEST,
            expected_run_id=DIAGNOSTIC_RUN_ID,
            report_sha256=REPORT_SHA,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["experiment_decision"], "LOCALIZATION_INCONCLUSIVE")
        self.assertEqual(result["cleanup"], "PASS_9_OF_9_READY_CLOSED_DELETED_403")

    def test_adjudicator_rejects_rrf_score_or_final_prefix_drift(self):
        for mutation in ("score", "final"):
            with self.subTest(mutation=mutation):
                report = valid_report()
                if mutation == "score":
                    report["cases"][0]["ladder"]["rrf_ladder"][0]["score"] += 0.1
                else:
                    report["cases"][0]["ladder"]["final_top3"].reverse()
                with self.assertRaises(ReportRejected):
                    adjudicate(
                        report,
                        expected_head_commit=HEAD,
                        expected_input_manifest_sha256=MANIFEST,
                        expected_run_id=DIAGNOSTIC_RUN_ID,
                        report_sha256=REPORT_SHA,
                    )

    def test_adjudicator_rejects_holdout_or_cleanup_drift(self):
        for path in ("test", "cleanup"):
            with self.subTest(path=path):
                report = valid_report()
                if path == "test":
                    report["split_isolation"]["test"] = "READ"
                else:
                    report["cleanup"]["jobs_succeeded"] = 8
                with self.assertRaises(ReportRejected):
                    adjudicate(
                        report,
                        expected_head_commit=HEAD,
                        expected_input_manifest_sha256=MANIFEST,
                        expected_run_id=DIAGNOSTIC_RUN_ID,
                        report_sha256=REPORT_SHA,
                    )


if __name__ == "__main__":
    unittest.main()
