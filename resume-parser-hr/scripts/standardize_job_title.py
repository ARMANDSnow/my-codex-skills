#!/usr/bin/env python3
"""Job-title normalization and similarity rules for HR screening."""

from __future__ import annotations

from typing import Dict, List, Tuple


JOB_SYNONYMS: Dict[str, str] = {
    "电话销售": "电话销售",
    "电销": "电话销售",
    "telesales": "电话销售",
    "电话销售专员": "电话销售",
    "电话营销": "电话销售",
    "外呼销售": "电话销售",
    "销售代表": "销售",
    "销售专员": "销售",
    "销售顾问": "销售",
    "销售经理": "销售",
    "业务员": "销售",
    "业务代表": "销售",
    "面销": "面销",
    "门店销售": "面销",
    "导购": "面销",
    "大客户销售": "大客户销售",
    "客户经理": "大客户销售",
    "ka销售": "大客户销售",
    "渠道销售": "渠道销售",
    "渠道经理": "渠道销售",
    "招商专员": "渠道销售",
    "bd": "商务拓展",
    "商务拓展": "商务拓展",
    "商务经理": "商务拓展",
    "客服专员": "客服",
    "客户支持": "客服",
    "售后客服": "客服",
    "客服代表": "客服",
    "客户服务": "客服",
    "招聘专员": "招聘",
    "talent acquisition": "招聘",
    "ta": "招聘",
    "招聘顾问": "招聘",
    "行政专员": "行政",
    "办公室助理": "行政",
    "行政助理": "行政",
    "办公室文员": "行政",
    "市场营销": "市场营销",
    "市场专员": "市场营销",
    "市场推广": "市场营销",
    "运营专员": "运营",
    "用户运营": "运营",
    "软件工程师": "软件工程师",
    "软件开发工程师": "软件工程师",
    "产品经理": "产品经理",
    "数据分析师": "数据分析师",
}

SALES_TITLES = {"销售", "电话销售", "面销", "大客户销售", "渠道销售", "商务拓展"}

JOB_SIMILARITY: Dict[str, Dict[str, float]] = {
    "电话销售": {"销售": 0.9, "面销": 0.7, "客服": 0.55, "商务拓展": 0.55, "市场营销": 0.35},
    "面销": {"销售": 0.9, "电话销售": 0.7, "客服": 0.45},
    "大客户销售": {"销售": 0.9, "商务拓展": 0.75, "渠道销售": 0.65, "客服": 0.4},
    "渠道销售": {"销售": 0.85, "商务拓展": 0.75, "大客户销售": 0.65, "市场营销": 0.5},
    "商务拓展": {"销售": 0.75, "渠道销售": 0.75, "大客户销售": 0.75, "市场营销": 0.55},
    "客服": {"销售": 0.5, "电话销售": 0.55, "运营": 0.35},
    "市场营销": {"销售": 0.6, "渠道销售": 0.5, "运营": 0.5},
    "行政": {"销售": 0.25, "招聘": 0.4, "运营": 0.3},
    "招聘": {"销售": 0.35, "客服": 0.35},
}


def clean_title(raw_title: str | None) -> str:
    return (raw_title or "").strip().lower().replace(" ", "")


def standardize_job_title(raw_title: str | None) -> str:
    if not raw_title:
        return ""
    cleaned = clean_title(raw_title)
    if cleaned in JOB_SYNONYMS:
        return JOB_SYNONYMS[cleaned]
    for key, standard in JOB_SYNONYMS.items():
        key_clean = clean_title(key)
        if key_clean and (key_clean in cleaned or cleaned in key_clean):
            return standard
    if "销售" in raw_title:
        return "销售"
    if "客服" in raw_title or "客户服务" in raw_title:
        return "客服"
    if "行政" in raw_title or "文员" in raw_title:
        return "行政"
    return raw_title.strip()


def get_job_similarity(job1: str | None, job2: str | None) -> float:
    j1 = standardize_job_title(job1)
    j2 = standardize_job_title(job2)
    if not j1 or not j2:
        return 0.0
    if j1 == j2:
        return 1.0
    if j1 in SALES_TITLES and j2 in SALES_TITLES:
        return 0.8
    if j1 in JOB_SIMILARITY and j2 in JOB_SIMILARITY[j1]:
        return JOB_SIMILARITY[j1][j2]
    if j2 in JOB_SIMILARITY and j1 in JOB_SIMILARITY[j2]:
        return JOB_SIMILARITY[j2][j1]
    return 0.0


def is_sales_related(title: str | None, threshold: float = 0.5) -> bool:
    return get_job_similarity(title, "销售") >= threshold


def extract_job_keywords(title: str | None) -> List[str]:
    title = title or ""
    keywords = ["销售", "电销", "面销", "客户", "渠道", "招商", "商务", "客服", "行政", "招聘", "运营", "市场"]
    return [kw for kw in keywords if kw.lower() in title.lower()]


def fuzzy_match_job_title(raw_title: str, target_titles: List[str]) -> Tuple[str, float]:
    standardized = standardize_job_title(raw_title)
    best_match, best_score = standardized, 0.0
    for target in target_titles:
        score = get_job_similarity(standardized, target)
        if score > best_score:
            best_match, best_score = target, score
    return best_match, best_score


def load_synonyms_from_file(filepath: str) -> Dict[str, str]:
    return JOB_SYNONYMS


if __name__ == "__main__":
    for title in ["电销", "KA销售", "客服专员", "办公室助理"]:
        print(title, "=>", standardize_job_title(title), get_job_similarity(title, "销售"))
