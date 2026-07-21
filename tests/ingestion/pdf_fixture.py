"""Minimal in-memory text PDF fixture.

Adapted from Zhiyan Paper Reading Agent under its MIT License. See
``docs/THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations


def synthetic_text_pdf(page_texts: list[str]) -> bytes:
    page_count = len(page_texts)
    font_id = 3 + page_count * 2
    page_ids = [3 + index * 2 for index in range(page_count)]
    content_ids = [page_id + 1 for page_id in page_ids]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{item} 0 R' for item in page_ids)}] "
            f"/Count {page_count} >>"
        ).encode("ascii"),
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page_id, content_id, text in zip(page_ids, content_ids, page_texts, strict=True):
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        escaped_lines = []
        for line in text.splitlines() or [""]:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            escaped_lines.append(f"({escaped}) Tj T*")
        stream = (
            "BT /F1 11 Tf 72 720 Td 14 TL " + " ".join(escaped_lines) + " ET"
        ).encode("latin-1")
        objects[content_id] = (
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        )

    payload = bytearray(b"%PDF-1.4\n%synthetic\n")
    offsets = [0] * (font_id + 1)
    for object_id in range(1, font_id + 1):
        offsets[object_id] = len(payload)
        payload.extend(f"{object_id} 0 obj\n".encode("ascii"))
        payload.extend(objects[object_id])
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {font_id + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for object_id in range(1, font_id + 1):
        payload.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {font_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(payload)
