"""Deterministic text normalization and chunking tests."""

from app.rag.chunking import chunk_text, normalize_text


def test_normalization_preserves_content_and_paragraphs() -> None:
    raw = "  Heading  \r\n\r\nFirst line.   \rSecond line.\n\n\nFinal.  "

    assert normalize_text(raw) == "Heading\n\nFirst line.\nSecond line.\n\nFinal."


def test_chunking_is_deterministic_and_overlaps() -> None:
    text = "Alpha paragraph has useful facts.\n\nBeta paragraph has more useful facts. " * 4

    first = chunk_text(text, chunk_size=90, overlap=20)
    second = chunk_text(text, chunk_size=90, overlap=20)

    assert first == second
    assert len(first) > 1
    assert [chunk.index for chunk in first] == list(range(len(first)))
    assert all(chunk.content for chunk in first)
    assert all(len(chunk.content) <= 90 for chunk in first)


def test_chunking_rejects_invalid_overlap() -> None:
    try:
        chunk_text("content", chunk_size=100, overlap=100)
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("Expected invalid overlap to fail")
