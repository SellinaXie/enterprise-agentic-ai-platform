"""Filename, MIME, and signature validation plus allowlisted parser routing."""

import re
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from app.core.exceptions import EmptyFileError, UnsupportedFileTypeError
from app.ingestion.models import FileFormat
from app.ingestion.parsers.base import DocumentParser

CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
MAX_FILENAME_LENGTH = 255

MIME_TYPES = {
    ".pdf": frozenset({"application/pdf", "application/x-pdf"}),
    ".docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    ".txt": frozenset({"text/plain"}),
    ".md": frozenset({"text/markdown", "text/x-markdown", "text/plain"}),
    ".markdown": frozenset({"text/markdown", "text/x-markdown", "text/plain"}),
}

FORMAT_BY_EXTENSION = {
    ".pdf": FileFormat.PDF,
    ".docx": FileFormat.DOCX,
    ".txt": FileFormat.TXT,
    ".md": FileFormat.MARKDOWN,
    ".markdown": FileFormat.MARKDOWN,
}


def sanitize_filename(value: str | None) -> str:
    """Reduce an untrusted upload name to bounded display-only metadata."""
    candidate = (value or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    candidate = CONTROL_CHARACTERS.sub("", candidate)
    if not candidate or candidate in {".", ".."}:
        raise UnsupportedFileTypeError
    suffix = PurePath(candidate).suffix[-20:]
    if len(candidate) > MAX_FILENAME_LENGTH:
        stem_limit = MAX_FILENAME_LENGTH - len(suffix)
        candidate = f"{PurePath(candidate).stem[:stem_limit]}{suffix}"
    return candidate


class DocumentParserRouter:
    """Select exactly one parser after layered upload validation."""

    def __init__(self, parsers: list[DocumentParser]) -> None:
        self._parsers = {parser.file_format: parser for parser in parsers}

    def select(
        self,
        *,
        filename: str,
        mime_type: str | None,
        data: bytes,
    ) -> DocumentParser:
        if not data:
            raise EmptyFileError
        extension = PurePath(filename).suffix.casefold()
        file_format = FORMAT_BY_EXTENSION.get(extension)
        normalized_mime = (mime_type or "").split(";", 1)[0].strip().casefold()
        if file_format is None or normalized_mime not in MIME_TYPES[extension]:
            raise UnsupportedFileTypeError
        if file_format == FileFormat.PDF and not data.startswith(b"%PDF-"):
            raise UnsupportedFileTypeError
        if file_format == FileFormat.DOCX and not _is_docx_package(data):
            raise UnsupportedFileTypeError
        if file_format in {FileFormat.TXT, FileFormat.MARKDOWN} and b"\x00" in data:
            raise UnsupportedFileTypeError
        parser = self._parsers.get(file_format)
        if parser is None:
            raise UnsupportedFileTypeError
        return parser


def _is_docx_package(data: bytes) -> bool:
    if not data.startswith(b"PK"):
        return False
    try:
        with ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
    except (BadZipFile, OSError):
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names
