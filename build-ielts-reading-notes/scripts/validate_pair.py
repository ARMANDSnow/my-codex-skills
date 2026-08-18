#!/usr/bin/env python3
"""Validate aligned English and Chinese Obsidian IELTS reading notes."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ANCHOR_RE = re.compile(r"\^p(\d{2,3})\b")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
GLOSS_RE = re.compile(r"\*\*[^*]+\*\*（[^）]+）")


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def source_body(text: str) -> str:
    marker = "\n## Key Vocabulary & Phrases\n"
    return text.split(marker, 1)[0]


def heading_levels(text: str) -> list[int]:
    return [len(match.group(1)) for match in HEADING_RE.finditer(text)]


def validate(path_en: Path, path_zh: Path) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    en = path_en.read_text(encoding="utf-8")
    zh = path_zh.read_text(encoding="utf-8")
    en_source = source_body(en)

    en_ids = ANCHOR_RE.findall(en_source)
    zh_ids = ANCHOR_RE.findall(zh)
    if not en_ids:
        fail("English note contains no paragraph IDs.", errors)
    if en_ids != zh_ids:
        fail("English and Chinese paragraph ID sequences differ.", errors)
    expected = [f"{index:02d}" for index in range(1, len(en_ids) + 1)]
    if en_ids != expected:
        fail("Paragraph IDs are not unique and sequential from p01.", errors)

    if heading_levels(en_source) != heading_levels(zh):
        fail("Heading-level sequences differ before the English glossary.", errors)

    en_anchor_lines = [i for i, line in enumerate(en_source.splitlines(), 1) if ANCHOR_RE.search(line)]
    zh_anchor_lines = [i for i, line in enumerate(zh.splitlines(), 1) if ANCHOR_RE.search(line)]
    if en_anchor_lines != zh_anchor_lines:
        warnings.append("Aligned paragraph IDs occur on different line numbers; review blank-line rhythm.")

    for line_number, line in enumerate(en_source.splitlines(), 1):
        count = len(GLOSS_RE.findall(line))
        if count > 3:
            fail(f"Line {line_number} has {count} inline glosses; maximum is 3.", errors)

    if re.search(r"^>\s*\[!", en, re.MULTILINE) or re.search(r"^>\s*\[!", zh, re.MULTILINE):
        fail("Foldable/callout blocks are not allowed in paired notes.", errors)
    if "阅读提示" in en or "Reading tip" in en:
        fail("Reading-tip content remains in the English note.", errors)

    required_en = ["language: en", "parallel-reading", "## Key Vocabulary & Phrases", "| Word | 中文释义 |", "| Phrase | 中文释义 |"]
    required_zh = ["language: zh-CN", "parallel-reading"]
    for marker in required_en:
        if marker not in en:
            fail(f"English note is missing required marker: {marker}", errors)
    for marker in required_zh:
        if marker not in zh:
            fail(f"Chinese note is missing required marker: {marker}", errors)

    metrics = {
        "paragraphs": len(en_ids),
        "annotated_expressions": len(GLOSS_RE.findall(en_source)),
        "vocabulary_rows": table_rows(en, "### Key Vocabulary", "### Key Phrases"),
        "phrase_rows": table_rows(en, "### Key Phrases", "\n[[00-学习首页/"),
    }
    if metrics["annotated_expressions"] > max(6, len(en_ids) * 2):
        warnings.append("Inline gloss density exceeds two per aligned paragraph on average.")
    return errors, warnings, metrics


def table_rows(text: str, start: str, end: str) -> int:
    if start not in text or end not in text:
        return 0
    section = text.split(start, 1)[1].split(end, 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| ")]
    return max(0, len(rows) - 2)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: validate_pair.py <english-note.md> <chinese-note.md>", file=sys.stderr)
        return 2
    path_en, path_zh = map(Path, sys.argv[1:])
    missing = [str(path) for path in (path_en, path_zh) if not path.is_file()]
    if missing:
        print("Missing file(s): " + ", ".join(missing), file=sys.stderr)
        return 2

    errors, warnings, metrics = validate(path_en, path_zh)
    for message in warnings:
        print(f"WARNING: {message}")
    for message in errors:
        print(f"ERROR: {message}")
    print("METRICS: " + ", ".join(f"{key}={value}" for key, value in metrics.items()))
    if errors:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
