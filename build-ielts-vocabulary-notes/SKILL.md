---
name: build-ielts-vocabulary-notes
description: Build or revise Obsidian IELTS vocabulary-review notes from word-book photos, pasted word lists, or an existing chapter note. Use when the user wants to extract a chapter, remove mastered words, create independent vocabulary cards, add detailed explanations for high-value IELTS words, compare near-synonyms, mark key cards in the outline, or maintain the vocabulary-review index.
---

# Build IELTS Vocabulary Notes

Create concise, high-yield chapter notes for a learner around IELTS Band 7.5. Preserve the word book's useful core, but make the resulting note easier to review, recognize in reading, and use in speaking and writing.

## Establish the source and scope

1. Read the vault's `AGENTS.md` and inspect the existing vocabulary note and home page before editing.
2. For word-book photos, visually verify the page order and extract every headword in source order. Do not treat example words or bolded collocations as headwords.
3. First give the user a numbered, page-grouped list and wait for their mastered-word exclusions. Retain any prior exclusions the user confirms.
4. Do not create an independent card for an excluded word. Mention it only when essential to a concise comparison.
5. For an existing note, preserve user-approved word selection, headings, frontmatter, and user content unless the request explicitly changes them.

## Build the chapter note

- Store chapter notes directly under `02-词汇复习/` with the fixed pattern `NN 第N章词汇.md`; do not create a chapter subfolder.
- Use frontmatter with `title`, `date`, `tags`, `status`, `source`, `retained_words`, `excluded_words`, and `cssclasses: [ielts-vocabulary-note]`.
- Organize by the chapter's semantic progression. Use a `###` group only for true near-synonyms or a tightly connected contrast; otherwise, keep individual cards separate with blank lines.
- Update `00-学习首页/IELTS 精读首页.md` with one full vault-relative wikilink under `## 词汇复习`. Never duplicate or leave stale links after a move.

## Write cards at two information levels

### Standard card

Use for specialist, low-yield, or already-transparent words:

```markdown
**marble /ˈmɑːrbl/ 大理石；弹珠**
常见：`a marble floor/statue` 大理石地板／雕像。
```

- Put the headword, US IPA, and direct Chinese meaning on the first line.
- Put usage, a short restriction, or a high-value collocation on the next line.
- Do not write filler such as “意为”, “这是错误写法”, “辨认即可”, or “专业语境辨认即可”. State only the useful correct form.

### Detailed key card

Use for words with transferable collocations, multiple useful senses, a meaningful register difference, a useful word family, or a recurring IELTS topic. Make the card an H4 heading so it appears in the Obsidian outline.

```markdown
#### ⭐️ jeopardize /ˈdʒepərdaɪz/ 危及；损害
指使某事面临失败、失去或受损的风险，常用于机会、计划、事业和关系。
*The scandal could jeopardize his political career.*
这起丑闻可能危及他的政治生涯。
常见用法：

- `jeopardize one’s chances/prospects` 危及机会／前景
- `jeopardize negotiations` 使谈判面临失败
- `jeopardize national security` 危及国家安全

和 **endanger** 相比：**endanger** 多用于生命、健康、物种等实际危险；**jeopardize** 多用于计划、机会、事业和关系等可能受损或失败。
```

For every detailed card:

1. Give the semantic boundary or register in one concise sentence.
2. Add one natural, transferable English example and its Chinese translation.
3. Add two to five collocations or fixed patterns.
4. Add a comparison or word-family note only when it changes accurate usage.

Mark only genuinely high-value words with `#### ⭐️`. The star must be part of the heading text so it is visible both in the note body and the right outline. Keep specialist nouns and simple concrete words as standard cards; do not inflate every retained word into a long entry.

## Language and style rules

- Use American spelling consistently in headwords, explanations, examples, and collocations: e.g. `jeopardize`, `vapor`, `meters`, `harbor`, `behavior`, `fibers`.
- Preserve the original book's core meanings and valuable collocations. Replace low-information or unnatural examples with clear, natural examples when useful.
- Use concise Chinese; prioritize semantic boundary, collocation, and active-use value over dictionary-style sense lists.
- Keep punctuation, heading depth, IPA formatting, and blank-line rhythm consistent across the note.
- Do not expose private source images or user data outside the vault.

## Validate and visually inspect

1. Check that every retained word appears and every excluded word lacks an independent card.
2. Confirm every `#### ⭐️` card has a semantic note, example plus translation, and a `常见用法：` list.
3. Search for stale source paths and update all affected full-path wikilinks after renames or moves.
4. Search for forbidden filler and British spellings when the user requested US forms.
5. Open the note in Obsidian Reading view. Check card spacing, heading hierarchy, list wrapping, the ⭐️ entries in the right outline, and the home-page link.
6. Report the note path, retained/excluded counts, number of detailed ⭐️ cards, and the validation outcome.
