
"""Tests for document upload and listing endpoints."""

from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient

import backend.app as app_module
from backend.activity_store import ActivityStore
from backend.app import create_app
from backend.document_extractor import MAX_DOCUMENT_SIZE


def create_docx(content: str) -> bytes:
    """Create an in-memory DOCX document for testing."""
    buffer = BytesIO()
    document = Document()

    if content:
        document.add_paragraph(content)

    document.save(buffer)
    return buffer.getvalue()


def create_pdf(content: str) -> bytes:
    """Create a minimal text PDF for testing."""
    stream = (
        f"BT /F1 12 Tf 72 720 Td ({content}) Tj ET"
    ).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> "
            b"/Contents 4 0 R >>"
        ),
        (
            f"<< /Length {len(stream)} >>\n".encode()
            + b"stream\n"
            + stream
            + b"\nendstream"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]

    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode())
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())

    pdf.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )

    return bytes(pdf)

def create_client(tmp_path):
    """Create a test client with an isolated SQLite database."""
    store = ActivityStore(tmp_path / "activity.db")
    return TestClient(create_app(activity_store=store))


def test_upload_docx_success(tmp_path):
    client = create_client(tmp_path)
    content = create_docx("ContextTrace document upload test")

    response = client.post(
        "/documents",
        files={
            "file": (
                "test_document.docx",
                content,
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 201

    body = response.json()
    assert body["ok"] is True
    assert body["error"] is None
    assert body["data"]["file_name"] == "test_document.docx"
    assert body["data"]["file_type"] == ".docx"
    assert "ContextTrace document upload test" in body["data"]["extracted_text"]


def test_upload_unsupported_extension(tmp_path):
    client = create_client(tmp_path)

    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 415


def test_upload_docx_without_extractable_text(tmp_path):
    client = create_client(tmp_path)
    content = create_docx("")

    response = client.post(
        "/documents",
        files={
            "file": (
                "empty.docx",
                content,
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 422


def test_list_documents_after_upload(tmp_path):
    client = create_client(tmp_path)
    content = create_docx("Document stored for listing")

    upload_response = client.post(
        "/documents",
        files={
            "file": (
                "stored.docx",
                content,
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document",
            )
        },
    )

    assert upload_response.status_code == 201

    response = client.get("/documents")

    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is True
    assert body["error"] is None
    assert len(body["data"]["documents"]) == 1
    assert body["data"]["documents"][0]["file_name"] == "stored.docx"
    assert (
        "Document stored for listing"
        in body["data"]["documents"][0]["extracted_text"]
    )


def test_list_documents_empty_database(tmp_path):
    client = create_client(tmp_path)

    response = client.get("/documents")

    assert response.status_code == 200
    assert response.json()["data"]["documents"] == []


def test_list_documents_rejects_invalid_limit(tmp_path):
    client = create_client(tmp_path)

    response = client.get("/documents?limit=0")

    assert response.status_code == 422


def test_upload_pdf_success(tmp_path):
    client = create_client(tmp_path)
    content = create_pdf("ContextTrace PDF upload test")

    response = client.post(
        "/documents",
        files={"file": ("test_document.pdf", content, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["file_name"] == "test_document.pdf"
    assert body["data"]["file_type"] == ".pdf"
    assert "ContextTrace PDF upload test" in body["data"]["extracted_text"]


def test_upload_document_exceeding_size_limit(tmp_path):
    client = create_client(tmp_path)
    content = b"x" * (MAX_DOCUMENT_SIZE + 1)

    response = client.post(
        "/documents",
        files={"file": ("large.docx", content, "application/octet-stream")},
    )

    assert response.status_code == 413


def test_upload_corrupted_docx(tmp_path):
    client = create_client(tmp_path)

    response = client.post(
        "/documents",
        files={"file": ("corrupted.docx", b"not a valid DOCX", "application/octet-stream")},
    )

    assert response.status_code == 422


def test_upload_corrupted_docx_cleans_up_temporary_file(
    tmp_path, monkeypatch
):
    client = create_client(tmp_path)
    created_paths = []
    original_named_temporary_file = app_module.tempfile.NamedTemporaryFile

    def tracking_named_temporary_file(*args, **kwargs):
        temporary_file = original_named_temporary_file(*args, **kwargs)
        created_paths.append(Path(temporary_file.name))
        return temporary_file

    monkeypatch.setattr(
        app_module.tempfile,
        "NamedTemporaryFile",
        tracking_named_temporary_file,
    )

    response = client.post(
        "/documents",
        files={"file": ("corrupted.docx", b"invalid DOCX", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert len(created_paths) == 1
    assert not created_paths[0].exists()