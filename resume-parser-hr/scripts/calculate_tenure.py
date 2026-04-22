#!/usr/bin/env python3
"""Tenure, overlap, and month-level date utilities for HR resume parsing."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Dict, List, Optional, Tuple


PRESENT_TOKENS = {"至今", "今", "现在", "目前", "present", "now", "current"}


def parse_date(date_str: str | None, today: Optional[datetime] = None) -> Optional[datetime]:
    """Parse common resume date strings. Missing values return None, not today."""
    if not date_str:
        return None

    raw = str(date_str).strip()
    if not raw:
        return None

    today = today or datetime.now()
    if raw.lower() in PRESENT_TOKENS:
        return datetime(today.year, today.month, 1)

    raw = raw.replace("年", "-").replace("月", "-").replace("日", "")
    raw = raw.replace(".", "-").replace("/", "-").replace("—", "-").replace("–", "-")
    raw = re.sub(r"\s+", "", raw)

    match = re.search(r"(19|20)\d{2}(?:-(\d{1,2}))?(?:-(\d{1,2}))?", raw)
    if not match:
        return None

    year = int(match.group(0)[:4])
    parts = match.group(0).split("-")
    month = int(parts[1]) if len(parts) > 1 and parts[1] else 1
    day = int(parts[2]) if len(parts) > 2 and parts[2] else 1
    if not 1 <= month <= 12:
        return None
    if not 1 <= day <= 31:
        day = 1
    return datetime(year, month, day)


def months_between(start: Optional[datetime], end: Optional[datetime]) -> int:
    """Return month difference. Invalid or reversed ranges return 0 for safe scoring."""
    if not start or not end or start > end:
        return 0
    return max(0, (end.year - start.year) * 12 + (end.month - start.month))


def normalize_date_range(start: str | None, end: str | None) -> Tuple[Optional[datetime], Optional[datetime]]:
    return parse_date(start), parse_date(end)


def calculate_experience_duration(exp: Dict) -> int:
    start, end = normalize_date_range(exp.get("start_date"), exp.get("end_date"))
    return months_between(start, end)


def calculate_tenure(experiences: List[Dict]) -> Dict[str, float]:
    """Calculate formal work, internship, project, freelance, and pending durations."""
    tenure = {
        "full_time_months": 0,
        "internship_months": 0,
        "project_months": 0,
        "freelance_months": 0,
        "pending_months": 0,
    }

    for exp in experiences:
        duration = exp.get("duration_months")
        if duration is None:
            duration = calculate_experience_duration(exp)
            exp["duration_months"] = duration

        if exp.get("overlap_tag") == "重叠经历":
            continue

        exp_type = exp.get("type", "")
        if exp_type == "正式工作":
            tenure["full_time_months"] += duration
        elif exp_type == "实习":
            tenure["internship_months"] += duration
        elif exp_type == "校园项目":
            tenure["project_months"] += duration
        elif exp_type in {"自由职业", "创业", "自由职业/创业"}:
            tenure["freelance_months"] += duration
        else:
            tenure["pending_months"] += duration

    tenure["full_time_years"] = round(tenure["full_time_months"] / 12, 2)
    return tenure


def detect_overlaps(experiences: List[Dict]) -> List[Dict]:
    """Mark overlapping experiences and keep the longest formal/main experience."""
    dated = []
    for index, exp in enumerate(experiences):
        start, end = normalize_date_range(exp.get("start_date"), exp.get("end_date"))
        exp["overlap_tag"] = None
        if start and end:
            exp["duration_months"] = months_between(start, end)
            dated.append((index, exp, start, end))

    dated.sort(key=lambda item: item[2])
    overlap_groups: List[List[Tuple[int, Dict, datetime, datetime]]] = []

    for item in dated:
        placed = False
        for group in overlap_groups:
            if any(not (item[2] >= other[3] or item[3] <= other[2]) for other in group):
                group.append(item)
                placed = True
                break
        if not placed:
            overlap_groups.append([item])

    for group in overlap_groups:
        if len(group) == 1:
            group[0][1]["overlap_tag"] = "主经历"
            continue

        main = max(
            group,
            key=lambda item: (
                item[1].get("type") == "正式工作",
                item[1].get("duration_months", 0),
            ),
        )
        for item in group:
            item[1]["overlap_tag"] = "主经历" if item is main else "重叠经历"

    return experiences


def format_months(months: int | float) -> str:
    months = int(round(months or 0))
    years, rem = divmod(months, 12)
    if years and rem:
        return f"{years}年{rem}个月"
    if years:
        return f"{years}年"
    return f"{rem}个月"


def format_tenure(tenure: Dict[str, int]) -> str:
    parts = [
        f"正式工作：{format_months(tenure.get('full_time_months', 0))}",
        f"实习：{format_months(tenure.get('internship_months', 0))}",
        f"校园项目：{format_months(tenure.get('project_months', 0))}",
    ]
    return "；".join(parts)


if __name__ == "__main__":
    sample = [
        {"type": "正式工作", "company": "A公司", "start_date": "2022.01", "end_date": "2023.03"},
        {"type": "正式工作", "company": "B公司", "start_date": "2023.01", "end_date": "至今"},
        {"type": "实习", "company": "C公司", "start_date": "2021.07", "end_date": "2021.12"},
    ]
    print(format_tenure(calculate_tenure(detect_overlaps(sample))))
