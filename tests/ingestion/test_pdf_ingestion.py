from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.api.app import create_app
from backend.ingestion.parser import PypdfTextParser
from backend.ingestion.service import PdfIngestionError, ingest_pdf_bytes
from tests.ingestion.pdf_fixture import synthetic_text_pdf


ROOT = Path(__file__).resolve().parents[2]
PAGE_ONE = """1. Introduction
This paper explains a deterministic retrieval pipeline with authorization filters.
The first page establishes exact source lineage and stable document identity."""
PAGE_TWO = """2. Method
The method combines lexical candidates before reranking and preserves PDF page numbers.
The second page provides enough evidence for a grounded answer."""


def ingest(pdf_bytes: bytes, **overrides):
    arguments = {
        "document_id": "doc_local_test_001",
        "tenant_id": "tenant_fixture",
        "visibility": "private",
        "library_scope_ids": ["lib_fixture"],
        "strategy": "fixed_boundary_v1",
    }
    arguments.update(overrides)
    return ingest_pdf_bytes(pdf_bytes, **arguments)


class PdfIngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf_bytes = synthetic_text_pdf([PAGE_ONE, PAGE_TWO])
        schema = json.loads(
            (ROOT / "contracts/schemas/chunk-record-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        cls.chunk_validator = Draft202012Validator(schema)

    def test_fixed_boundary_output_matches_contract_and_cross_page_range(self):
        result = ingest(self.pdf_bytes)

        self.assertEqual(result.parse_status, "PASS")
        self.assertEqual(len(result.chunks), 1)
        chunk = result.chunks[0]
        self.chunk_validator.validate(chunk.model_dump(mode="json"))
        self.assertEqual((chunk.page_start, chunk.page_end), (1, 2))
        self.assertEqual(chunk.embedding_version, "not_embedded_v1")
        self.assertEqual(chunk.parse_version, "pypdf_text_v1")
        self.assertIsNone(chunk.previous_chunk_id)
        self.assertIsNone(chunk.next_chunk_id)

    def test_section_parent_child_is_deterministic_and_neighbors_are_reciprocal(self):
        long_pages = [
            "1. Introduction\n" + "First auditable paragraph. " * 70,
            "2. Method\n" + "Second deterministic paragraph. " * 70,
        ]
        pdf_bytes = synthetic_text_pdf(long_pages)

        first = ingest(pdf_bytes, strategy="section_parent_child_v1")
        second = ingest(pdf_bytes, strategy="section_parent_child_v1")

        self.assertEqual(first.model_dump(mode="json"), second.model_dump(mode="json"))
        self.assertGreaterEqual(len(first.chunks), 2)
        by_id = {chunk.chunk_id: chunk for chunk in first.chunks}
        for chunk in first.chunks:
            self.chunk_validator.validate(chunk.model_dump(mode="json"))
            self.assertIsNotNone(chunk.parent_chunk_id)
            if chunk.next_chunk_id is not None:
                self.assertEqual(by_id[chunk.next_chunk_id].previous_chunk_id, chunk.chunk_id)

    def test_roman_numeral_heading_is_preserved_in_section_path(self):
        pdf_bytes = synthetic_text_pdf(
            [
                "I. INTRODUCTION\n"
                "This section contains enough deterministic text for the parse quality gate. "
                "It is mapped to the original PDF page."
            ]
        )

        result = ingest(pdf_bytes, strategy="section_parent_child_v1")

        self.assertIn("I. INTRODUCTION", result.chunks[0].section_path)

    def test_reference_author_initial_is_not_treated_as_major_section(self):
        pdf_bytes = synthetic_text_pdf(
            [
                "I. INTRODUCTION\n"
                + "Auditable introduction text. " * 20
                + "\nREFERENCES\n"
                + "D. Example, P. Author, and Q. Writer, A referenced work.\n"
                + "Reference details remain evidence text. " * 20
            ]
        )

        result = ingest(pdf_bytes, strategy="section_parent_child_v1")

        self.assertFalse(
            any("D. Example" in chunk.section_path for chunk in result.chunks)
        )

    def test_expected_pdf_hash_mismatch_fails_before_parsing(self):
        with self.assertRaises(PdfIngestionError) as captured:
            ingest(self.pdf_bytes, expected_sha256="0" * 64)
        self.assertEqual(captured.exception.code, "PDF_IDENTITY_MISMATCH")

    def test_invalid_and_textless_pdfs_fail_closed(self):
        with self.assertRaises(PdfIngestionError) as invalid:
            ingest(b"not a pdf")
        self.assertEqual(invalid.exception.code, "PDF_SIGNATURE_INVALID")

        with self.assertRaises(PdfIngestionError) as textless:
            ingest(synthetic_text_pdf([""]))
        self.assertEqual(textless.exception.code, "PARSE_QUALITY_GATE_BLOCKED")

    def test_parse_review_requires_explicit_approval(self):
        short_pdf = synthetic_text_pdf(["Short text"])
        with self.assertRaises(PdfIngestionError) as blocked:
            ingest(short_pdf)
        self.assertEqual(blocked.exception.code, "PARSE_QUALITY_GATE_BLOCKED")

        allowed = ingest(short_pdf, allow_parse_review=True)
        self.assertEqual(allowed.parse_status, "REVIEW")
        self.assertEqual(allowed.warnings, ("EXTRACTED_TEXT_TOO_SHORT",))

    def test_ingestion_and_answer_api_complete_without_network(self):
        with patch("socket.socket", side_effect=AssertionError("local flow opened a socket")):
            result = ingest(self.pdf_bytes)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chunks_path = root / "chunks.json"
            chunks_path.write_text(
                json.dumps(
                    [chunk.model_dump(mode="json") for chunk in result.chunks],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            response = TestClient(create_app(chunks_path=chunks_path)).post(
                "/api/v1/rag/answers",
                json={
                    "question": "How are lexical candidates combined before reranking?",
                    "document_ids": ["doc_local_test_001"],
                    "stream": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        answer = response.json()
        self.assertEqual(answer["status"], "COMPLETED")
        self.assertEqual(answer["evidence"][0]["page_start"], 1)
        self.assertEqual(answer["evidence"][0]["page_end"], 2)

    def test_cli_writes_only_chunk_record_array(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "paper.pdf"
            output_path = root / "chunks.json"
            pdf_path.write_bytes(self.pdf_bytes)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.ingestion.cli",
                    "--pdf",
                    str(pdf_path),
                    "--expected-sha256",
                    sha256(self.pdf_bytes).hexdigest(),
                    "--document-id",
                    "doc_local_cli_001",
                    "--tenant-id",
                    "tenant_fixture",
                    "--visibility",
                    "private",
                    "--library-scope-id",
                    "lib_fixture",
                    "--strategy",
                    "fixed_boundary_v1",
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            rows = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIsInstance(rows, list)
            self.assertTrue(rows)
            for row in rows:
                self.chunk_validator.validate(row)


class ParserLimitTests(unittest.TestCase):
    def test_parser_rejects_oversized_input_before_pdf_reader(self):
        parser = PypdfTextParser(maximum_pdf_bytes=4)
        with self.assertRaisesRegex(ValueError, "input limit"):
            parser.parse(b"%PDF-1.4")


if __name__ == "__main__":
    unittest.main()
