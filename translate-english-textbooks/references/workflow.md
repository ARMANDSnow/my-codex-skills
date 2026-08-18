# Translation Workflow

## 1. Source Audit

Record the PDF filename, checksum, physical page count, printed-page mapping, language, text-layer quality, chapter starts, front/back matter, and image count. Compare `pdftotext -layout` with `pdftotext -raw`; render representative pages with `pdftoppm` to verify reading order and detect text embedded only in images.

Use the printed table of contents as the primary chapter manifest, then confirm each boundary against rendered pages. Do not assign chapters until the manifest is stable.

## 2. Structured Extraction

Represent source content as ordered blocks with stable IDs, for example `ch03-s02-b014`. Record content type (`heading`, `paragraph`, `definition`, `figure`, `table`, `exercise`, `answer`, `citation`) and source-page number separately from visible text.

Normalize line-wrap hyphenation only when the joined spelling is certain. Preserve intentional hyphens, symbols, superscripts, formulas, and list numbering. Remove running heads and production marks only after confirming they are repeated non-content.

## 3. Sample-First Gate

For a full textbook, choose the first substantive chapter unless it is unusually short or lacks normal textbook features. The main agent translates and packages this chapter without subagents. The sample must exercise representative headings, definitions, figures or tables, exercises, and answer formatting when those appear in the book.

Ask the user to review terminology, prose register, English-term retention, figures, tables, TXT readability, and EPUB layout. Apply feedback to the sample, then record the approved decisions in a project termbase and style sheet. Do not start parallel chapter translation before explicit approval.

## 4. Translation and Review

Freeze a termbase containing the English term, approved Chinese term, permitted variants, first-use rule, and notes. Give each translator only disjoint chapters or contiguous chapter segments, the source blocks, relevant rendered pages, and the frozen termbase.

Require every translated block to retain its source block ID. A reviewer who did not translate the block checks:

- omissions, additions, and changed logical relationships;
- terminology and proper names;
- numbers, currencies, percentages, years, units, formulas, and variables;
- heading hierarchy, captions, cross-references, questions, choices, and answers;
- image labels or table cells not present in the extracted text.

The coordinating agent resolves reviewer findings and runs a global consistency pass. Never merge simultaneous edits into the same chapter file.

## 5. Figures and Tables

Prefer images rendered or converted to RGB so EPUB readers do not invert CMYK assets. Crop only the informative region and preserve attribution. Decorative backgrounds may be omitted; instructional diagrams, charts, photographs, and cartoons must be inventoried.

When labels remain in English inside a figure, provide Chinese alt text and a nearby label/value transcription sufficient to understand the figure. Do not claim a full graphical translation if labels were not redrawn.

## 6. Failure Handling

- If reading order differs between extraction modes, use coordinates and page renders to reconstruct the source before translation.
- If OCR uncertainty changes meaning, mark the block unresolved and inspect the page image; do not guess.
- If a formula cannot be represented reliably in reflowable text, preserve a sharp image and add a text transcription.
- If an index depends on source pages, retain hidden source-page anchors and link translated index entries to them without printing page labels in the body.
