#!/usr/bin/env python3
"""Batch screen resumes against a target JD and output an HR review table."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from .parse_resume import extract_text, parse_resume_text
    from .recommendation_engine import DEGREE_ORDER, parse_jd, related_experiences
except ImportError:
    from parse_resume import extract_text, parse_resume_text
    from recommendation_engine import DEGREE_ORDER, parse_jd, related_experiences


SUPPORTED_RESUME_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DEFAULT_WEIGHTS = {
    "relevant_experience": 0.35,
    "skill_keyword": 0.25,
    "education": 0.15,
    "stability_gap": 0.15,
    "parsing_confidence": 0.10,
}
RESULT_ORDER = {"强推荐": 0, "待审核": 1, "暂不推荐": 2}


def load_text_or_path(value: str) -> str:
    try:
        path = Path(value)
        if "\n" not in value and len(value) < 512 and path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        pass
    return value


def iter_resume_files(resume_dir: Path) -> Iterable[Path]:
    for path in sorted(resume_dir.iterdir()):
        if path.is_file():
            yield path


def _dimension_for_text(text: str) -> Optional[str]:
    lowered = text.lower()
    if any(token in text for token in ["相关经验", "工作经验", "经验"]):
        return "relevant_experience"
    if any(token in text for token in ["技能", "关键词", "关键字", "命中"]):
        return "skill_keyword"
    if "学历" in text or "教育" in text:
        return "education"
    if any(token in text for token in ["稳定", "gap", "Gap", "履历"]):
        return "stability_gap"
    if any(token in text for token in ["解析", "置信", "完整度"]):
        return "parsing_confidence"
    if any(token in lowered for token in ["confidence", "parsing"]):
        return "parsing_confidence"
    return None


def _number_from_text(text: str) -> Optional[float]:
    percent = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if percent:
        return float(percent.group(1)) / 100
    number = re.search(r"(?<!\d)(0?\.\d+|1(?:\.0+)?|\d+(?:\.\d+)?)(?!\d)", text)
    if not number:
        return None
    value = float(number.group(1))
    if value > 1:
        value = value / 100
    return value


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    merged = dict(DEFAULT_WEIGHTS)
    merged.update({key: value for key, value in weights.items() if key in DEFAULT_WEIGHTS and value >= 0})
    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {key: round(value / total, 4) for key, value in merged.items()}


def _weights_from_lines(lines: Iterable[str]) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for line in lines:
        text = " ".join(str(part) for part in re.split(r"[\t,，|]", line) if str(part).strip())
        dimension = _dimension_for_text(text)
        value = _number_from_text(text)
        if dimension and value is not None:
            weights[dimension] = value
    return weights


def load_weights(path: str | None) -> Tuple[Dict[str, float], List[str]]:
    warnings: List[str] = []
    if not path:
        return dict(DEFAULT_WEIGHTS), warnings

    file_path = Path(path)
    if not file_path.exists():
        warnings.append(f"权重文件不存在：{path}，已使用默认权重")
        return dict(DEFAULT_WEIGHTS), warnings

    try:
        suffix = file_path.suffix.lower()
        if suffix == ".xlsx":
            try:
                import openpyxl
            except ImportError as exc:
                raise RuntimeError("需要安装 openpyxl 才能解析 .xlsx 权重") from exc
            workbook = openpyxl.load_workbook(str(file_path), data_only=True)
            lines = []
            for sheet in workbook.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    lines.append(" ".join("" if value is None else str(value) for value in row))
            return _normalize_weights(_weights_from_lines(lines)), warnings
        if suffix == ".docx":
            try:
                from docx import Document
            except ImportError as exc:
                raise RuntimeError("需要安装 python-docx 才能解析 .docx 权重") from exc
            doc = Document(str(file_path))
            lines = [paragraph.text for paragraph in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    lines.append(" ".join(cell.text for cell in row.cells))
            return _normalize_weights(_weights_from_lines(lines)), warnings
        warnings.append(f"暂不支持权重文件类型：{suffix}，已使用默认权重")
    except Exception as exc:  # noqa: BLE001 - keep batch screening resilient.
        warnings.append(f"权重文件解析失败：{exc}；已使用默认权重")
    return dict(DEFAULT_WEIGHTS), warnings


def highest_degree(candidate: Dict) -> str:
    education = candidate.get("education", [])
    if not education:
        return "未解析"
    degrees = [edu.get("degree") for edu in education if edu.get("degree")]
    if not degrees:
        return "未解析"
    return max(degrees, key=lambda degree: DEGREE_ORDER.get(degree, 0))


def education_score(candidate: Dict, jd: Dict) -> float:
    required = DEGREE_ORDER.get(jd.get("min_degree") or "不限", 0)
    if required <= 0:
        return 1.0
    candidate_level = max((DEGREE_ORDER.get(edu.get("degree", ""), 0) for edu in candidate.get("education", [])), default=0)
    return 1.0 if candidate_level >= required else 0.0


def relevant_experience_months(candidate: Dict, job_title: str) -> int:
    return sum(
        exp.get("duration_months", 0) or 0
        for exp in related_experiences(candidate, job_title)
        if exp.get("credibility_score", 0) >= 0.4 and exp.get("type") in {"正式工作", "实习"}
    )


def keyword_hits(candidate: Dict, jd: Dict) -> List[str]:
    jd_skills = jd.get("skills", []) or []
    text_parts = []
    for exp in candidate.get("experiences", []):
        text_parts.extend([
            exp.get("job_title", ""),
            exp.get("standardized_job_title", ""),
            exp.get("description", ""),
        ])
    text = "\n".join(part for part in text_parts if part)
    hits = [skill for skill in jd_skills if skill and skill.lower() in text.lower()]
    if not hits:
        for token in ["销售", "客户", "沟通", "成交", "回款", "外呼", "渠道", "BD", "客服"]:
            if token.lower() in text.lower():
                hits.append(token)
    return sorted(set(hits))


def stability_gap_score(candidate: Dict) -> float:
    stability = candidate.get("stability_scores", {})
    stability_score = float(stability.get("stability_score") or 0) / 100
    gap_score = float(stability.get("gap_score") or 0) / 100
    return max(0.0, min(1.0, (stability_score + gap_score) / 2))


def calculate_match_score(candidate: Dict, jd: Dict, job_title: str, weights: Dict[str, float]) -> float:
    min_months = jd.get("min_experience_months") or 6
    relevant_months = relevant_experience_months(candidate, job_title)
    experience_score = min(relevant_months / max(min_months, 1), 1.0)
    skills = jd.get("skills", []) or []
    hits = keyword_hits(candidate, jd)
    if skills:
        skill_score = min(len(hits) / len(skills), 1.0)
    else:
        skill_score = min(len(hits) / 4, 1.0)
    score = (
        weights["relevant_experience"] * experience_score
        + weights["skill_keyword"] * skill_score
        + weights["education"] * education_score(candidate, jd)
        + weights["stability_gap"] * stability_gap_score(candidate)
        + weights["parsing_confidence"] * float(candidate.get("parsing_confidence") or 0)
    )
    return round(max(0.0, min(1.0, score)) * 100, 1)


def review_reasons(candidate: Dict) -> List[str]:
    reasons = []
    if candidate.get("parsing_confidence", 0) < 0.6:
        reasons.append("解析置信度低")
    for item in candidate.get("anomalies", []):
        level = item.get("level")
        if level in {"P0", "P1"} or "不参与评分" in item.get("action", ""):
            reasons.append(f"{item.get('type')}：{item.get('description')}")
    return reasons[:4]


def mismatch_items(candidate: Dict) -> List[str]:
    recommendation = candidate.get("recommendation", {})
    details = recommendation.get("details", {})
    items = list(details.get("unmet_strong_criteria", []))
    items.extend(details.get("downgrade_factors", []))
    return items[:4]


def short_comment(candidate: Dict, hits: List[str], mismatches: List[str]) -> str:
    result = candidate.get("recommendation", {}).get("result", "待审核")
    hit_text = "、".join(hits[:3]) if hits else "命中点较少"
    risk_text = "；" + mismatches[0] if mismatches else ""
    comment = f"{result}：{hit_text}{risk_text}"
    return comment[:50]


def row_from_candidate(path: Path, candidate: Dict, jd: Dict, job_title: str, weights: Dict[str, float]) -> Dict:
    recommendation = candidate.get("recommendation", {})
    if candidate.get("parsing_confidence", 0) < 0.6 and recommendation.get("result") == "强推荐":
        recommendation = dict(recommendation)
        recommendation["result"] = "待审核"
        recommendation["reason"] = (recommendation.get("reason", "") + "；解析置信度低，需人工复核").strip("；")
        candidate["recommendation"] = recommendation

    hits = keyword_hits(candidate, jd)
    mismatches = mismatch_items(candidate)
    reasons = review_reasons(candidate)
    row = {
        "source_file": path.name,
        "candidate": candidate.get("basic_info", {}).get("name") or path.stem,
        "recommendation": recommendation.get("result", "待审核"),
        "match_score": calculate_match_score(candidate, jd, job_title, weights),
        "recommendation_score": recommendation.get("score", 0),
        "parsing_confidence": candidate.get("parsing_confidence", 0),
        "education": highest_degree(candidate),
        "relevant_experience_months": relevant_experience_months(candidate, job_title),
        "keyword_hits": "、".join(hits) if hits else "-",
        "mismatch_items": "；".join(mismatches) if mismatches else "-",
        "review_reasons": "；".join(reasons) if reasons else "-",
        "comment": short_comment(candidate, hits, mismatches),
        "candidate_card": candidate,
    }
    return row


def unparsed_row(path: Path, reason: str) -> Dict:
    return {
        "source_file": path.name,
        "candidate": path.stem,
        "recommendation": "待审核",
        "match_score": 0.0,
        "recommendation_score": 0,
        "parsing_confidence": 0,
        "education": "未解析",
        "relevant_experience_months": 0,
        "keyword_hits": "-",
        "mismatch_items": "-",
        "review_reasons": reason,
        "comment": "待审核：文件未完成解析，需人工处理",
        "candidate_card": None,
    }


def sort_rows(rows: List[Dict]) -> List[Dict]:
    return sorted(
        rows,
        key=lambda row: (
            RESULT_ORDER.get(row.get("recommendation"), 9),
            -float(row.get("recommendation_score") or 0),
            -float(row.get("match_score") or 0),
        ),
    )


DISPLAY_FIELDS = [
    "candidate",
    "recommendation",
    "match_score",
    "parsing_confidence",
    "education",
    "relevant_experience_months",
    "keyword_hits",
    "mismatch_items",
    "review_reasons",
    "comment",
]
FIELD_LABELS = {
    "candidate": "候选人",
    "recommendation": "推荐",
    "match_score": "匹配分",
    "parsing_confidence": "解析置信度",
    "education": "学历",
    "relevant_experience_months": "相关经验月数",
    "keyword_hits": "命中关键词",
    "mismatch_items": "不匹配项",
    "review_reasons": "人工复核原因",
    "comment": "评语",
}


def markdown_table(rows: List[Dict], warnings: List[str]) -> str:
    lines: List[str] = []
    if warnings:
        lines.append("\n".join(f"> 警告：{warning}" for warning in warnings))
        lines.append("")
    header = [FIELD_LABELS[field] for field in DISPLAY_FIELDS]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows:
        values = [str(row.get(field, "-")).replace("\n", " ").replace("|", "/") for field in DISPLAY_FIELDS]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_output(rows: List[Dict], output: str | None, warnings: List[str]) -> None:
    if not output:
        print(markdown_table(rows, warnings))
        return

    path = Path(output)
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = {"warnings": warnings, "rows": rows}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    if suffix == ".csv":
        with path.open("w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=DISPLAY_FIELDS)
            writer.writerow({field: FIELD_LABELS[field] for field in DISPLAY_FIELDS})
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in DISPLAY_FIELDS})
        return
    path.write_text(markdown_table(rows, warnings), encoding="utf-8")


def run_batch(resume_dir: Path, jd_text: str, job_title: str, weights: Dict[str, float]) -> List[Dict]:
    jd = parse_jd(jd_text)
    effective_job_title = job_title or jd.get("job_title") or "销售"
    rows: List[Dict] = []
    files = list(iter_resume_files(resume_dir))
    if not files:
        raise RuntimeError(f"简历目录为空：{resume_dir}")

    for path in files:
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            rows.append(unparsed_row(path, "图片简历需 OCR/人工处理"))
            continue
        if suffix not in SUPPORTED_RESUME_SUFFIXES:
            rows.append(unparsed_row(path, f"暂不支持文件类型：{suffix}"))
            continue
        try:
            text = extract_text(str(path))
            candidate = parse_resume_text(text, jd_text=jd_text, job_title=effective_job_title)
            rows.append(row_from_candidate(path, candidate, jd, effective_job_title, weights))
        except Exception as exc:  # noqa: BLE001 - one bad resume must not stop the batch.
            rows.append(unparsed_row(path, f"解析失败：{exc}"))
    return sort_rows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch screen resumes against a target JD.")
    parser.add_argument("resume_dir", help="Directory containing resumes")
    parser.add_argument("--jd", required=True, help="JD text or path to a JD text file")
    parser.add_argument("--job-title", default="", help="Target job title")
    parser.add_argument("--weights", default="", help="Optional .docx/.xlsx weighting file")
    parser.add_argument("--output", default="", help="Optional .md/.csv/.json output path")
    args = parser.parse_args()

    resume_dir = Path(args.resume_dir)
    if not resume_dir.exists() or not resume_dir.is_dir():
        raise SystemExit(f"简历目录不存在或不是目录：{resume_dir}")
    jd_text = load_text_or_path(args.jd)
    if not jd_text.strip():
        raise SystemExit("JD 不能为空：请通过 --jd 提供 JD 文件路径或文本")
    weights, warnings = load_weights(args.weights)
    for warning in warnings:
        print(f"警告：{warning}", file=sys.stderr)
    try:
        rows = run_batch(resume_dir, jd_text, args.job_title, weights)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    write_output(rows, args.output or None, warnings)


if __name__ == "__main__":
    main()
