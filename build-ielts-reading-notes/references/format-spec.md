# Paired note format

## English frontmatter

```yaml
---
title: "{{ENGLISH_TITLE}}"
source: "{{PUBLISHER}}"
published: "{{YYYY-MM-DD}}"
language: en
unit: "{{NNN}}"
topic: "{{CHINESE_TOPIC}}"
translation: "[[01-精读文章/{{NNN}} - {{CHINESE_TOPIC}} - {{PUBLISHER}}/02 中文翻译]]"
source_url: "{{URL}}"
tags:
  - IELTS/阅读
  - 文章精读
cssclasses:
  - parallel-reading
---
```

Add `content_mode: study-adaptation` when the text came only from a copyrighted webpage and is paraphrased. Omit it for user-provided verbatim text.

## Chinese frontmatter

```yaml
---
title: "{{CHINESE_TITLE}}"
source: "{{PUBLISHER}}"
published: "{{YYYY-MM-DD}}"
language: zh-CN
unit: "{{NNN}}"
topic: "{{CHINESE_TOPIC}}"
original: "[[01-精读文章/{{NNN}} - {{CHINESE_TOPIC}} - {{PUBLISHER}}/01 英文原文]]"
source_url: "{{URL}}"
tags:
  - IELTS/阅读
  - 中文翻译
cssclasses:
  - parallel-reading
---
```

## Body contract

- Store the pair in `01-精读文章/NNN - 中文主题 - Publisher/` as `01 英文原文.md` and `02 中文翻译.md`.
- Allocate `NNN` from the largest existing three-digit learning-unit number plus one. Dates do not belong in paths.
- Use full vault-relative wikilinks because the two fixed filenames repeat in every unit.
- Use one H1 title.
- Put subtitle, byline/date, and external source link directly below the title.
- Use H2 for article sections and H3 for profiles or named subsections.
- Use identical heading-level sequences in both notes; heading text may be translated.
- Preserve one blank line between structural blocks and paragraphs.
- End each aligned paragraph with a unique sequential ID: `^p01`, `^p02`, ...
- Count meaningful chart captions and source notes as aligned paragraphs when included.
- Put language tables after a horizontal rule and after the final aligned ID.
- End with `[[00-学习首页/IELTS 精读首页|...]]` when that study home exists.

## Annotation contract

Correct:

```markdown
Demand is expected to **outstrip**（超过） supply, resulting in a **shortfall**（缺口）. ^p08
```

Avoid fragmented emphasis:

```markdown
**swap** diesel buses **for** electric ones（替换）
```

Prefer:

```markdown
**swap diesel buses for electric ones**（把柴油公交换成电动公交）
```

Keep annotations short. Put nuance, collocations, grammar, and reusable examples in the tables.

## Table contract

```markdown
## Key Vocabulary & Phrases

### Key Vocabulary

| Word | 中文释义 | 原文语境与用法 |
| --- | --- | --- |
| outstrip | v. 超过；超越 | *demand outstrips supply*：经济类文章常见搭配。 |

### Key Phrases

| Phrase | 中文释义 | 用法讲解 |
| --- | --- | --- |
| on track to do | 按目前趋势将会…… | 表示照当前进度很可能实现。 |
```

## Structural exclusions

Do not include foldable callouts, reading tips, language lectures between source paragraphs, navigation labels, newsletter prompts, related-story cards, or unverified fragments from flat extraction.
