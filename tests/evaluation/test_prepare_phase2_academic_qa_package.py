from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from scripts.prepare_phase2_academic_qa_package import prepare_package


ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _case(case_id: str, document_id: str, page: int) -> dict:
    return {
        "case_id": case_id,
        "category": "ANSWERABLE",
        "question": f"Question for {case_id}?",
        "document_ids": [document_id],
        "expected": {
            "http_status": 200,
            "answer_status": "COMPLETED",
            "min_evidence_count": 1,
            "required_evidence": [
                {"document_id": document_id, "page_start": page, "page_end": page}
            ],
        },
    }


class PreparePhase2AcademicQaPackageTests(unittest.TestCase):
    def test_tracked_policy_freezes_qwen_nine_cases_and_unchanged_retrieval(self):
        policy = json.loads(
            (ROOT / "evaluation/generation/phase2-academic-qa-acceptance-v1.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(policy["selection"]["required_case_count"], 9)
        self.assertEqual(len(set(policy["selection"]["case_ids"])), 9)
        self.assertEqual(policy["generation"]["model"], "qwen3:14b")
        self.assertFalse(policy["generation"]["think"])
        self.assertFalse(policy["retrieval"]["parameters_changed"])

    def _inputs(self, root: Path) -> tuple[Path, Path, Path, dict[str, Path]]:
        pdfs = {"doc_a": root / "a.pdf", "doc_b": root / "b.pdf"}
        pdfs["doc_a"].write_bytes(b"pdf-a")
        pdfs["doc_b"].write_bytes(b"pdf-b")
        papers = root / "papers.json"
        _write_json(
            papers,
            {
                "papers": [
                    {
                        "document_id": document_id,
                        "file_name": path.name,
                        "sha256": sha256(path.read_bytes()).hexdigest(),
                    }
                    for document_id, path in pdfs.items()
                ]
            },
        )
        cases = root / "cases.jsonl"
        rows = [
            _case("case.a", "doc_a", 3),
            _case("case.b", "doc_b", 7),
        ]
        cases.write_text(
            "".join(json.dumps(value) + "\n" for value in rows),
            encoding="utf-8",
        )
        policy = root / "policy.json"
        _write_json(
            policy,
            {
                "schema_version": "phase2_academic_qa_acceptance_policy_v1",
                "package_id": "fixture-phase2-qa",
                "source_cases_sha256": sha256(cases.read_bytes()).hexdigest(),
                "source_papers_sha256": sha256(papers.read_bytes()).hexdigest(),
                "selection": {
                    "required_case_count": 2,
                    "required_cases_per_document": 1,
                    "case_ids": ["case.a", "case.b"],
                },
                "generation": {
                    "provider": "ollama",
                    "model": "qwen3:14b",
                    "digest": "a" * 64,
                    "prompt_version": "academic-evidence-answer-v1",
                    "think": False,
                },
                "retrieval": {"parameters_changed": False, "top_k": 3},
                "privacy": {
                    "tracked_questions": False,
                    "tracked_pdf_bytes": False,
                },
            },
        )
        return policy, cases, papers, pdfs

    def test_builds_deterministic_private_package_without_question_in_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy, cases, papers, pdfs = self._inputs(root)
            created_at = datetime(2026, 7, 22, tzinfo=timezone.utc)
            first = prepare_package(
                policy_path=policy,
                cases_path=cases,
                papers_path=papers,
                pdf_paths=pdfs,
                output_dir=root / "out-a",
                created_at=created_at,
            )
            second = prepare_package(
                policy_path=policy,
                cases_path=cases,
                papers_path=papers,
                pdf_paths=pdfs,
                output_dir=root / "out-b",
                created_at=created_at,
            )

            self.assertEqual(first["zip_sha256"], second["zip_sha256"])
            self.assertEqual(first["case_count"], 2)
            self.assertEqual(first["document_count"], 2)
            report_text = (root / "out-a" / "package-report.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("Question for", report_text)
            suite = json.loads(
                (root / "out-a" / "suites" / "doc_a.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(suite["cases"][0]["required_page_ranges"][0]["page_start"], 3)

    def test_rejects_pdf_identity_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy, cases, papers, pdfs = self._inputs(root)
            pdfs["doc_a"].write_bytes(b"drift")

            with self.assertRaisesRegex(ValueError, "PDF identity mismatch"):
                prepare_package(
                    policy_path=policy,
                    cases_path=cases,
                    papers_path=papers,
                    pdf_paths=pdfs,
                    output_dir=root / "out",
                    created_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
                )


if __name__ == "__main__":
    unittest.main()
