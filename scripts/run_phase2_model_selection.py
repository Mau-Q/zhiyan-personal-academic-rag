"""Compare the frozen Phase 2 generation candidate against the fallback model."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.rag.generation import (
    PROMPT_SHA256,
    PROMPT_VERSION,
    GenerationProvider,
    OllamaGenerationProvider,
)


REPORT_SCHEMA_VERSION = "phase2_model_selection_report_v1"
CASES_SCHEMA_VERSION = "phase2_model_selection_cases_v1"
CASES_PATH = Path("evaluation/generation/phase2-model-selection-v1.json")
CASES_SHA256 = "2ddec2697294ef98bacae7e01fd49a382235dad506b6a22b93b7b4d789ac176f"
DEFAULT_OUTPUT = Path(
    "runtime/phases/source-phase2-model-selection-qwen3-14b/report.json"
)
_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class FrozenModel:
    role: str
    model: str
    digest: str


BASELINE_MODEL = FrozenModel(
    role="fallback_baseline",
    model="llama3.2:latest",
    digest="a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72",
)
CANDIDATE_MODEL = FrozenModel(
    role="preferred_candidate",
    model="qwen3:14b",
    digest="bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8",
)


class ModelSelectionGateError(RuntimeError):
    """Stable, report-safe model-selection failure."""


ProviderFactory = Callable[..., GenerationProvider]


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_frozen_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelSelectionGateError("FROZEN_CASES_UNREADABLE") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != CASES_SCHEMA_VERSION:
        raise ModelSelectionGateError("FROZEN_CASES_SCHEMA_MISMATCH")
    if _canonical_sha256(payload) != CASES_SHA256:
        raise ModelSelectionGateError("FROZEN_CASES_DIGEST_MISMATCH")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 4:
        raise ModelSelectionGateError("FROZEN_CASES_COUNT_MISMATCH")
    return cases


def _validate_loopback_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ModelSelectionGateError("OLLAMA_URL_MUST_USE_LOOPBACK")
    return value.rstrip("/")


def _validate_output_path(path: Path) -> None:
    if (
        path.is_absolute()
        or not path.parts
        or path.parts[0] != "runtime"
        or ".." in path.parts
        or path.suffix != ".json"
    ):
        raise ModelSelectionGateError("OUTPUT_MUST_BE_RUNTIME_JSON")


def _term_groups_pass(answer: str, groups: object) -> bool:
    if not isinstance(groups, list):
        return False
    normalized = "".join(answer.casefold().split())
    return all(
        isinstance(group, list)
        and bool(group)
        and any(
            isinstance(term, str)
            and "".join(term.casefold().split()) in normalized
            for term in group
        )
        for group in groups
    )


def _forbidden_terms_absent(answer: str, terms: object) -> bool:
    if not isinstance(terms, list):
        return False
    normalized = "".join(answer.casefold().split())
    return all(
        isinstance(term, str)
        and "".join(term.casefold().split()) not in normalized
        for term in terms
    )


def _required_citations_pass(answer: str, required: object) -> tuple[bool, list[int]]:
    if not isinstance(required, list) or any(type(value) is not int for value in required):
        return False, []
    actual = sorted({int(value) for value in _CITATION_PATTERN.findall(answer)})
    return set(required).issubset(actual), actual


def _evaluate_model(
    model: FrozenModel,
    cases: Sequence[Mapping[str, Any]],
    *,
    base_url: str,
    provider_factory: ProviderFactory = OllamaGenerationProvider,
) -> dict[str, Any]:
    provider = provider_factory(
        model=model.model,
        expected_digest=model.digest,
        base_url=base_url,
    )
    configured_identity = provider.configured_identity()
    case_reports: list[dict[str, Any]] = []
    for case in cases:
        question = case.get("question")
        evidence = case.get("evidence")
        if not isinstance(question, str) or not isinstance(evidence, list):
            raise ModelSelectionGateError("FROZEN_CASE_STRUCTURE_INVALID")
        results = []
        durations_ms = []
        errors = []
        for _ in range(2):
            started = time.perf_counter()
            try:
                results.append(provider.generate(question, evidence))
            except Exception as exc:
                errors.append(type(exc).__name__)
            finally:
                durations_ms.append(round((time.perf_counter() - started) * 1000, 3))

        generation_complete = len(results) == 2 and not errors
        stable_replay = (
            generation_complete and results[0].answer == results[1].answer
        )
        identity_validated = generation_complete and all(
            result.identity == configured_identity for result in results
        )
        answer = results[0].answer if results else ""
        citations_pass, citation_ids = _required_citations_pass(
            answer, case.get("required_citation_ids")
        )
        semantic_checks_pass = _term_groups_pass(
            answer, case.get("required_any_term_groups")
        )
        forbidden_terms_absent = _forbidden_terms_absent(
            answer, case.get("forbidden_terms")
        )
        hard_gate_pass = all(
            (
                generation_complete,
                stable_replay,
                identity_validated,
                citations_pass,
                semantic_checks_pass,
                forbidden_terms_absent,
            )
        )
        case_reports.append(
            {
                "case_id": case.get("case_id"),
                "generation_complete": generation_complete,
                "stable_replay": stable_replay,
                "identity_validated": identity_validated,
                "required_citations_present": citations_pass,
                "citation_ids": citation_ids,
                "semantic_checks_pass": semantic_checks_pass,
                "forbidden_terms_absent": forbidden_terms_absent,
                "hard_gate_pass": hard_gate_pass,
                "answer_sha256": _text_sha256(answer) if answer else None,
                "attempt_duration_ms": durations_ms,
                "median_duration_ms": round(statistics.median(durations_ms), 3),
                "prompt_eval_count": (
                    [result.prompt_eval_count for result in results]
                    if generation_complete
                    else []
                ),
                "eval_count": (
                    [result.eval_count for result in results]
                    if generation_complete
                    else []
                ),
                "sanitized_errors": sorted(set(errors)),
            }
        )
    execution_complete = all(row["generation_complete"] for row in case_reports)
    hard_gate_pass = execution_complete and all(
        row["hard_gate_pass"] for row in case_reports
    )
    return {
        "model": asdict(model),
        "execution_complete": execution_complete,
        "hard_gate_pass": hard_gate_pass,
        "hard_gate_cases_passed": sum(
            bool(row["hard_gate_pass"]) for row in case_reports
        ),
        "hard_gate_cases_total": len(case_reports),
        "cases": case_reports,
    }


def run_selection(
    *,
    base_url: str,
    provider_factory: ProviderFactory = OllamaGenerationProvider,
    cases_path: Path = CASES_PATH,
) -> dict[str, Any]:
    cases = _load_frozen_cases(cases_path)
    baseline = _evaluate_model(
        BASELINE_MODEL,
        cases,
        base_url=base_url,
        provider_factory=provider_factory,
    )
    candidate = _evaluate_model(
        CANDIDATE_MODEL,
        cases,
        base_url=base_url,
        provider_factory=provider_factory,
    )
    execution_complete = bool(
        baseline["execution_complete"] and candidate["execution_complete"]
    )
    if not execution_complete:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "FAIL",
            "error_code": "MODEL_SELECTION_EXECUTION_INCOMPLETE",
            "cases_sha256": CASES_SHA256,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": PROMPT_SHA256,
            "retrieval_parameters_changed": False,
            "results": [baseline, candidate],
        }
    candidate_eligible = bool(candidate["hard_gate_pass"])
    decision = "PROMOTE_QWEN3_14B" if candidate_eligible else "KEEP_LLAMA3_2"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "PASS",
        "cases_sha256": CASES_SHA256,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": PROMPT_SHA256,
        "retrieval_parameters_changed": False,
        "selection_policy": (
            "PREFERRED_CANDIDATE_PROMOTES_ONLY_IF_ALL_FIXED_HARD_GATES_PASS"
        ),
        "performance_threshold_frozen": False,
        "performance_measurements_decide_selection": False,
        "decision": decision,
        "candidate_eligible": candidate_eligible,
        "fallback_model": BASELINE_MODEL.model,
        "results": [baseline, candidate],
    }


def _write_new(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        _validate_output_path(args.output)
        if args.output.exists():
            raise ModelSelectionGateError("OUTPUT_ALREADY_EXISTS")
        report = run_selection(base_url=_validate_loopback_url(args.ollama_url))
        _write_new(args.output, report)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["status"] == "PASS" else 1
    except Exception as exc:
        error_code = (
            str(exc)
            if type(exc) is ModelSelectionGateError
            else type(exc).__name__
        )
        failure = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "FAIL",
            "error_code": error_code,
        }
        if not args.output.exists():
            try:
                _write_new(args.output, failure)
            except Exception:
                pass
        print(json.dumps(failure), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
