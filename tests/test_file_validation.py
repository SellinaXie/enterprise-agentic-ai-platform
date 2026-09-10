"""Upload allowlist, MIME/signature, size, filename, and metadata tests."""

import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile

from app.core.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    InvalidUploadMetadataError,
    UnsupportedFileTypeError,
)
from app.ingestion.parsers import (
    DOCXDocumentParser,
    MarkdownDocumentParser,
    PDFDocumentParser,
    TextDocumentParser,
)
from app.ingestion.router import DocumentParserRouter, sanitize_filename
from app.ingestion.service import FileIngestionService, parse_upload_metadata
from tests.file_fixtures import build_docx, build_pdf


def _router() -> DocumentParserRouter:
    return DocumentParserRouter(
        [
            PDFDocumentParser(min_extracted_characters=1),
            DOCXDocumentParser(),
            TextDocumentParser(),
            MarkdownDocumentParser(),
        ]
    )


@pytest.mark.parametrize(
    ("filename", "mime_type", "data"),
    [
        ("policy.pdf", "application/pdf", build_pdf("Synthetic policy text.")),
        (
            "manual.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            build_docx(),
        ),
        ("notes.txt", "text/plain", b"Synthetic notes"),
        ("guide.md", "text/markdown", b"# Synthetic guide"),
        ("guide.markdown", "text/plain", b"# Synthetic guide"),
    ],
)
def test_supported_extension_mime_and_signature(
    filename: str,
    mime_type: str,
    data: bytes,
) -> None:
    parser = _router().select(filename=filename, mime_type=mime_type, data=data)

    assert parser is not None


@pytest.mark.parametrize(
    ("filename", "mime_type", "data"),
    [
        ("payload.exe", "application/octet-stream", b"MZ"),
        ("fake.pdf", "application/pdf", b"not a pdf"),
        ("fake.txt", "application/pdf", b"plain text"),
        (
            "fake.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PKbad",
        ),
        ("binary.txt", "text/plain", b"hello\x00binary"),
    ],
)
def test_unsupported_or_mismatched_upload_is_rejected(
    filename: str,
    mime_type: str,
    data: bytes,
) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        _router().select(filename=filename, mime_type=mime_type, data=data)


def test_empty_upload_is_rejected() -> None:
    with pytest.raises(EmptyFileError):
        _router().select(filename="empty.txt", mime_type="text/plain", data=b"")


def test_filename_is_display_only_and_path_components_are_removed() -> None:
    assert sanitize_filename("../../policies/review.md") == "review.md"
    assert sanitize_filename(r"..\..\manual.docx") == "manual.docx"
    assert len(sanitize_filename(f"{'x' * 300}.pdf")) == 255


def test_bounded_reader_rejects_upload_before_unlimited_growth() -> None:
    service = FileIngestionService(
        parsers=_router(),
        knowledge=object(),  # type: ignore[arg-type]
        graph=None,
        max_upload_size_bytes=3,
    )
    upload = UploadFile(filename="too-large.txt", file=BytesIO(b"four"))

    with pytest.raises(FileTooLargeError):
        asyncio.run(service._read_bounded(upload))


def test_upload_metadata_must_be_a_json_object() -> None:
    assert parse_upload_metadata('{"department": "risk"}') == {"department": "risk"}
    assert parse_upload_metadata(None) == {}
    with pytest.raises(InvalidUploadMetadataError):
        parse_upload_metadata("[1, 2]")
    with pytest.raises(InvalidUploadMetadataError):
        parse_upload_metadata("{bad json")
