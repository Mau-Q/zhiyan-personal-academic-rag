#!/usr/bin/env python3
"""Freeze and run the existing fixed reranker on frozen Phase 3 RRF ladders."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if not sys.path or Path(sys.path[0]).resolve() != ROOT:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.reranker import (  # noqa: E402
    build_passage,
    directory_sha256,
    load_config,
    load_document_titles,
)


IDENTITY_SCHEMA = "phase3_fixed_reranker_screening_identity_v1"
REPORT_SCHEMA = "phase3_fixed_reranker_screening_report_v1"
DIAGNOSTIC_SOURCE_COMMIT = "4a908f1fa8a4d87cdb351c0bb3e5f5df1aab63fc"
DIAGNOSTIC_REPORT_SHA256 = (
    "f110daba4bc5d26c952b682502f812a156f6e3fde8ecd04b716db73b99e45186"
)
DIAGNOSTIC_ADJUDICATION_SHA256 = (
    "4fba0e27d44abfd009e496a0430b5da2eabfdc009a57f0c5b8cb8d7e297fed8f"
)
INPUT_MANIFEST_SHA256 = (
    "05c36a393a51a8aa705e17d1ac3895df074b9273f8af6bfad06c9904c458c63f"
)
CHUNK_SNAPSHOT_SHA256 = (
    "f7eb7e4a6c7820abde5523dca906df1d1a052e2e3b2174887781531295c7a282"
)
DEV_REVIEW_SHA256 = (
    "13b7ddfb0185ba03f251664366d5ab28a0cae64adda9ef9a57da563be0ae2c6e"
)
MODEL_SNAPSHOT_SHA256 = (
    "f9dd638f0b27b57667d99b01f83ca4dbb3c82983911a1ef31a4601c7b890eaec"
)
COHORT = (
    "local3.assisted.0033",
    "local3.assisted.0304",
    "local3.assisted.0383",
)
EXCLUDED_CASE = "local3.assisted.0387"
FULL_DIAGNOSTIC_COHORT = (*COHORT, EXCLUDED_CASE)
DOCUMENT_SOURCE_SHA256 = {
    "doc_arxiv_2601_03260": (
        "d509e0891cedd235251940fa57880bd31721e08a22379d922cddd534f62dce70"
    ),
    "doc_arxiv_2602_11409": (
        "3e7e4628ffadc9183e85341b3a88050c3b58a06dec02926c8f2028b55879d6ea"
    ),
    "doc_arxiv_2603_04915": (
        "ff3b39d94690de98cff09998c669b20333861d43b797ea000af812bc7f524dcf"
    ),
}
EXPECTED_MODEL = {
    "provider": "sentence_transformers_cross_encoder",
    "model_id": "BAAI/bge-reranker-v2-m3",
    "revision": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
    "max_length": 512,
    "batch_size": 16,
    "device": "mps",
    "trust_remote_code": False,
    "input_template": "question_title_section_text_v1",
}


JsonObject = dict[str, Any]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _jsonl(path: Path) -> list[JsonObject]:
    values = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not all(isinstance(value, dict) for value in values):
        raise ValueError(f"non-object JSONL row in {path}")
    return values


def _head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _require_sha(path: Path, expected: str, label: str) -> None:
    if _sha256(path) != expected:
        raise ValueError(f"{label} identity drifted")


def _chunk_text_sha256(chunk: Mapping[str, Any]) -> str:
    text = chunk.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError("frozen candidate text is unavailable")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _target_labels(row: Mapping[str, Any]) -> dict[str, JsonObject]:
    labels = row.get("final_labels")
    judgments = labels.get("chunk_judgments") if isinstance(labels, dict) else None
    if not isinstance(judgments, list):
        raise ValueError("frozen case judgments are unavailable")
    result = {
        str(value["chunk_id"]): {
            "document_id": str(value["document_id"]),
            "relevance": int(value["relevance"]),
        }
        for value in judgments
        if isinstance(value, dict) and int(value.get("relevance", 0)) >= 2
    }
    if len({value["document_id"] for value in result.values()}) != 2:
        raise ValueError("frozen bilateral target identity is invalid")
    return result


def _candidate_identity(
    candidate: Mapping[str, Any],
    chunks_by_id: Mapping[str, Mapping[str, Any]],
) -> JsonObject:
    chunk_id = str(candidate.get("source_chunk_id", ""))
    chunk = chunks_by_id.get(chunk_id)
    if chunk is None:
        raise ValueError(f"candidate source Chunk is missing: {chunk_id}")
    compared = {
        "source_document_id": "document_id",
        "page_start": "page_start",
        "page_end": "page_end",
        "section_path": "section_path",
    }
    for candidate_field, chunk_field in compared.items():
        if candidate.get(candidate_field) != chunk.get(chunk_field):
            raise ValueError(f"candidate retained identity drifted: {chunk_id}")
    document_id = str(chunk["document_id"])
    source_sha256 = DOCUMENT_SOURCE_SHA256.get(document_id)
    if source_sha256 is None:
        raise ValueError("candidate document source fingerprint is unavailable")
    expected_version_id = f"version_{source_sha256[:24]}"
    if chunk.get("version_id") != expected_version_id:
        raise ValueError("candidate retained document version drifted")
    return {
        "original_rrf_rank": int(candidate["rank"]),
        "source_chunk_id": chunk_id,
        "runtime_chunk_id": str(candidate["runtime_chunk_id"]),
        "source_document_id": document_id,
        "source_document_version_id": expected_version_id,
        "source_fingerprint_sha256": source_sha256,
        "page_start": chunk["page_start"],
        "page_end": chunk["page_end"],
        "section_path": chunk["section_path"],
        "text_sha256": _chunk_text_sha256(chunk),
    }


def _validate_case(
    case: Mapping[str, Any],
    row: Mapping[str, Any],
    chunks_by_id: Mapping[str, Mapping[str, Any]],
    *,
    candidate_top_k: int,
) -> JsonObject:
    case_id = str(case.get("case_id", ""))
    if row.get("question_id") != case_id or row.get("split") != "dev":
        raise ValueError("screening case is not identity-bound dev")
    question = row.get("question")
    if not isinstance(question, str) or not question:
        raise ValueError("screening question text is unavailable")
    target_labels = _target_labels(row)
    if set(case.get("required_source_chunk_ids", ())) != set(target_labels):
        raise ValueError("report and frozen target Chunk identities differ")
    required_documents = sorted(
        {value["document_id"] for value in target_labels.values()}
    )
    if sorted(case.get("required_source_documents", ())) != required_documents:
        raise ValueError("report and frozen bilateral documents differ")

    ladder = case.get("ladder")
    rrf_ladder = ladder.get("rrf_ladder") if isinstance(ladder, dict) else None
    final_top3 = ladder.get("final_top3") if isinstance(ladder, dict) else None
    if not isinstance(rrf_ladder, list) or len(rrf_ladder) < candidate_top_k:
        raise ValueError("frozen RRF ladder is incomplete")
    if not isinstance(final_top3, list) or len(final_top3) != 3:
        raise ValueError("frozen RRF Top-3 is incomplete")
    if [value.get("rank") for value in rrf_ladder] != list(
        range(1, len(rrf_ladder) + 1)
    ):
        raise ValueError("frozen RRF ranks are not contiguous")
    source_ids = [str(value.get("source_chunk_id", "")) for value in rrf_ladder]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("frozen RRF ladder contains duplicate candidates")
    if [value.get("source_chunk_id") for value in final_top3] != source_ids[:3]:
        raise ValueError("frozen Top-3 is not the RRF prefix")

    identities = [
        _candidate_identity(candidate, chunks_by_id) for candidate in rrf_ladder
    ]
    for candidate in rrf_ladder:
        expected_relevance = target_labels.get(
            str(candidate["source_chunk_id"]), {"relevance": 0}
        )["relevance"]
        if candidate.get("target_relevance") != expected_relevance:
            raise ValueError("frozen target relevance drifted")

    effective_ids = set(source_ids[:candidate_top_k])
    target_ranks = {
        chunk_id: next(
            (
                int(candidate["rank"])
                for candidate in rrf_ladder
                if candidate["source_chunk_id"] == chunk_id
            ),
            None,
        )
        for chunk_id in target_labels
    }
    effective_target_documents = sorted(
        {
            target["document_id"]
            for chunk_id, target in target_labels.items()
            if chunk_id in effective_ids
        }
    )
    return {
        "case_id": case_id,
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "required_source_documents": required_documents,
        "target_rrf_ranks": target_ranks,
        "full_rrf_candidate_count": len(rrf_ladder),
        "full_rrf_candidate_set_sha256": _canonical_sha256(identities),
        "effective_reranker_candidate_count": candidate_top_k,
        "effective_reranker_candidate_set_sha256": _canonical_sha256(
            identities[:candidate_top_k]
        ),
        "effective_target_documents": effective_target_documents,
        "bilateral_recovery_possible_with_fixed_candidate_top_k": (
            set(effective_target_documents) == set(required_documents)
        ),
    }


def build_identity(*, expected_screening_source_commit: str) -> JsonObject:
    if _head_commit() != expected_screening_source_commit:
        raise ValueError("screening source commit identity drifted")
    report_path = ROOT / "runtime/phase3-candidate-ladder-local-intake/report.json"
    chunks_path = (
        ROOT / "runtime/evaluation/mvp-175-remote-baseline-input-v1/chunks-v1.json"
    )
    dev_review_path = (
        ROOT
        / "runtime/handoffs/member-b-phase2-4-dev-review-input-v1/"
        "dev-claim-evidence-review-input-v1.jsonl"
    )
    config_path = ROOT / "evaluation/reranker/fixed-cross-encoder-v1.json"
    title_catalog_path = ROOT / "fixtures/sample-corpus-v1.json"
    _require_sha(report_path, DIAGNOSTIC_REPORT_SHA256, "candidate-ladder report")
    _require_sha(chunks_path, CHUNK_SNAPSHOT_SHA256, "retained Chunk snapshot")
    _require_sha(dev_review_path, DEV_REVIEW_SHA256, "dev review input")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    identity = report.get("identity")
    if (
        report.get("status") != "PASS"
        or report.get("run_id") != "phase3_candidate_ladder_20260809_01"
        or not isinstance(identity, dict)
        or identity.get("source_commit") != DIAGNOSTIC_SOURCE_COMMIT
        or identity.get("input_manifest_sha256") != INPUT_MANIFEST_SHA256
        or tuple(identity.get("cohort", ())) != FULL_DIAGNOSTIC_COHORT
    ):
        raise ValueError("candidate-ladder report formal identity drifted")

    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    if not isinstance(chunks, list) or len(chunks) != 316:
        raise ValueError("retained Chunk snapshot shape drifted")
    chunks_by_id = {str(chunk.get("chunk_id", "")): chunk for chunk in chunks}
    if len(chunks_by_id) != len(chunks):
        raise ValueError("retained Chunk snapshot identity is duplicated")

    dev_rows = _jsonl(dev_review_path)
    if len(dev_rows) != 105 or {row.get("split") for row in dev_rows} != {"dev"}:
        raise ValueError("dev-only split boundary drifted")
    rows_by_id = {
        str(row["question_id"]): row
        for row in dev_rows
        if row.get("question_id") in COHORT
    }
    if set(rows_by_id) != set(COHORT):
        raise ValueError("screening cohort is incomplete")

    config = load_config(config_path)
    if (
        config.candidate_top_k != 20
        or config.output_top_k != 20
        or dict(config.model) != EXPECTED_MODEL
    ):
        raise ValueError("existing fixed reranker configuration drifted")
    titles = load_document_titles(title_catalog_path)
    if not set(DOCUMENT_SOURCE_SHA256).issubset(titles):
        raise ValueError("fixed reranker document titles are incomplete")

    snapshot_path = (
        ROOT
        / "runtime/models/huggingface/models--BAAI--bge-reranker-v2-m3/snapshots"
        / EXPECTED_MODEL["revision"]
    )
    if directory_sha256(snapshot_path) != MODEL_SNAPSHOT_SHA256:
        raise ValueError("existing fixed reranker model snapshot drifted")

    cases = report.get("cases")
    if not isinstance(cases, list):
        raise ValueError("candidate-ladder cases are unavailable")
    selected_cases = [case for case in cases if case.get("case_id") in COHORT]
    if tuple(case.get("case_id") for case in selected_cases) != COHORT:
        raise ValueError("screening cohort order drifted")
    case_identities = [
        _validate_case(
            case,
            rows_by_id[str(case["case_id"])],
            chunks_by_id,
            candidate_top_k=config.candidate_top_k,
        )
        for case in selected_cases
    ]

    tokenizer_files = {}
    for name in (
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
    ):
        tokenizer_files[name] = _sha256(snapshot_path / name)
    frozen = {
        "schema_version": IDENTITY_SCHEMA,
        "screening_source_commit": expected_screening_source_commit,
        "diagnostic_source_commit": DIAGNOSTIC_SOURCE_COMMIT,
        "candidate_ladder_report_sha256": DIAGNOSTIC_REPORT_SHA256,
        "candidate_ladder_adjudication_sha256": DIAGNOSTIC_ADJUDICATION_SHA256,
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "chunk_snapshot_sha256": CHUNK_SNAPSHOT_SHA256,
        "dev_review_sha256": DEV_REVIEW_SHA256,
        "title_catalog_sha256": _sha256(title_catalog_path),
        "cohort": list(COHORT),
        "excluded_cases": [EXCLUDED_CASE],
        "candidate_selection_contract": (
            "FULL_FROZEN_RRF_LADDER_VERIFIED_EXISTING_FIXED_RERANKER_CONSUMES_PREFIX_20"
        ),
        "reranker": {
            "config_sha256": _sha256(config_path),
            "model": dict(config.model),
            "snapshot_sha256": MODEL_SNAPSHOT_SHA256,
            "tokenizer_and_config_sha256": tokenizer_files,
            "scoring_semantics": (
                "DESCENDING_CROSS_ENCODER_LOGIT_TIE_BREAK_ORIGINAL_RRF_RANK"
            ),
            "candidate_top_k": config.candidate_top_k,
            "output_top_k": config.output_top_k,
        },
        "document_source_sha256": DOCUMENT_SOURCE_SHA256,
        "cases": case_identities,
        "decision_thresholds": {
            "SCREENING_STRONG_SUPPORT": "3/3",
            "SCREENING_PARTIAL_SUPPORT": "2/3",
            "SCREENING_WEAKENED": "0-1/3",
        },
        "boundaries": {
            "retrieval_calls": 0,
            "embedding_calls": 0,
            "candidate_membership_change": False,
            "test_or_acceptance_read": False,
            "performance_gate": False,
        },
    }
    frozen["identity_sha256"] = _canonical_sha256(frozen)
    return frozen


def _ordered_indices(scores: Sequence[float]) -> list[int]:
    if any(not math.isfinite(float(score)) for score in scores):
        raise ValueError("fixed reranker returned a non-finite score")
    return sorted(range(len(scores)), key=lambda index: (-float(scores[index]), index))


def _bilateral_top3(
    ordered_chunk_ids: Sequence[str], target_labels: Mapping[str, Mapping[str, Any]]
) -> bool:
    target_documents = {
        target_labels[chunk_id]["document_id"]
        for chunk_id in ordered_chunk_ids[:3]
        if chunk_id in target_labels
        and int(target_labels[chunk_id]["relevance"]) >= 2
    }
    required_documents = {value["document_id"] for value in target_labels.values()}
    return target_documents == required_documents


def _screening_decision(recovered: int) -> str:
    if recovered == 3:
        return "SCREENING_STRONG_SUPPORT"
    if recovered == 2:
        return "SCREENING_PARTIAL_SUPPORT"
    if recovered in (0, 1):
        return "SCREENING_WEAKENED"
    raise ValueError("recovered case count is invalid")


def run_screening(*, frozen_identity: Mapping[str, Any]) -> JsonObject:
    expected_commit = str(frozen_identity.get("screening_source_commit", ""))
    recomputed = build_identity(expected_screening_source_commit=expected_commit)
    if _canonical_bytes(recomputed) != _canonical_bytes(frozen_identity):
        raise ValueError("frozen screening identity changed before inference")

    report = json.loads(
        (ROOT / "runtime/phase3-candidate-ladder-local-intake/report.json").read_text(
            encoding="utf-8"
        )
    )
    chunks = json.loads(
        (
            ROOT
            / "runtime/evaluation/mvp-175-remote-baseline-input-v1/chunks-v1.json"
        ).read_text(encoding="utf-8")
    )
    rows = _jsonl(
        ROOT
        / "runtime/handoffs/member-b-phase2-4-dev-review-input-v1/"
        "dev-claim-evidence-review-input-v1.jsonl"
    )
    chunks_by_id = {str(chunk["chunk_id"]): chunk for chunk in chunks}
    rows_by_id = {
        str(row["question_id"]): row for row in rows if row.get("question_id") in COHORT
    }
    cases_by_id = {str(case["case_id"]): case for case in report["cases"]}
    titles = load_document_titles(ROOT / "fixtures/sample-corpus-v1.json")
    config = load_config(ROOT / "evaluation/reranker/fixed-cross-encoder-v1.json")
    snapshot_path = (
        ROOT
        / "runtime/models/huggingface/models--BAAI--bge-reranker-v2-m3/snapshots"
        / str(config.model["revision"])
    )

    from sentence_transformers import CrossEncoder

    encoder = CrossEncoder(
        str(snapshot_path),
        device=str(config.model["device"]),
        max_length=int(config.model["max_length"]),
        trust_remote_code=False,
    )
    case_inputs: list[tuple[str, list[JsonObject], list[tuple[str, str]]]] = []
    for case_id in COHORT:
        case = cases_by_id[case_id]
        candidates = [dict(value) for value in case["ladder"]["rrf_ladder"][:20]]
        question = str(rows_by_id[case_id]["question"])
        pairs = [
            (
                question,
                build_passage(chunks_by_id[str(candidate["source_chunk_id"])], titles),
            )
            for candidate in candidates
        ]
        case_inputs.append((case_id, candidates, pairs))

    first_scores: dict[str, list[float]] = {}
    second_scores: dict[str, list[float]] = {}
    token_lengths: dict[str, list[int]] = {}
    for case_id, _candidates, pairs in case_inputs:
        first, second = zip(*pairs, strict=True)
        encoded = encoder.tokenizer(
            list(first),
            list(second),
            add_special_tokens=True,
            truncation=False,
            padding=False,
        )
        token_lengths[case_id] = [len(value) for value in encoded["input_ids"]]
        for target in (first_scores, second_scores):
            values = encoder.predict(
                pairs,
                batch_size=int(config.model["batch_size"]),
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            target[case_id] = [float(value) for value in values.reshape(-1).tolist()]

    case_results = []
    recovered = 0
    for case_id, candidates, _pairs in case_inputs:
        scores = first_scores[case_id]
        repeat_scores = second_scores[case_id]
        if len(scores) != 20 or len(repeat_scores) != 20:
            raise ValueError("fixed reranker score count drifted")
        first_order = _ordered_indices(scores)
        second_order = _ordered_indices(repeat_scores)
        if first_order != second_order:
            raise ValueError("fixed reranker total order is not deterministic")
        score_delta = max(
            abs(first - second)
            for first, second in zip(scores, repeat_scores, strict=True)
        )
        if score_delta > 1e-6:
            raise ValueError("fixed reranker repeated scores drifted")

        row = rows_by_id[case_id]
        target_labels = _target_labels(row)
        original_full = cases_by_id[case_id]["ladder"]["rrf_ladder"]
        original_ids = [str(value["source_chunk_id"]) for value in original_full]
        reranked_ids = [str(candidates[index]["source_chunk_id"]) for index in first_order]
        original_bilateral = _bilateral_top3(original_ids, target_labels)
        reranked_bilateral = _bilateral_top3(reranked_ids, target_labels)
        recovered += int(reranked_bilateral)

        reranked_rank_by_id = {
            str(candidates[index]["source_chunk_id"]): rank
            for rank, index in enumerate(first_order, 1)
        }
        score_by_id = {
            str(candidate["source_chunk_id"]): float(score)
            for candidate, score in zip(candidates, scores, strict=True)
        }
        target_evidence = []
        for chunk_id, target in target_labels.items():
            original_rank = next(
                (
                    int(candidate["rank"])
                    for candidate in original_full
                    if candidate["source_chunk_id"] == chunk_id
                ),
                None,
            )
            target_evidence.append(
                {
                    "source_chunk_id": chunk_id,
                    "target_side_identity": target["document_id"],
                    "relevance": target["relevance"],
                    "original_rrf_rank": original_rank,
                    "reranker_score": score_by_id.get(chunk_id),
                    "reranked_rank": reranked_rank_by_id.get(chunk_id),
                    "original_top3_membership": (
                        original_rank is not None and original_rank <= 3
                    ),
                    "reranked_top3_membership": (
                        reranked_rank_by_id.get(chunk_id) is not None
                        and reranked_rank_by_id[chunk_id] <= 3
                    ),
                    "eligible_under_fixed_candidate_top_k_20": chunk_id in score_by_id,
                }
            )
        ranking = [
            {
                "source_chunk_id": str(candidates[index]["source_chunk_id"]),
                "source_document_id": str(candidates[index]["source_document_id"]),
                "original_rrf_rank": int(candidates[index]["rank"]),
                "reranker_score": float(scores[index]),
                "reranked_rank": rank,
                "target_side_identity": (
                    target_labels.get(str(candidates[index]["source_chunk_id"]), {}).get(
                        "document_id"
                    )
                ),
                "original_top3_membership": int(candidates[index]["rank"]) <= 3,
                "reranked_top3_membership": rank <= 3,
            }
            for rank, index in enumerate(first_order, 1)
        ]
        case_results.append(
            {
                "case_id": case_id,
                "original_target_ranks": sorted(
                    value["original_rrf_rank"] for value in target_evidence
                ),
                "original_bilateral_top3": original_bilateral,
                "reranked_target_ranks": sorted(
                    value["reranked_rank"]
                    for value in target_evidence
                    if value["reranked_rank"] is not None
                ),
                "reranked_bilateral_top3": reranked_bilateral,
                "target_evidence": target_evidence,
                "reranked_top3": ranking[:3],
                "complete_reranked_order": ranking,
                "determinism": {
                    "repeated_total_order_identical": True,
                    "maximum_absolute_score_delta": score_delta,
                },
                "tokenization": {
                    "maximum_pair_tokens_before_truncation": max(token_lengths[case_id]),
                    "pairs_over_max_length": sum(
                        value > int(config.model["max_length"])
                        for value in token_lengths[case_id]
                    ),
                },
            }
        )

    decision = _screening_decision(recovered)
    return {
        "schema_version": REPORT_SCHEMA,
        "status": "PASS",
        "experiment_decision": decision,
        "hypothesis_effect": {
            "SCREENING_STRONG_SUPPORT": "SUPPORTED",
            "SCREENING_PARTIAL_SUPPORT": "PARTIALLY_SUPPORTED",
            "SCREENING_WEAKENED": "WEAKENED",
        }[decision],
        "identity_sha256": frozen_identity["identity_sha256"],
        "screening_source_commit": expected_commit,
        "cases": case_results,
        "aggregate": {
            "recovered_cases": recovered,
            "case_count": 3,
            "decision_threshold": (
                "3/3 STRONG_SUPPORT; 2/3 PARTIAL_SUPPORT; 0-1/3 WEAKENED"
            ),
            "screening_decision": decision,
        },
        "boundaries": {
            "new_retrieval_calls": 0,
            "new_embedding_calls": 0,
            "candidate_membership_changed": False,
            "excluded_case_included": False,
            "test_or_acceptance_read": False,
            "performance_gate_run": False,
            "formal_adoption": False,
            "next_algorithm_selected": False,
        },
        "strategy_handoff": "NO_AUTOMATIC_NEXT_EXPERIMENT",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--expected-screening-source-commit", required=True)
    freeze.add_argument("--output", type=Path, required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--identity", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "freeze":
            value = build_identity(
                expected_screening_source_commit=args.expected_screening_source_commit
            )
        else:
            frozen_identity = json.loads(args.identity.read_text(encoding="utf-8"))
            value = run_screening(frozen_identity=frozen_identity)
        _write_json(args.output, value)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"phase3 fixed reranker screening refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
