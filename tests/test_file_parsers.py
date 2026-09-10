"""Deterministic parser tests for every V6.5 enterprise document format."""

import pytest

from app.core.exceptions import (
    DocumentParseError,
    EncryptedPDFError,
    OCRRequiredError,
    TextDecodeError,
)
from app.ingestion.parsers import (
    DOCXDocumentParser,
    MarkdownDocumentParser,
    PDFDocumentParser,
    TextDocumentParser,
)
from app.models.knowledge import KnowledgeSourceType
from tests.file_fixtures import build_docx, build_pdf


def test_pdf_extracts_multiple_pages_with_page_provenance() -> None:
    parser = PDFDocumentParser(min_extracted_characters=1)

    parsed = parser.parse(
        build_pdf("Page one compliance evidence.", "Page two human review evidence."),
        filename="policy.pdf",
        mime_type="application/pdf",
    )

    assert parsed.page_count == 2
    assert [segment.page_number for segment in parsed.segments] == [1, 2]
    assert "Page one" in parsed.text and "Page two" in parsed.text
    assert parsed.metadata["ocr_used"] is False


def test_pdf_malformed_encrypted_and_image_only_fail_safely() -> None:
    parser = PDFDocumentParser(min_extracted_characters=1)
    with pytest.raises(DocumentParseError):
        parser.parse(b"%PDF-malformed", filename="bad.pdf", mime_type="application/pdf")
    with pytest.raises(EncryptedPDFError):
        parser.parse(
            build_pdf("Secret synthetic text", encrypted=True),
            filename="locked.pdf",
            mime_type="application/pdf",
        )
    with pytest.raises(OCRRequiredError):
        parser.parse(build_pdf(""), filename="scan.pdf", mime_type="application/pdf")


def test_docx_extracts_headings_paragraphs_and_tables_in_reading_order() -> None:
    parsed = DOCXDocumentParser().parse(
        build_docx(),
        filename="manual.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert parsed.title == "Synthetic Governance Manual"
    assert parsed.sections == ["Human Review"]
    assert "Authorized reviewers" in parsed.text
    assert "Control | Owner" in parsed.text
    assert parsed.segments[-1].section_heading == "Human Review"


def test_docx_malformed_and_empty_fail_safely() -> None:
    with pytest.raises(DocumentParseError):
        DOCXDocumentParser().parse(
            b"PKmalformed",
            filename="bad.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    with pytest.raises(DocumentParseError):
        DOCXDocumentParser().parse(
            build_docx(include_content=False),
            filename="empty.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def test_txt_handles_utf8_bom_and_newlines() -> None:
    parsed = TextDocumentParser().parse(
        b"\xef\xbb\xbfFirst line\r\nSecond line",
        filename="notes.txt",
        mime_type="text/plain",
    )

    assert parsed.text == "First line\r\nSecond line"
    assert parsed.source_type == KnowledgeSourceType.TEXT


def test_txt_invalid_utf8_and_empty_text_fail_safely() -> None:
    with pytest.raises(TextDecodeError):
        TextDocumentParser().parse(b"\xff\xfeinvalid", filename="bad.txt", mime_type="text/plain")
    with pytest.raises(DocumentParseError):
        TextDocumentParser().parse(b" \n ", filename="empty.txt", mime_type="text/plain")


def test_markdown_preserves_lists_code_and_section_metadata() -> None:
    content = b"# Governance\n\n- Human review\n\n```python\nprint('data only')\n```"
    parsed = MarkdownDocumentParser().parse(
        content,
        filename="guide.md",
        mime_type="text/markdown",
    )

    assert parsed.title == "Governance"
    assert parsed.sections == ["Governance"]
    assert "- Human review" in parsed.text
    assert "```python" in parsed.text
    assert parsed.source_type == KnowledgeSourceType.MARKDOWN


def test_empty_markdown_fails_safely() -> None:
    with pytest.raises(DocumentParseError):
        MarkdownDocumentParser().parse(b"\n\n", filename="empty.md", mime_type="text/markdown")
