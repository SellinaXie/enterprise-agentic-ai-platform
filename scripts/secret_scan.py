"""Conservative tracked-file secret-pattern scan for local and CI use."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
PATTERNS = {
    "OpenAI-style key": re.compile(r"\bsk-" + r"[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA" + r"[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(
        r"\b(?:gh[pousr]_" + r"[A-Za-z0-9]{36,}|github_pat_" + r"[A-Za-z0-9_]{40,})\b"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
PASSWORD_ASSIGNMENT = re.compile(r"(?im)^\s*(?:[A-Z0-9_]*PASSWORD|password)\s*[:=]\s*([^#\r\n]+)")
ALLOWED_PASSWORD_VALUES = (
    "${",
    "change-me",
    "ci-",
    "local-development-only",
    "placeholder",
    "replace-with",
    "<",
)


def candidate_files() -> list[Path]:
    """Return tracked and non-ignored new files without interpreting filenames as options."""
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    )
    return [ROOT / value.decode() for value in output.split(b"\0") if value]


def main() -> int:
    findings: list[str] = []
    for path in candidate_files():
        if path == SELF or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(ROOT)
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append(f"{relative}: possible {label}")
        if path.suffix in {".yaml", ".yml", ".toml"} or path.name.startswith(".env"):
            for match in PASSWORD_ASSIGNMENT.finditer(content):
                value = match.group(1).strip().strip("\"'").casefold()
                if value and not value.startswith(ALLOWED_PASSWORD_VALUES):
                    findings.append(f"{relative}: possible committed password value")

    if findings:
        print("\n".join(findings))
        return 1
    print("No high-confidence tracked-file secret patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
