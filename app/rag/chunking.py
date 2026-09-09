"""Deterministic, explainable text normalization and chunking."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextChunk:
    """One normalized chunk with a stable document-relative index."""

    index: int
    content: str


def normalize_text(raw_text: str) -> str:
    """Normalize line endings and excess blank lines without rewriting content."""
    normalized_lines: list[str] = []
    previous_blank = False
    for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = line.rstrip()
        is_blank = not cleaned.strip()
        if is_blank:
            if normalized_lines and not previous_blank:
                normalized_lines.append("")
        else:
            normalized_lines.append(cleaned)
        previous_blank = is_blank
    return "\n".join(normalized_lines).strip()


def chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
    """Split normalized text at natural boundaries with deterministic overlap."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    normalized = normalize_text(text)
    if not normalized:
        return []

    chunks: list[TextChunk] = []
    start = 0
    minimum_boundary = chunk_size // 2
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            search_start = min(start + minimum_boundary, end)
            boundary = normalized.rfind("\n\n", search_start, end)
            if boundary < 0:
                boundary = normalized.rfind("\n", search_start, end)
            if boundary < 0:
                boundary = normalized.rfind(" ", search_start, end)
            if boundary >= search_start:
                end = boundary

        content = normalized[start:end].strip()
        if content:
            chunks.append(TextChunk(index=len(chunks), content=content))
        if end >= len(normalized):
            break
        next_start = max(end - overlap, start + 1)
        start = next_start

    return chunks
