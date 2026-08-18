#!/usr/bin/env python3
"""Validate translated textbook TXT and EPUB deliverables with stdlib only."""

from __future__ import annotations

import argparse
import posixpath
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

VISIBLE_PAGE_LABEL = re.compile(r"原书第\s*\d+\s*页")
EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"


def validate_txt(path: Path, errors: list[str]) -> None:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"TXT is not readable UTF-8: {exc}")
        return
    if "\r\n" in text or "\r" in text:
        errors.append("TXT must use LF line endings")
    if VISIBLE_PAGE_LABEL.search(text):
        errors.append("TXT contains a visible source-page label")
    if not text.strip():
        errors.append("TXT is empty")


def collect_ids(root: ET.Element) -> set[str]:
    return {elem.attrib["id"] for elem in root.iter() if "id" in elem.attrib}


def validate_epub(path: Path, errors: list[str], warnings: list[str]) -> None:
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"EPUB is not a readable ZIP: {exc}")
        return
    with zf:
        names = zf.namelist()
        if not names or names[0] != "mimetype":
            errors.append("EPUB mimetype must be the first entry")
        elif zf.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            errors.append("EPUB mimetype must be uncompressed")
        elif zf.read("mimetype") != b"application/epub+zip":
            errors.append("EPUB mimetype has the wrong value")

        roots: dict[str, ET.Element] = {}
        for name in names:
            if name.endswith((".xml", ".opf", ".xhtml")):
                try:
                    roots[name] = ET.fromstring(zf.read(name))
                except ET.ParseError as exc:
                    errors.append(f"Malformed XML in {name}: {exc}")

        for name, root in roots.items():
            if not name.endswith(".xhtml"):
                continue
            visible = " ".join(text.strip() for text in root.itertext() if text.strip())
            if VISIBLE_PAGE_LABEL.search(visible):
                errors.append(f"Visible source-page label found in {name}")
            for elem in root.iter():
                if elem.attrib.get(EPUB_TYPE) == "pagebreak":
                    if not elem.attrib.get("id") or not elem.attrib.get("title"):
                        errors.append(f"Pagebreak without id/title in {name}")
                    if "".join(elem.itertext()).strip():
                        errors.append(f"Pagebreak anchor contains visible text in {name}")
                for attr in ("href", "src"):
                    ref = elem.attrib.get(attr)
                    if not ref or ref.startswith(("http:", "https:", "mailto:", "#")):
                        continue
                    ref_path, _, fragment = ref.partition("#")
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(name), ref_path)) if ref_path else name
                    if target not in names:
                        errors.append(f"Missing EPUB resource: {name} -> {ref}")
                    elif fragment and target.endswith(".xhtml") and target in roots:
                        if fragment not in collect_ids(roots[target]):
                            errors.append(f"Broken EPUB fragment: {name} -> {ref}")

    epubcheck = shutil.which("epubcheck")
    if epubcheck:
        result = subprocess.run([epubcheck, str(path)], capture_output=True, text=True)
        if result.returncode:
            errors.append("EPUBCheck failed:\n" + (result.stdout + result.stderr).strip())
    else:
        warnings.append("epubcheck is not installed; only internal validation ran")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--txt", type=Path)
    parser.add_argument("--epub", type=Path)
    args = parser.parse_args()
    if not args.txt and not args.epub:
        parser.error("provide --txt, --epub, or both")

    errors: list[str] = []
    warnings: list[str] = []
    if args.txt:
        validate_txt(args.txt, errors)
    if args.epub:
        validate_epub(args.epub, errors, warnings)

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("Translated textbook validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
