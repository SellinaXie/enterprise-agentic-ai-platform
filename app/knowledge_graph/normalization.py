"""Conservative deterministic entity-name normalization."""

import unicodedata


def normalize_entity_name(value: str) -> str:
    """Normalize Unicode, surrounding/internal whitespace, and case only."""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def canonicalize_entity_name(value: str) -> str:
    """Preserve display case while removing accidental whitespace variation."""
    return " ".join(unicodedata.normalize("NFKC", value).split())
