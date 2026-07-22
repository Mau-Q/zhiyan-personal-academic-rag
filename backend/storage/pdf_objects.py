"""Immutable, content-verified PDF object storage for the local Stage 1 Gate."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from backend.storage.models import PdfObjectV1


class PdfObjectStoreError(RuntimeError):
    """Raised when object identity, persistence, or replay verification fails."""


class FilesystemPdfObjectStore:
    """Persist PDFs under deterministic opaque keys in an operator-owned data root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @staticmethod
    def object_key(
        *,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        content_sha256: str,
    ) -> str:
        identity = f"{owner_id}\0{document_id}\0{document_version_id}".encode("utf-8")
        identity_sha256 = sha256(identity).hexdigest()
        return (
            f"pdf/v1/{identity_sha256[:2]}/{identity_sha256}/"
            f"{content_sha256}.pdf"
        )

    def put_pdf(
        self,
        pdf_bytes: bytes,
        *,
        owner_id: str,
        document_id: str,
        document_version_id: str,
        content_sha256: str,
    ) -> PdfObjectV1:
        actual_sha256 = sha256(pdf_bytes).hexdigest()
        if not pdf_bytes or actual_sha256 != content_sha256:
            raise PdfObjectStoreError("PDF object bytes do not match content identity")
        object_key = self.object_key(
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=document_version_id,
            content_sha256=content_sha256,
        )
        target = self._target(object_key)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.exists():
            self._verify_file(target, expected_sha256=content_sha256)
        else:
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=target.parent,
                    prefix=".pdf-object-",
                    delete=False,
                ) as temporary:
                    temporary.write(pdf_bytes)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                    temporary_path = Path(temporary.name)
                os.replace(temporary_path, target)
                temporary_path = None
                if os.name != "nt":
                    target.chmod(0o600)
                self._verify_file(target, expected_sha256=content_sha256)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
        return PdfObjectV1(
            owner_id=owner_id,
            document_id=document_id,
            document_version_id=document_version_id,
            object_key=object_key,
            storage_backend="filesystem_v1",
            content_sha256=content_sha256,
            size_bytes=len(pdf_bytes),
            stored_at=datetime.fromtimestamp(target.stat().st_mtime, timezone.utc),
        )

    def read_pdf(self, pdf_object: PdfObjectV1) -> bytes:
        target = self._target(pdf_object.object_key)
        self._verify_file(target, expected_sha256=pdf_object.content_sha256)
        payload = target.read_bytes()
        if len(payload) != pdf_object.size_bytes:
            raise PdfObjectStoreError("PDF object size drifted after persistence")
        return payload

    def delete_pdf(self, pdf_object: PdfObjectV1) -> bool:
        """Delete the exact verified object; a missing replay is already complete."""

        target = self._target(pdf_object.object_key)
        if not target.exists():
            return False
        self._verify_file(target, expected_sha256=pdf_object.content_sha256)
        target.unlink()
        return True

    def _target(self, object_key: str) -> Path:
        target = self.root.joinpath(*object_key.split("/")).resolve()
        if not target.is_relative_to(self.root):
            raise PdfObjectStoreError("PDF object key escaped the configured data root")
        return target

    @staticmethod
    def _verify_file(path: Path, *, expected_sha256: str) -> None:
        if not path.is_file():
            raise PdfObjectStoreError("PDF object is missing from persistent storage")
        actual_sha256 = sha256(path.read_bytes()).hexdigest()
        if actual_sha256 != expected_sha256:
            raise PdfObjectStoreError("PDF object payload drifted after persistence")
