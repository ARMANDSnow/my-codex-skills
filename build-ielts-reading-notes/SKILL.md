---
name: build-ielts-reading-notes
description: Build numbered IELTS reading units in Obsidian from user-pasted English text or articles inspected through the user's authenticated Chrome session. Use for Bloomberg, The Economist, and similar long-form imports that need a clean English note, a Chinese companion translation, full-path links, matched headings and paragraph IDs, selective IELTS Band 7 inline glosses, vocabulary and phrase tables, split-pane CSS, deterministic validation, and Obsidian visual QA.
---

# Build IELTS Reading Notes

Create a clean two-note reading set: English on the left, Chinese on the right. Preserve article hierarchy, keep paragraphs aligned, and make language help useful without overwhelming the page.

## Select the source path

- For user-pasted text, treat the supplied text as authoritative. Preserve its wording and paragraph boundaries unless the user asks for editing.
- For Bloomberg, The Economist, or another page in an existing signed-in Chrome session, use the Chrome control skill. Read [publisher-acquisition.md](references/publisher-acquisition.md) before browsing.
- If only a URL is supplied and authentication is unnecessary, use an appropriate clean extraction tool when available, then verify page hierarchy visually.
- If browser-acquired text is copyrighted, do not reproduce the full article verbatim. Create a clearly labeled English study adaptation with a short compliant excerpt and a source link. A full verbatim English note requires user-provided text.

## Build the article model

Capture title, subtitle, byline, publisher, publication date, canonical URL, section headings, paragraphs, captions, chart sources, and profile metadata. Exclude navigation, promotions, related links, audio controls, comments, and repeated sticky text.

Verify ambiguous structure against the rendered page. Never trust a flat extraction alone for paragraph boundaries or card order.

## Create the paired notes

Read [format-spec.md](references/format-spec.md) and use the templates in `assets/` as scaffolding.

1. Run `python3 scripts/next_unit.py <vault-root> "<中文主题>" "<Publisher>"` to allocate the next three-digit learning number.
2. Create `01-精读文章/NNN - 中文主题 - Publisher/`. Do not include the publication date in folder or file names; keep it only in frontmatter.
3. Use the fixed filenames `01 英文原文.md` and `02 中文翻译.md` inside the unit.
4. Use full vault-relative wikilinks between the two notes and from the study home because filenames repeat across units.
5. Reproduce the same heading depth and order in both notes.
6. Keep one source paragraph per Markdown paragraph and one translation paragraph opposite it.
7. Add matching hidden block IDs `^p01`, `^p02`, ... to every aligned content paragraph, including meaningful captions and sources.
8. Keep company profiles, captions, and notes expanded as normal Markdown. Do not use folding callouts or reading-tip cards.
9. Translate for meaning while retaining paragraph scope, factual qualifiers, names, figures, and causal logic.

## Add Band 7 language support

Annotate only expressions likely to slow a learner around IELTS Band 7:

- Prefer C1 vocabulary, reporting collocations, phrasal verbs with non-literal meanings, idioms, and topic-specific terms.
- Skip common B2 words and expressions made obvious by context.
- Use `**English expression**（简明中文义）` at first useful occurrence.
- Aim for zero to three annotations per substantive paragraph and normally no more than two.
- Never add annotations to the Chinese note.

After the last aligned paragraph, add `## Key Vocabulary & Phrases`, then:

- `### Key Vocabulary`: normally 15–25 high-value words.
- `### Key Phrases`: normally 15–25 transferable phrases.
- Use three-column Markdown tables: item, Chinese meaning, and context/usage explanation.
- Keep tables after all paragraph IDs so they do not disturb alignment.

## Apply vault styling

Use the `parallel-reading` CSS class in both notes. If the vault lacks a compatible snippet, copy `assets/parallel-reading.css` into `.obsidian/snippets/parallel-reading.css` and enable it. If a snippet already exists, merge only the missing rules; do not overwrite unrelated user styling.

## Validate and inspect

Run:

```bash
python3 scripts/validate_pair.py <english-note.md> <chinese-note.md>
```

Fix every error. Treat warnings as review prompts.

Then open the two notes side by side in Obsidian Reading view. Check top alignment, heading hierarchy, paragraph spacing, gloss density, table wrapping, and the absence of accidental cards or unrelated page text. Use Obsidian CLI when available; otherwise use local app control for a read-only visual inspection.

When `00-学习首页/IELTS 精读首页.md` exists, add the numbered unit and both full-path links without duplicating entries. Report the source mode, unit number, created files, paragraph count, annotation count, glossary counts, and validation result.
