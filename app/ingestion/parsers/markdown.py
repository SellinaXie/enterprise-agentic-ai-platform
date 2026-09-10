"""Markdown-preserving textual parser with lightweight heading provenance."""

import re
from pathlib import PurePath

from app.ingestion.models import FileFormat, ParsedDocument, ParsedDocumentSegment
from app.ingestion.parsers.text import TextDocumentParser
from app.models.knowledge import KnowledgeSourceType

HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


class MarkdownDocumentParser:
    """Keep Markdown as text while tracking headings for source attribution."""

    file_format = FileFormat.MARKDOWN

    def parse(self, data: bytes, *, filename: str, mime_type: str) -> ParsedDocument:
        decoded = TextDocumentParser().parse(data, filename=filename, mime_type=mime_type).text
        sections: list[str] = []
        segments: list[ParsedDocumentSegment] = []
        block: list[str] = []
        current_heading: str | None = None

        def flush() -> None:
            text = "\n".join(block).strip()
            if text:
                segments.append(ParsedDocumentSegment(text=text, section_heading=current_heading))
            block.clear()

        for line in decoded.splitlines():
            match = HEADING_PATTERN.match(line)
            if match:
                flush()
                current_heading = match.group(1).strip()
                sections.append(current_heading)
                block.append(line)
            else:
                block.append(line)
        flush()
        title = sections[0] if sections else PurePath(filename).stem
        return ParsedDocument(
            text="\n\n".join(segment.text for segment in segments),
            title=title,
            filename=filename,
            mime_type=mime_type,
            file_format=self.file_format,
            source_type=KnowledgeSourceType.MARKDOWN,
            sections=sections,
            parser_name="markdown_text",
            parser_version="1",
            extraction_method="utf8_markdown_preserved",
            metadata={"heading_count": len(sections)},
            segments=segments,
        )
