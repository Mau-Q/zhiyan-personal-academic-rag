#!/usr/bin/env python3
"""Build the private, deterministic input package for the Windows Reranker Gate."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from hashlib import sha256
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FILES = {
    "runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/manifest.json": (
        "b1a3d2aa7a40e38c28818b1b712ccdf14a05eeeaa87826545e0d102d2f400207"
    ),
    "runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/items-v1.jsonl": (
        "940e5b8c8d00d9f70626e65e34fdfce6bac6ec7ab681b8d2b08794976b94d5d4"
    ),
    "runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/annotations-v1.jsonl": (
        "9a6f66e2709fc2d7a91cb332de62ec01c30563e44df2efad3458c9ecede8cb68"
    ),
    "runtime/evaluation/formal-retrieval-v1/ai-audited-engineering-v1/rankings-v1/local_rrf.jsonl": (
        "777b41c3e2544badcb9ed6fb7208f4556f4a989286a2373ebad5a59028bbc7f5"
    ),
    "runtime/evaluation/mvp-175-remote-baseline-input-v1/chunks-v1.json": (
        "f7eb7e4a6c7820abde5523dca906df1d1a052e2e3b2174887781531295c7a282"
    ),
}
ZIP_TIMESTAMP = (2026, 7, 23, 0, 0, 0)


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def build_package(
    *,
    repository_root: Path,
    output_path: Path,
    expected_files: Mapping[str, str] = EXPECTED_FILES,
) -> dict[str, object]:
    members: dict[str, bytes] = {}
    for relative_path, expected_sha256 in sorted(expected_files.items()):
        source_path = repository_root / relative_path
        value = source_path.read_bytes()
        actual_sha256 = _sha256_bytes(value)
        if actual_sha256 != expected_sha256:
            raise ValueError(f"frozen Reranker input digest drifted: {relative_path}")
        members[relative_path] = value

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for relative_path, value in sorted(members.items()):
            info = zipfile.ZipInfo(relative_path, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    with zipfile.ZipFile(output_path, mode="r") as archive:
        if archive.namelist() != sorted(members):
            raise ValueError("frozen Reranker package member set drifted")
        for relative_path, expected_value in sorted(members.items()):
            if archive.read(relative_path) != expected_value:
                raise ValueError(f"frozen Reranker package CRC mismatch: {relative_path}")

    return {
        "schema_version": "fixed_reranker_input_package_report_v1",
        "package_path": str(output_path),
        "package_sha256": sha256(output_path.read_bytes()).hexdigest(),
        "member_count": len(members),
        "members": [
            {
                "path": relative_path,
                "sha256": expected_files[relative_path],
                "size_bytes": len(members[relative_path]),
            }
            for relative_path in sorted(members)
        ],
        "boundary": "PRIVATE_IGNORED_RUNTIME_HANDOFF_NOT_FOR_GIT",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "runtime/handoffs/fixed-reranker-input-v1.zip",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = build_package(repository_root=ROOT, output_path=args.output.resolve())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"fixed Reranker input package error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
