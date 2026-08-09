from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from scripts.run_phase3_fixed_reranker_screening import (
    COHORT,
    DIAGNOSTIC_SOURCE_COMMIT,
    DOCUMENT_SOURCE_SHA256,
    EXCLUDED_CASE,
    FULL_DIAGNOSTIC_COHORT,
    INPUT_MANIFEST_SHA256,
    _bilateral_top3,
    _build_identity_from_validated_inputs,
    _ordered_indices,
    _screening_decision,
    _sorted_optional_ranks,
    TOP20_CONFIG_PATH,
    TOP50_CONFIG_PATH,
    TOP20_SCREENING_IDENTITY_SHA256,
)

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "machine/phase3_fixed_reranker_screening_gate.json"
TOP50_GATE_PATH = (
    ROOT / "machine/phase3_fixed_reranker_top50_screening_gate.json"
)


def _fixture_sha256(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _synthetic_screening_inputs() -> dict:
    """Build contract-only screening inputs; these are not historical evidence."""
    documents = tuple(DOCUMENT_SOURCE_SHA256)
    chunks = []
    rows = []
    cases = []
    case_contracts = (
        (COHORT[0], documents[0], documents[2], 5, 25, 50),
        (COHORT[1], documents[0], documents[1], 10, 30, 50),
        (COHORT[2], documents[1], documents[2], 8, 16, 40),
    )
    for case_index, (
        case_id,
        first_document,
        second_document,
        first_rank,
        second_rank,
        count,
    ) in enumerate(case_contracts):
        candidates = []
        judgments = []
        required_chunk_ids = []
        for rank in range(1, count + 1):
            document_id = first_document if rank % 2 else second_document
            relevance = 0
            if rank == first_rank:
                document_id = first_document
                relevance = 3
            elif rank == second_rank:
                document_id = second_document
                relevance = 2
            chunk_id = f"fixture_{case_index}_{rank:03d}"
            section_path = f"Synthetic section {case_index}.{rank}"
            chunk = {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "version_id": f"version_{DOCUMENT_SOURCE_SHA256[document_id][:24]}",
                "page_start": rank,
                "page_end": rank,
                "section_path": section_path,
                "text": f"Synthetic contract text for {chunk_id}.",
            }
            candidate = {
                "rank": rank,
                "runtime_chunk_id": f"runtime_{chunk_id}",
                "source_chunk_id": chunk_id,
                "source_document_id": document_id,
                "page_start": rank,
                "page_end": rank,
                "section_path": section_path,
                "target_relevance": relevance,
            }
            chunks.append(chunk)
            candidates.append(candidate)
            if relevance:
                required_chunk_ids.append(chunk_id)
                judgments.append(
                    {
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "relevance": relevance,
                    }
                )
        cases.append(
            {
                "case_id": case_id,
                "required_source_chunk_ids": required_chunk_ids,
                "required_source_documents": [first_document, second_document],
                "ladder": {
                    "rrf_ladder": candidates,
                    "final_top3": candidates[:3],
                },
            }
        )
        rows.append(
            {
                "question_id": case_id,
                "split": "dev",
                "question": f"Synthetic screening question {case_index}?",
                "final_labels": {"chunk_judgments": judgments},
            }
        )

    while len(chunks) < 316:
        index = len(chunks)
        document_id = documents[index % len(documents)]
        chunks.append(
            {
                "chunk_id": f"unused_fixture_{index:03d}",
                "document_id": document_id,
                "version_id": f"version_{DOCUMENT_SOURCE_SHA256[document_id][:24]}",
                "page_start": index + 1,
                "page_end": index + 1,
                "section_path": f"Unused synthetic section {index}",
                "text": f"Unused synthetic contract text {index}.",
            }
        )
    while len(rows) < 105:
        index = len(rows)
        rows.append(
            {
                "question_id": f"unused.dev.{index:03d}",
                "split": "dev",
                "question": f"Unused synthetic question {index}?",
                "final_labels": {"chunk_judgments": []},
            }
        )

    report = {
        "status": "PASS",
        "run_id": "phase3_candidate_ladder_20260809_01",
        "identity": {
            "source_commit": DIAGNOSTIC_SOURCE_COMMIT,
            "input_manifest_sha256": INPUT_MANIFEST_SHA256,
            "cohort": list(FULL_DIAGNOSTIC_COHORT),
        },
        "cases": cases,
    }
    tokenizer_files = {
        name: _fixture_sha256(f"synthetic-{name}")
        for name in (
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "sentencepiece.bpe.model",
            "special_tokens_map.json",
        )
    }
    return {
        "report": report,
        "chunks": chunks,
        "dev_rows": rows,
        "titles": {
            document_id: f"Synthetic title {index}"
            for index, document_id in enumerate(documents)
        },
        "candidate_ladder_report_sha256": _fixture_sha256("synthetic-report"),
        "chunk_snapshot_sha256": _fixture_sha256("synthetic-chunks"),
        "dev_review_sha256": _fixture_sha256("synthetic-dev-review"),
        "title_catalog_sha256": _fixture_sha256("synthetic-titles"),
        "model_snapshot_sha256": _fixture_sha256("synthetic-model-snapshot"),
        "tokenizer_files": tokenizer_files,
    }


class Phase3FixedRerankerScreeningTests(unittest.TestCase):
    def _build_test_identity(self, *, head: str, config_path: Path) -> dict:
        return _build_identity_from_validated_inputs(
            expected_screening_source_commit=head,
            config_path=config_path,
            **_synthetic_screening_inputs(),
        )

    def test_top20_result_is_formalized_without_full_candidate_table(self) -> None:
        gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(gate["experiment_decision"], "SCREENING_WEAKENED")
        self.assertEqual(
            gate["formal_evidence"]["bilateral_recovery"],
            {"recovered_cases": 0, "case_count": 3},
        )
        self.assertEqual(
            [value["case_id"] for value in gate["formal_evidence"]["case_outcomes"]],
            list(COHORT),
        )
        self.assertNotIn("complete_reranked_order", GATE_PATH.read_text(encoding="utf-8"))

    def test_strategy_closeout_preserves_bounded_stop_and_hold_states(self) -> None:
        top20_gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))
        top50_gate = json.loads(TOP50_GATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(top20_gate["experiment_decision"], "SCREENING_WEAKENED")
        self.assertEqual(
            top20_gate["formal_evidence"]["bilateral_recovery"],
            {"recovered_cases": 0, "case_count": 3},
        )
        self.assertEqual(top50_gate["experiment_decision"], "SCREENING_WEAKENED")
        self.assertEqual(top50_gate["formal_evidence"]["baseline_bilateral_recovery"], "0/3")
        self.assertEqual(top50_gate["formal_evidence"]["top50_bilateral_recovery"], "0/3")

        project_state = json.loads(
            (ROOT / "machine/project_state.json").read_text(encoding="utf-8")
        )
        closeout = project_state["execution_boundaries"][
            "phase3_retrieval_ranking_optimization_closeout"
        ]
        for token in (
            "STOP",
            "PHASE3_PARTIAL",
            "NO_PROMOTION",
            "FIXED_RERANKER_FAMILY_WEAKENED",
            "COVERAGE_AWARE_RANKING_HOLD",
            "DEEP_CANDIDATE_RETRIEVAL_HOLD",
            "NEXT_EXPERIMENT_NONE",
            "TEST_ACCEPTANCE_SEALED",
            "NO_PRODUCTION_ADOPTION",
        ):
            self.assertIn(token, closeout)
        self.assertNotIn(
            "FUTURE_LOCALIZATION_OPTIONAL",
            project_state["execution_boundaries"]["phase3_phase4_unified_closeout"],
        )

        feature_list = json.loads(
            (ROOT / "machine/feature_list.json").read_text(encoding="utf-8")
        )
        feature = next(
            value
            for value in feature_list["features"]
            if value["id"] == "phase3_retrieval_ranking_optimization_closeout"
        )
        self.assertEqual(feature["status"], "COMPLETE")

        decision_doc = (
            ROOT / "docs/PHASE_3_FUTURE_COMPARISON_FAILURE_LOCALIZATION.md"
        ).read_text(encoding="utf-8")
        for statement in (
            "PHASE_3_OVERALL = PARTIAL",
            "PROMOTION = NO_PROMOTION",
            "RETRIEVAL_RANKING_OPTIMIZATION = STOP",
            "EXISTING_FIXED_RERANKER_FAMILY = WEAKENED",
            "NEXT_EXPERIMENT = NONE",
            "Cross-document / coverage-aware ranking",
            "Deep candidate retrieval",
        ):
            self.assertIn(statement, decision_doc)

        product_decisions = (ROOT / "docs/PRODUCT_DECISIONS.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("| PD-071 | ACCEPTED |", product_decisions)
        self.assertIn("| PD-070 | SUPERSEDED_BY_PD-071 |", product_decisions)

    def test_current_frozen_inputs_form_exact_three_case_identity(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        identity = self._build_test_identity(
            head=head,
            config_path=TOP20_CONFIG_PATH,
        )
        self.assertEqual(tuple(identity["cohort"]), COHORT)
        self.assertEqual(identity["excluded_cases"], [EXCLUDED_CASE])
        self.assertEqual(len(identity["cases"]), 3)
        self.assertEqual(identity["reranker"]["candidate_top_k"], 20)

    def test_fixed_candidate_limit_makes_two_cases_impossible(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        identity = self._build_test_identity(
            head=head,
            config_path=TOP20_CONFIG_PATH,
        )
        possible = {
            value["case_id"]: value[
                "bilateral_recovery_possible_with_fixed_candidate_top_k"
            ]
            for value in identity["cases"]
        }
        self.assertEqual(
            possible,
            {
                "local3.assisted.0033": False,
                "local3.assisted.0304": False,
                "local3.assisted.0383": True,
            },
        )

    def test_top50_identity_changes_only_exposure_and_binds_top20_parent(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        identity = self._build_test_identity(
            head=head,
            config_path=TOP50_CONFIG_PATH,
        )
        self.assertEqual(identity["reranker"]["candidate_top_k"], 50)
        self.assertEqual(identity["reranker"]["output_top_k"], 20)
        self.assertNotEqual(
            identity["reranker"]["config_sha256"],
            self._build_test_identity(
                head=head,
                config_path=TOP20_CONFIG_PATH,
            )["reranker"]["config_sha256"],
        )
        self.assertEqual(
            identity["parent_top20_screening"]["identity_sha256"],
            TOP20_SCREENING_IDENTITY_SHA256,
        )
        self.assertEqual(
            {
                value["case_id"]: value["effective_reranker_candidate_count"]
                for value in identity["cases"]
            },
            {
                "local3.assisted.0033": 50,
                "local3.assisted.0304": 50,
                "local3.assisted.0383": 40,
            },
        )
        self.assertTrue(
            all(
                value["bilateral_recovery_possible_with_fixed_candidate_top_k"]
                for value in identity["cases"]
            )
        )

    def test_existing_score_order_uses_original_rank_as_tie_break(self) -> None:
        self.assertEqual(_ordered_indices([0.2, 0.7, 0.7, -0.1]), [1, 2, 0, 3])

    def test_bilateral_metric_requires_relevant_top3_from_both_documents(self) -> None:
        targets = {
            "a": {"document_id": "doc-a", "relevance": 3},
            "b": {"document_id": "doc-b", "relevance": 2},
        }
        self.assertTrue(_bilateral_top3(["x", "a", "b"], targets))
        self.assertFalse(_bilateral_top3(["a", "x", "y"], targets))

    def test_frozen_decision_thresholds(self) -> None:
        self.assertEqual(_screening_decision(3), "SCREENING_STRONG_SUPPORT")
        self.assertEqual(_screening_decision(2), "SCREENING_PARTIAL_SUPPORT")
        self.assertEqual(_screening_decision(1), "SCREENING_WEAKENED")
        self.assertEqual(_screening_decision(0), "SCREENING_WEAKENED")

    def test_target_rank_output_preserves_unobserved_target(self) -> None:
        self.assertEqual(_sorted_optional_ranks([16, None, 10]), [10, 16, None])


if __name__ == "__main__":
    unittest.main()
