"""Strict UTF-8 plain-text parser."""

from pathlib import PurePath

from app.core.exceptions import DocumentParseError, TextDecodeError
from app.ingestion.models import FileFormat, ParsedDocument, ParsedDocumentSegment
from app.models.knowledge import KnowledgeSourceType


class TextDocumentParser:
    """Decode UTF-8 or UTF-8-with-BOM without guessing legacy encodings."""

    file_format = FileFormat.TXT

    def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise TextDecodeError from exc
        if not text.strip():
            raise DocumentParseError
        return ParsedDocument(
            text=text,
            title=PurePath(filename).stem,
            filename=filename,
            mime_type=mime_type,
            file_format=self.file_format,
            source_type=KnowledgeSourceType.TEXT,
            parser_name="utf8_text",
            parser_version="1",
            extraction_method="utf8_decode",
            segments=[ParsedDocumentSegment(text=text)] if text.strip() else [],
        )
