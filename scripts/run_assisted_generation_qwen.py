#!/usr/bin/env python3
"""Generate assisted retrieval-evaluation candidates with DashScope Qwen."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import certifi


REQUIRED_OUTPUT_FIELDS = {
    "slot_id",
    "question",
    "conversation_history",
    "question_types",
    "answerability",
    "expected_route",
    "expected_document_ids",
    "chunk_judgments",
    "reference_claims",
    "acceptable_answer_points",
    "must_not_claim",
    "expected_citations",
    "freshness_cutoff",
    "generation_notes",
}


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    model: str
    timeout: float
    workers: int
    retries: int


def load_env_file(path: Path) -> dict[str, str]:
    """Read a simple dotenv file without executing shell content."""
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"invalid dotenv line {line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key.replace("_", "a").isalnum() or key[0].isdigit():
            raise ValueError(f"invalid dotenv key on line {line_number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_requests(batch_dir: Path) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for path in sorted(batch_dir.glob("batch-*.jsonl")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
            if payload.get("schema_version") != "assisted_question_generation_request_v1":
                raise ValueError(f"unsupported request at {path}:{line_number}")
            requests.append(payload)
    if len(requests) != 500:
        raise ValueError(f"expected exactly 500 requests, found {len(requests)}")
    slot_ids = [request["slot"]["slot_id"] for request in requests]
    if len(slot_ids) != len(set(slot_ids)):
        raise ValueError("request slot ids must be unique")
    return requests


def build_api_payload(request: dict[str, Any], model: str) -> dict[str, Any]:
    user_payload = {
        "slot": request["slot"],
        "evidence_chunks": request["evidence_chunks"],
    }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": request["instructions"]},
            {
                "role": "user",
                "content": json.dumps(
                    user_payload, ensure_ascii=False, separators=(",", ":")
                ),
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "enable_thinking": False,
        "max_tokens": 4096,
    }


def validate_candidate(candidate: Any, expected_slot_id: str) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ValueError("model content must be a JSON object")
    missing = sorted(REQUIRED_OUTPUT_FIELDS - set(candidate))
    if missing:
        raise ValueError(f"model content is missing fields: {','.join(missing)}")
    if candidate["slot_id"] != expected_slot_id:
        raise ValueError("model content returned the wrong slot_id")
    if not isinstance(candidate["question"], str) or not candidate["question"].strip():
        raise ValueError("model content returned an empty question")
    for field in (
        "conversation_history",
        "question_types",
        "expected_document_ids",
        "chunk_judgments",
        "reference_claims",
        "acceptable_answer_points",
        "must_not_claim",
        "expected_citations",
    ):
        if not isinstance(candidate[field], list):
            raise ValueError(f"model content field {field} must be a list")
    return candidate


def parse_api_response(
    payload: dict[str, Any], expected_slot_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        choice = payload["choices"][0]
        message = choice["message"]
        content = json.loads(message["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid DashScope response shape or JSON content") from exc
    reasoning = message.get("reasoning_content")
    if reasoning not in (None, ""):
        raise ValueError("thinking content was returned despite enable_thinking=false")
    candidate = validate_candidate(content, expected_slot_id)
    metadata = {
        "response_id": payload.get("id"),
        "model": payload.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "usage": payload.get("usage", {}),
        "reasoning_present": False,
    }
    return candidate, metadata


def build_https_opener() -> urllib.request.OpenerDirector:
    """Use certifi explicitly while keeping certificate verification enabled."""
    context = ssl.create_default_context(cafile=certifi.where())
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
    )


def call_one(
    request_payload: dict[str, Any], settings: Settings
) -> tuple[dict[str, Any], dict[str, Any]]:
    slot_id = request_payload["slot"]["slot_id"]
    body = json.dumps(
        build_api_payload(request_payload, settings.model),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    endpoint = settings.base_url.rstrip("/") + "/chat/completions"
    last_error: Exception | None = None
    opener = build_https_opener()
    for attempt in range(settings.retries + 1):
        api_request = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with opener.open(api_request, timeout=settings.timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            return parse_api_response(response_payload, slot_id)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            last_error = RuntimeError(f"HTTP {exc.code}: {detail}")
            if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                break
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            last_error = exc
        if attempt < settings.retries:
            time.sleep(min(2**attempt + random.random(), 8))
    raise RuntimeError(f"{slot_id}: {last_error}")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_generation(
    requests: list[dict[str, Any]], output_dir: Path, settings: Settings
) -> dict[str, Any]:
    result_dir = output_dir / "items"
    result_dir.mkdir(parents=True, exist_ok=True)
    completed: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    for request_payload in requests:
        slot_id = request_payload["slot"]["slot_id"]
        result_path = result_dir / f"{slot_id}.json"
        if result_path.exists():
            saved = json.loads(result_path.read_text(encoding="utf-8"))
            validate_candidate(saved["candidate"], slot_id)
            completed[slot_id] = saved
        else:
            pending.append(request_payload)

    failures: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.workers) as pool:
        future_map = {
            pool.submit(call_one, request_payload, settings): request_payload
            for request_payload in pending
        }
        for future in concurrent.futures.as_completed(future_map):
            request_payload = future_map[future]
            slot_id = request_payload["slot"]["slot_id"]
            try:
                candidate, metadata = future.result()
                saved = {
                    "schema_version": "assisted_question_generation_result_v1",
                    "slot": request_payload["slot"],
                    "candidate": candidate,
                    "execution": {
                        **metadata,
                        "requested_model": settings.model,
                        "prompt_version": request_payload["prompt_version"],
                        "temperature": 0,
                        "enable_thinking": False,
                    },
                }
                _atomic_json(result_dir / f"{slot_id}.json", saved)
                completed[slot_id] = saved
                print(f"completed {len(completed)}/500 {slot_id}", flush=True)
            except Exception as exc:  # noqa: BLE001 - recorded per item for resume
                failures.append({"slot_id": slot_id, "error": str(exc)})
                print(f"failed {slot_id}: {exc}", flush=True)

    ordered = [completed[key] for key in sorted(completed)]
    (output_dir / "results.jsonl").write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
            for item in ordered
        ),
        encoding="utf-8",
    )
    (output_dir / "failures.jsonl").write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
            for item in failures
        ),
        encoding="utf-8",
    )
    token_totals: dict[str, int] = {}
    for item in ordered:
        for key, value in item["execution"].get("usage", {}).items():
            if isinstance(value, int):
                token_totals[key] = token_totals.get(key, 0) + value
    report = {
        "schema_version": "assisted_question_generation_run_report_v1",
        "requested_model": settings.model,
        "enable_thinking": False,
        "target_count": 500,
        "completed_count": len(completed),
        "failed_count": len(failures),
        "workers": settings.workers,
        "token_totals": token_totals,
        "status": "COMPLETE" if len(completed) == 500 else "INCOMPLETE_RETRY_REQUIRED",
    }
    _atomic_json(output_dir / "run-report.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="qwen3.7-plus")
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--retries", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        env = {**os.environ, **load_env_file(args.env_file)}
        base_url = env["CHUNK_QA_MODEL_BASE_URL"]
        api_key = env["CHUNK_QA_MODEL_API_KEY"]
        timeout = float(env.get("CHUNK_QA_MODEL_TIMEOUT", "120"))
        if args.workers < 1 or args.workers > 32:
            raise ValueError("workers must be between 1 and 32")
        if args.retries < 0 or args.retries > 10:
            raise ValueError("retries must be between 0 and 10")
        settings = Settings(
            base_url=base_url,
            api_key=api_key,
            model=args.model,
            timeout=timeout,
            workers=args.workers,
            retries=args.retries,
        )
        requests = load_requests(args.batch_dir)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        report = run_generation(requests, args.output_dir, settings)
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        print(f"Qwen assisted generation error: {exc}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
