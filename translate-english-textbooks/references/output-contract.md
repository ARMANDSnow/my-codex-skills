# TXT and EPUB Output Contract

## TXT

- UTF-8 with consistent LF line endings.
- Include title, author, translated table of contents, heading hierarchy, full body, captions, exercises, answers, glossary, and index when in scope.
- Use readable plain-text numbering and tables; do not leave HTML tags or entities.
- Replace binary images with `[图片说明]` plus Chinese alt text, translated caption, and attribution.
- Do not print `原书第 X 页` or equivalent source-page marker lines.

## EPUB

- EPUB 3.3-compatible ZIP: `mimetype` first and uncompressed; valid `container.xml`, OPF manifest/spine, navigation document, XHTML, CSS, and media resources.
- Set language to `zh-CN`, include cover metadata, a clickable multilevel table of contents, and one XHTML document per chapter or major front/back-matter unit.
- Use stable heading and block IDs. Keep source-page anchors empty and visually silent, for example:

```html
<span epub:type="pagebreak" id="source-page-127" title="127" class="source-page-anchor"></span>
```

- Do not add a visible source-page label or page-list navigation unless the user explicitly requests one.
- Use reflowable HTML tables where possible. Every instructional image needs Chinese alt text and a translated caption or transcription.
- Do not embed a commercial font without explicit permission; use a robust CJK system-font stack.

## Validation

Run:

```bash
python3 scripts/validate_book.py --txt path/to/book.txt --epub path/to/book.epub
epubcheck path/to/book.epub
```

The validator checks UTF-8, visible source-page labels, EPUB container invariants, XML well-formedness, internal links, referenced assets, and silent page anchors. EPUBCheck must finish with zero errors; resolve warnings when they indicate an actual compatibility or accessibility problem.

Also verify chapter, figure, table, exercise, answer, glossary, and index counts against the source manifest. Compare all numeric tokens and inspect every reported difference. Visually inspect chapter openers, sidebars, figures, tables, formulas, and long lists at both narrow and wide viewport sizes.
