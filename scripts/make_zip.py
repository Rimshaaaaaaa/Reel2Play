#!/usr/bin/env python3
"""Build reel2play.zip from this folder, leaving out everything .gitignore excludes.

Also refuses to build if a .env file or anything that looks like a secret would be packed.

    python3 scripts/make_zip.py ../reel2play.zip
"""

from __future__ import annotations

import fnmatch
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = "reel2play"
MAX_FILE_BYTES = 2 * 1024 * 1024
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    # The value must be on the same line: "TOKEN=" followed by the next setting is not a secret.
    re.compile(r"(?i)(api[_-]?key|secret|token|password)[ \t]*[=:][ \t]*['\"]?[A-Za-z0-9_\-]{24,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bEAA[A-Za-z0-9]{40,}"),  # Meta access tokens
]


def load_rules(root: Path) -> list[tuple[str, bool]]:
    rules: list[tuple[str, bool]] = [(".git/", False)]
    for line in (root / ".gitignore").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rules.append((line[1:], True) if line.startswith("!") else (line, False))
    return rules


def ignored(relative: str, is_dir: bool, rules: list[tuple[str, bool]]) -> bool:
    name = relative.rsplit("/", 1)[-1]
    result = False
    for pattern, negated in rules:
        dir_only = pattern.endswith("/")
        bare = pattern.rstrip("/")
        if dir_only and not is_dir:
            continue
        target = relative if "/" in bare else name
        if fnmatch.fnmatch(target, bare.lstrip("/")):
            result = not negated
    return result


def collect(root: Path) -> list[Path]:
    rules = load_rules(root)
    files: list[Path] = []

    def walk(directory: Path) -> None:
        for entry in sorted(directory.iterdir()):
            relative = entry.relative_to(root).as_posix()
            if ignored(relative, entry.is_dir(), rules):
                continue
            if entry.is_dir():
                walk(entry)
            else:
                files.append(entry)

    walk(root)
    return files


def check(files: list[Path], root: Path) -> list[str]:
    problems: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            problems.append(f"{relative}: environment file")
        if path.stat().st_size > MAX_FILE_BYTES:
            problems.append(f"{relative}: larger than 2 MB")
        if path.suffix in {".mp4", ".mov", ".webm", ".jpg", ".png", ".webp"} and not (
            relative.startswith(("fixtures/", "samples/"))
            or "/public/" in relative
            or "/assets/" in relative
        ):
            problems.append(f"{relative}: media outside the fixtures folder")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"{relative}: looks like it contains a secret")
                break
    return problems


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "reel2play.zip").resolve()
    files = collect(ROOT)
    problems = check(files, ROOT)
    if problems:
        print("Refusing to build the ZIP:\n  " + "\n  ".join(problems))
        return 1
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, f"{ARCHIVE_ROOT}/{path.relative_to(ROOT).as_posix()}")
    print(f"{target} ({len(files)} files, {target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
