"""Parser protocol shared by all allowlisted enterprise document adapters."""

from typing import Protocol

from app.ingestion.models import FileFormat, ParsedDocument


class DocumentParser(Protocol):
    """Convert validated bytes into a format-neutral parsed document."""

    file_format: FileFormat

    def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument: ...
