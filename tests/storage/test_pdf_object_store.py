from __future__ import annotations

import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from backend.storage.pdf_objects import FilesystemPdfObjectStore, PdfObjectStoreError


class FilesystemPdfObjectStoreTests(unittest.TestCase):
    def test_pdf_is_persistent_opaque_and_replay_safe(self):
        payload = b"%PDF-1.4\npersistent runtime object\n%%EOF"
        content_sha256 = sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            store = FilesystemPdfObjectStore(Path(directory))
            arguments = {
                "owner_id": "owner_001",
                "document_id": "document_001",
                "document_version_id": "version_001",
                "content_sha256": content_sha256,
            }

            first = store.put_pdf(payload, **arguments)
            second = store.put_pdf(payload, **arguments)

            self.assertEqual(second, first)
            self.assertEqual(store.read_pdf(first), payload)
            self.assertNotIn("owner_001", first.object_key)
            self.assertNotIn("version_001", first.object_key)
            self.assertTrue((Path(directory) / first.object_key).is_file())
            self.assertTrue(store.delete_pdf(first))
            self.assertFalse(store.delete_pdf(first))
            self.assertFalse((Path(directory) / first.object_key).exists())

    def test_identity_mismatch_and_persisted_payload_drift_fail_closed(self):
        payload = b"%PDF-1.4\nsource\n%%EOF"
        content_sha256 = sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            store = FilesystemPdfObjectStore(Path(directory))
            with self.assertRaises(PdfObjectStoreError):
                store.put_pdf(
                    payload,
                    owner_id="owner_001",
                    document_id="document_001",
                    document_version_id="version_001",
                    content_sha256="0" * 64,
                )

            stored = store.put_pdf(
                payload,
                owner_id="owner_001",
                document_id="document_001",
                document_version_id="version_001",
                content_sha256=content_sha256,
            )
            (Path(directory) / stored.object_key).write_bytes(b"drift")
            with self.assertRaises(PdfObjectStoreError):
                store.read_pdf(stored)


if __name__ == "__main__":
    unittest.main()
