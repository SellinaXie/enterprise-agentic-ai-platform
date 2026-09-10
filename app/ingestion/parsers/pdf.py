"""Text-only PDF adapter with explicit encrypted and OCR-required boundaries."""

from io import BytesIO
from pathlib import PurePath

from pypdf import PdfReader
from pypdf import __version__ as pypdf_version
from pypdf.errors import PdfReadError

from app.core.exceptions import DocumentParseError, EncryptedPDFError, OCRRequiredError
from app.ingestion.models import FileFormat, ParsedDocument, ParsedDocumentSegment
from app.models.knowledge import KnowledgeSourceType


class PDFDocumentParser:
    """Extract digitally encoded PDF text page by page; never invoke OCR."""

    file_format = FileFormat.PDF

    def __init__(self, *, min_extracted_characters: int) -> None:
        self._minimum_characters = min_extracted_characters

    def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument:
        try:
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise EncryptedPDFError
            segments = []
            for page_number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    segments.append(ParsedDocumentSegment(text=text, page_number=page_number))
            metadata = reader.metadata
            metadata_title = metadata.title if metadata is not None else None
        except EncryptedPDFError:
            raise
        except (PdfReadError, OSError, TypeError, ValueError, KeyError) as exc:
            raise DocumentParseError from exc

        text = "\n\n".join(segment.text for segment in segments)
        meaningful_characters = len("".join(text.split()))
        if meaningful_characters < self._minimum_characters:
            raise OCRRequiredError

        title = str(metadata_title).strip() if metadata_title else PurePath(filename).stem
        return ParsedDocument(
            text=text,
            title=title[:300],
            filename=filename,
            mime_type=mime_type,
            file_format=self.file_format,
            source_type=KnowledgeSourceType.TEXT,
            page_count=len(reader.pages),
            parser_name="pypdf",
            parser_version=pypdf_version,
            extraction_method="digital_text_per_page",
            metadata={"page_count": len(reader.pages), "ocr_used": False},
            segments=segments,
        )
