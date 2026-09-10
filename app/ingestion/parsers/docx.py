"""DOCX paragraph, heading, and table text parser."""

from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile

import docx
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError

from app.core.exceptions import DocumentParseError
from app.ingestion.models import FileFormat, ParsedDocument, ParsedDocumentSegment
from app.models.knowledge import KnowledgeSourceType


class DOCXDocumentParser:
    """Preserve readable OOXML order without attempting Word layout reconstruction."""

    file_format = FileFormat.DOCX

    def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument:
        try:
            document = Document(BytesIO(data))
            segments, sections = self._extract(document)
            core_title = (document.core_properties.title or "").strip()
        except (
            PackageNotFoundError,
            BadZipFile,
            XMLSyntaxError,
            KeyError,
            ValueError,
            TypeError,
        ) as exc:
            raise DocumentParseError from exc

        text = "\n\n".join(segment.text for segment in segments)
        if not text.strip():
            raise DocumentParseError
        title = core_title or (sections[0] if sections else PurePath(filename).stem)
        return ParsedDocument(
            text=text,
            title=title[:300],
            filename=filename,
            mime_type=mime_type,
            file_format=self.file_format,
            source_type=KnowledgeSourceType.TEXT,
            sections=sections,
            parser_name="python-docx",
            parser_version=docx.__version__,
            extraction_method="ooxml_reading_order",
            metadata={"heading_count": len(sections)},
            segments=segments,
        )

    @staticmethod
    def _extract(document: object) -> tuple[list[ParsedDocumentSegment], list[str]]:
        segments: list[ParsedDocumentSegment] = []
        sections: list[str] = []
        current_heading: str | None = None
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if not text:
                    continue
                style_name = block.style.name if block.style is not None else ""
                if style_name.startswith("Heading"):
                    current_heading = text
                    sections.append(text)
                segments.append(ParsedDocumentSegment(text=text, section_heading=current_heading))
            elif isinstance(block, Table):
                rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in block.rows]
                table_text = "\n".join(row for row in rows if row.strip(" |"))
                if table_text:
                    segments.append(
                        ParsedDocumentSegment(
                            text=table_text,
                            section_heading=current_heading,
                        )
                    )
        return segments, sections
