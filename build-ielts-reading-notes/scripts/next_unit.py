#!/usr/bin/env python3
"""Allocate the next numbered IELTS reading-unit folder."""

from __future__ import annotations

import re
import sys
from pathlib import Path


UNIT_RE = re.compile(r"^(\d{3}) - ")


def clean_component(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]", "-", value.strip())
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .-")


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: next_unit.py <vault-root> <chinese-topic> <publisher>", file=sys.stderr)
        return 2

    vault = Path(sys.argv[1]).expanduser().resolve()
    topic = clean_component(sys.argv[2])
    publisher = clean_component(sys.argv[3])
    if not vault.is_dir():
        print(f"Vault does not exist: {vault}", file=sys.stderr)
        return 2
    if not topic or not publisher:
        print("Topic and publisher must not be empty.", file=sys.stderr)
        return 2

    article_root = vault / "01-精读文章"
    numbers = []
    if article_root.is_dir():
        for child in article_root.iterdir():
            if child.is_dir() and (match := UNIT_RE.match(child.name)):
                numbers.append(int(match.group(1)))

    next_number = max(numbers, default=0) + 1
    if next_number > 999:
        print("No three-digit unit numbers remain.", file=sys.stderr)
        return 1

    unit = f"{next_number:03d}"
    folder = f"{unit} - {topic} - {publisher}"
    print(f"unit={unit}")
    print(f"folder={folder}")
    print(f"path={article_root / folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
