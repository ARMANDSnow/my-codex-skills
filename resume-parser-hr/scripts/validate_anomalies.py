#!/usr/bin/env python3
"""Anomaly validation, credibility scoring, stability, and gap scoring."""

from __future__ import annotations

from datetime import datetime
import statistics
import re
from typing import Dict, List, Optional, Tuple

try:
    from .calculate_tenure import calculate_tenure, detect_overlaps, months_between, parse_date
    from .standardize_job_title import get_job_similarity
except ImportError:
    from calculate_tenure import calculate_tenure, detect_overlaps, months_between, parse_date
    from standardize_job_title import get_job_similarity


PERFORMANCE_RE = re.compile(r"(\d+(\.\d+)?\s*(%|万|k|K|单|个|人|家|通|元|次))|转化|成交|销售额|业绩|达成率|回款|排名|top", re.I)
CUSTOMER_RE = re.compile(r"客户|用户|企业|商家|门店|会员|B端|C端|ka|KA|大客户|渠道|代理商")
GAP_REASON_RE = re.compile(r"备考|考研|考公|学习|培训|进修|创业|自由职业|项目|照顾家庭|生育|病假|休养|搬家|gap", re.I)

# 统一的「提醒但不影响评分」动作前缀。recommendation_engine 与 batch_screen_resumes
# 都靠子串「不参与评分」把这类项排除出打分、并归入「人工复核」区，务必保留该四字。
NO_SCORE_ACTION_PREFIX = "人工复核提示（不参与评分）"


def anomaly(anomaly_type: str, level: str, description: str, action: str = "人工复核") -> Dict:
    return {"type": anomaly_type, "level": level, "description": description, "action": action}


def calculate_experience_credibility(exp: Dict) -> float:
    desc = exp.get("description", "") or ""
    score = 0.0
    if exp.get("job_title") or exp.get("standardized_job_title"):
        score += 0.2
    if len(desc.strip()) >= 10:
        score += 0.3
    if PERFORMANCE_RE.search(desc):
        score += 0.3
    if CUSTOMER_RE.search(desc):
        score += 0.1
    if exp.get("start_date") and exp.get("end_date") and exp.get("duration_months", 0) > 0:
        score += 0.1
    return round(min(score, 1.0), 2)


def enrich_experience_scores(experiences: List[Dict]) -> None:
    for exp in experiences:
        if "credibility_score" not in exp:
            exp["credibility_score"] = calculate_experience_credibility(exp)
        score = exp.get("credibility_score", 0)
        if score >= 0.7:
            exp["credibility_level"] = "高可信"
        elif score >= 0.4:
            exp["credibility_level"] = "中可信"
        else:
            exp["credibility_level"] = "低可信"


def validate_age_tenure(age: Optional[int], full_time_months: int) -> List[Dict]:
    if not age:
        return []
    years = full_time_months / 12
    items = []
    if age <= 23 and years > 4:
        items.append(anomaly("履历时间线提示", "P2", f"候选人自述年龄{age}岁，正式工龄{years:.1f}年，需核验教育和工作时间线", NO_SCORE_ACTION_PREFIX))
    if age <= 25 and years > 6:
        items.append(anomaly("履历时间线提示", "P2", f"候选人自述年龄{age}岁，正式工龄{years:.1f}年，明显偏高，需人工核验", NO_SCORE_ACTION_PREFIX))
    if age <= 28 and years > 8:
        items.append(anomaly("履历时间线提示", "P2", f"候选人自述年龄{age}岁，正式工龄{years:.1f}年，需核验起始工作时间", NO_SCORE_ACTION_PREFIX))
    if age <= 35 and years > 15:
        items.append(anomaly("履历时间线提示", "P2", f"候选人自述年龄{age}岁，正式工龄{years:.1f}年，请核验教育和工作时间线", NO_SCORE_ACTION_PREFIX))
    return items


def validate_work_start_age(experiences: List[Dict], age: Optional[int]) -> List[Dict]:
    if not age:
        return []
    birth_year = datetime.now().year - age
    items = []
    for exp in experiences:
        if exp.get("type") != "正式工作":
            continue
        start = parse_date(exp.get("start_date"))
        if start and start.year - birth_year < 16:
            items.append(anomaly("工龄开始时间提示", "P2", f"按候选人自述年龄推算，{exp.get('company', '未知公司')}开始工作时约{start.year - birth_year}岁，需核验", NO_SCORE_ACTION_PREFIX))
    return items


def validate_time_ranges(experiences: List[Dict]) -> List[Dict]:
    items = []
    for exp in experiences:
        start = parse_date(exp.get("start_date"))
        end = parse_date(exp.get("end_date"))
        if exp.get("start_date") and exp.get("end_date") and (not start or not end):
            items.append(anomaly("时间格式异常", "P2", f"{exp.get('company', '未知公司')}的起止时间无法解析", "补充时间"))
        elif start and end and start > end:
            items.append(anomaly("时间倒置异常", "P0", f"{exp.get('company', '未知公司')}开始时间晚于结束时间", "强制复核"))
        elif not exp.get("start_date") or not exp.get("end_date"):
            items.append(anomaly("时间缺失", "P2", f"{exp.get('company', '未知公司')}缺少起止时间", "补充时间"))
    return items


def validate_overlaps(experiences: List[Dict]) -> List[Dict]:
    items = []
    dated: List[Tuple[Dict, datetime, datetime]] = []
    for exp in experiences:
        start = parse_date(exp.get("start_date"))
        end = parse_date(exp.get("end_date"))
        if start and end and start <= end:
            dated.append((exp, start, end))

    for i in range(len(dated)):
        group = [dated[i]]
        for j in range(i + 1, len(dated)):
            if not (dated[i][2] <= dated[j][1] or dated[j][2] <= dated[i][1]):
                group.append(dated[j])
        if len(group) < 2:
            continue
        full_time_count = sum(1 for exp, _, _ in group if exp.get("type") == "正式工作")
        types = [exp.get("type", "待确认") for exp, _, _ in group]
        companies = "、".join(exp.get("company", "未知公司") for exp, _, _ in group)
        if full_time_count >= 2:
            items.append(anomaly("时间重叠异常", "P0", f"同期存在{full_time_count}段正式工作：{companies}", "强制复核"))
        elif len(group) >= 3:
            # 应届生在校并行多段实习/兼职/项目是常态，不是造假信号：无任何正式工作并行时降为 P2 提示。
            non_full_time_only = full_time_count == 0 and all(
                t in {"实习", "校园项目", "自由职业/创业", "待确认"} for t in types
            )
            if non_full_time_only:
                items.append(anomaly("在校并行经历", "P2", f"同期存在{len(group)}段实习/兼职/项目（疑似在校期间）：{companies}", NO_SCORE_ACTION_PREFIX + "：确认是否为在校并行经历"))
            else:
                items.append(anomaly("时间重叠异常", "P0", f"同期存在{len(group)}段经历：{companies}", "强制复核"))
        elif "正式工作" in types and "实习" in types:
            items.append(anomaly("全职实习重叠", "P1", f"正式工作与实习时间重叠：{companies}", "降权并复核"))
        elif "校园项目" in types:
            items.append(anomaly("项目经历重叠", "P2", f"项目/实习与其他经历重叠：{companies}", "增加追问"))
    unique = []
    seen = set()
    for item in items:
        key = (item["type"], item["level"], item["description"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def validate_experience_credibility(experiences: List[Dict]) -> List[Dict]:
    items = []
    for exp in experiences:
        score = exp.get("credibility_score", calculate_experience_credibility(exp))
        if score < 0.4:
            items.append(anomaly("经历可信度低", "P1", f"{exp.get('company', '未知公司')} - {exp.get('job_title', '未知岗位')}缺少职责、指标、客户对象或时长", "降权"))
    return items


def validate_frequent_job_changes(experiences: List[Dict], years_window: int = 2) -> List[Dict]:
    now = datetime.now()
    window_start = datetime(now.year - years_window, now.month, 1)
    full_time = sorted(
        [exp for exp in experiences if exp.get("type") == "正式工作" and parse_date(exp.get("start_date"))],
        key=lambda exp: parse_date(exp.get("start_date")),
    )
    changes = 0
    recent_short_jobs = 0
    for idx, exp in enumerate(full_time):
        start = parse_date(exp.get("start_date"))
        end = parse_date(exp.get("end_date"))
        if end and end >= window_start and exp.get("duration_months", 0) < 12:
            recent_short_jobs += 1
        if idx == 0:
            continue
        prev_end = parse_date(full_time[idx - 1].get("end_date"))
        if prev_end and start and (prev_end >= window_start or start >= window_start):
            changes += 1

    if changes >= 4:
        return [anomaly("近期频繁跳槽", "P0", f"最近{years_window}年内工作变动{changes}次", "强制复核")]
    if changes == 3 or recent_short_jobs >= 3:
        return [anomaly("近期频繁跳槽", "P1", f"最近{years_window}年内工作变动{changes}次，短任职{recent_short_jobs}段", "降权")]
    if changes == 2:
        return [anomaly("近期频繁跳槽", "P2", f"最近{years_window}年内工作变动{changes}次", "增加追问")]
    return []


def validate_job_hopping_pattern(experiences: List[Dict]) -> List[Dict]:
    full_time = [exp for exp in experiences if exp.get("type") == "正式工作"]
    if len(full_time) < 3:
        return []
    recent = sorted(full_time, key=lambda exp: parse_date(exp.get("start_date")) or datetime.min)[-3:]
    titles = [exp.get("standardized_job_title") or exp.get("job_title", "") for exp in recent]
    low_pairs = 0
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            if get_job_similarity(titles[i], titles[j]) < 0.3:
                low_pairs += 1
    if low_pairs >= 2:
        return [anomaly("岗位跳跃异常", "P1", "最近三段经历岗位差异较大：" + "、".join(titles), "降权并复核")]
    if low_pairs == 1:
        return [anomaly("岗位跳跃提示", "P2", "最近三段经历存在跨职能变化：" + "、".join(titles), "增加追问")]
    return []


def validate_education_completeness(education: List[Dict]) -> List[Dict]:
    if not education:
        return [anomaly("学历信息不完整", "P1", "未解析到教育背景", "待补充")]
    items = []
    for edu in education:
        missing = []
        if not edu.get("school"):
            missing.append("学校")
        if not edu.get("degree"):
            missing.append("学历层级")
        if missing:
            level = "P1" if "学历层级" in missing else "P2"
            items.append(anomaly("学历信息不完整", level, "缺失" + "、".join(missing), "待补充"))
    return items


def _gap_reason_match(text: str) -> Optional[str]:
    """Return the matched gap-reason keyword (备考/考研/创业/项目…), or None."""
    match = GAP_REASON_RE.search(text or "")
    return match.group(0) if match else None


def validate_resume_freshness(candidate: Dict) -> List[Dict]:
    """Remind when the resume's newest information is ~2 years old or older.

    Reads ``candidate['resume_recency']`` produced by parse_resume.detect_resume_recency.
    Pure reminder (P2); never blocks or downgrades. Returns [] when recency is unknown
    or the resume is up to date.
    """
    recency = candidate.get("resume_recency") or {}
    if not recency.get("is_stale"):
        return []
    latest_year = recency.get("latest_year_in_text")
    years = recency.get("years_since_latest")
    threshold = recency.get("stale_threshold_years", 2)
    if recency.get("has_ongoing"):
        description = (
            f"简历标注“至今/在职”，但出现的最新年份为 {latest_year} 年，距今约 {years} 年，"
            f"未见更近的明确时间信息，可能简历未更新或该经历已结束"
        )
        action = NO_SCORE_ACTION_PREFIX + "：向候选人确认是否仍在职及最新经历"
    else:
        description = (
            f"简历最新信息截止 {latest_year} 年，距今约 {years} 年（达到约 {threshold} 年临界值），"
            f"可能未更新或遗漏近期经历"
        )
        action = NO_SCORE_ACTION_PREFIX + "：向候选人确认最新经历后再评估"
    return [anomaly("简历信息可能未更新", "P2", description, action)]


def _gap_explanation_score(experiences: List[Dict]) -> float:
    text = "\n".join((exp.get("description", "") or "") + " " + (exp.get("gap_reason", "") or "") for exp in experiences)
    return 0.85 if _gap_reason_match(text) else 0.35


def _gap_recency_weight(years_since: float) -> float:
    """空窗罚分的时间衰减权重：越久以前的空窗罚得越轻。

    近 2 年内全额计罚（1.0）；2-5 年线性衰减；5 年以上降到下限 0.2
    （仍保留少量罚分，HR 在 gap_details 仍能看到该空窗，但不至于把资深候选人拖垮）。
    """
    if years_since <= 2:
        return 1.0
    if years_since >= 5:
        return 0.2
    return 1.0 - (years_since - 2) / 3 * 0.8


def _format_gap_note(detail: Dict) -> str:
    """Human-readable one-line explanation for a single employment gap."""
    if detail.get("from_date") and detail.get("to_date"):
        span = f"{detail['from_date']} → {detail['to_date']}"
    else:
        span = "时间不详"
    scope = "近 5 年内" if detail.get("within_5y") else "5 年前"
    if detail.get("explained"):
        reason = f"有说明（{detail.get('reason')}）"
    else:
        reason = "无说明，建议追问"
    return (
        f"{span}（{detail['from_company']} → {detail['to_company']}）："
        f"空窗 {detail['gap_months']} 个月，{scope}，{reason}"
    )


def calculate_stability_scores(experiences: List[Dict]) -> Dict:
    full_time = [
        exp for exp in experiences
        if exp.get("type") == "正式工作" and parse_date(exp.get("start_date")) and parse_date(exp.get("end_date"))
    ]
    full_time.sort(key=lambda exp: parse_date(exp.get("start_date")))
    if not full_time:
        return {
            "stability_score": 0.0,
            "gap_score": 0.0,
            "stability_label": "无正式工作",
            "gap_label": "无正式工作",
            "gap_summary": "无正式工作经历，暂无空窗分析。",
            "gap_score_breakdown": "无正式工作经历，暂无空窗分析。",
            "stability_metrics": {},
            "gap_details": [],
            "gap_metrics": {},
        }

    durations = [max(0, exp.get("duration_months") or months_between(parse_date(exp.get("start_date")), parse_date(exp.get("end_date")))) for exp in full_time]
    avg_duration = sum(durations) / len(durations)
    median_duration = statistics.median(durations)
    short_ratio = sum(1 for d in durations if d < 12) / len(durations)
    severe_short_ratio = sum(1 for d in durations if d < 6) / len(durations)
    if len(durations) >= 3:
        recent_avg = sum(durations[-2:]) / 2
        earlier_avg = sum(durations[:-2]) / len(durations[:-2])
    else:
        recent_avg = durations[-1]
        earlier_avg = durations[0] if len(durations) > 1 else durations[-1]
    consistency = min(recent_avg / max(earlier_avg, 1), 1)

    stability_score = 100 * (
        0.35 * min(avg_duration, 42) / 42
        + 0.15 * min(median_duration, 36) / 36
        + 0.20 * (1 - short_ratio)
        + 0.10 * (1 - severe_short_ratio)
        + 0.20 * consistency
    )

    now = datetime.now()
    five_years_ago = datetime(now.year - 5, now.month, 1)
    gaps = []
    recent_gaps = []
    gap_details = []
    longest_penalties = []  # 各段空窗经时间衰减后的罚分占比（0..1），用于“最长空窗”项
    for idx in range(len(full_time) - 1):
        prev_exp = full_time[idx]
        next_exp = full_time[idx + 1]
        end = parse_date(prev_exp.get("end_date"))
        start = parse_date(next_exp.get("start_date"))
        gap = months_between(end, start)
        if gap >= 1:
            gaps.append(gap)
            within_5y = bool(start and start >= five_years_ago)
            if within_5y:
                recent_gaps.append(gap)
            # 该空窗距今年数（以空窗结束、即下一段开始为锚点）→ 时间衰减权重
            years_since = (now - start).days / 365.25 if start else 0.0
            base_penalty = min(gap, 6) / 6  # 该空窗的满罚占比（>=6 个月即满）
            longest_penalties.append(base_penalty * _gap_recency_weight(years_since))
            reason_text = " ".join([
                prev_exp.get("description", "") or "",
                prev_exp.get("gap_reason", "") or "",
                next_exp.get("description", "") or "",
                next_exp.get("gap_reason", "") or "",
            ])
            reason = _gap_reason_match(reason_text)
            detail = {
                "from_company": prev_exp.get("company") or "未知公司",
                "to_company": next_exp.get("company") or "未知公司",
                "from_date": end.strftime("%Y-%m") if end else None,
                "to_date": start.strftime("%Y-%m") if start else None,
                "gap_months": gap,
                "within_5y": within_5y,
                "explained": bool(reason),
                "reason": reason,
            }
            detail["note"] = _format_gap_note(detail)
            gap_details.append(detail)

    total_recent_gap = sum(recent_gaps)
    longest_gap = max(gaps) if gaps else 0
    explanation = _gap_explanation_score(experiences) if gaps else 1.0

    if gap_details:
        explained_count = sum(1 for d in gap_details if d["explained"])
        gap_summary = (
            f"共 {len(gap_details)} 段空窗，累计 {sum(gaps)} 个月，最长 {longest_gap} 个月，"
            f"近 5 年 {total_recent_gap} 个月；其中 {explained_count} 段有说明、"
            f"{len(gap_details) - explained_count} 段无说明。"
        )
    else:
        gap_summary = "正式工作之间无明显空窗（≥1 个月）。"
    # 最长空窗项加时间衰减：取各段空窗“衰减后罚分占比”的最大值，老空窗罚得轻。
    longest_penalty = max(longest_penalties) if longest_penalties else 0.0
    gap_score = 100 * (
        0.50 * (1 - min(total_recent_gap, 12) / 12)
        + 0.30 * (1 - longest_penalty)
        + 0.20 * explanation
    )
    # Gap 分三项构成，让 HR 看懂分数怎么来的（口径同 references/validation_rules.md）。
    recent_part = round(100 * 0.50 * (1 - min(total_recent_gap, 12) / 12), 1)
    longest_part = round(100 * 0.30 * (1 - longest_penalty), 1)
    explain_part = round(100 * 0.20 * explanation, 1)
    gap_score_breakdown = (
        f"Gap 分 {round(gap_score, 1)} = 近5年Gap项 {recent_part}"
        f"（近5年空窗 {total_recent_gap} 个月，满分50）"
        f" + 最长Gap项 {longest_part}（最长 {longest_gap} 个月，已按距今年数时间衰减，满分30）"
        f" + 说明项 {explain_part}（说明系数 {round(explanation, 2)}，满分20）"
    )

    def label(score: float, kind: str) -> str:
        if kind == "gap":
            return "优秀" if score >= 80 else "良好" if score >= 70 else "一般" if score >= 60 else "较差"
        return "优秀" if score >= 80 else "良好" if score >= 60 else "一般" if score >= 40 else "较差"

    return {
        "stability_score": round(stability_score, 1),
        "gap_score": round(gap_score, 1),
        "stability_label": label(stability_score, "stability"),
        "gap_label": label(gap_score, "gap"),
        "gap_summary": gap_summary,
        "gap_score_breakdown": gap_score_breakdown,
        "stability_metrics": {
            "avg_duration_months": round(avg_duration, 1),
            "median_duration_months": round(median_duration, 1),
            "recent_2_avg_months": round(recent_avg, 1),
            "short_tenure_ratio_12": round(short_ratio, 3),
            "severe_short_ratio_6": round(severe_short_ratio, 3),
            "short_tenure_count": sum(1 for d in durations if d < 12),
        },
        "gap_details": gap_details,
        "gap_metrics": {
            "total_gap_months": sum(gaps),
            "recent_5y_gap_months": total_recent_gap,
            "longest_gap_months": longest_gap,
            "gap_count": len(gaps),
            "gap_explanation_score": round(explanation, 2),
            "gap_score_recent_part": recent_part,
            "gap_score_longest_part": longest_part,
            "gap_score_explanation_part": explain_part,
        },
    }


def run_all_validations(candidate: Dict) -> List[Dict]:
    experiences = candidate.get("experiences", [])
    detect_overlaps(experiences)
    enrich_experience_scores(experiences)
    candidate["tenure_summary"] = calculate_tenure(experiences)

    items: List[Dict] = []
    age = candidate.get("basic_info", {}).get("age")
    items.extend(validate_time_ranges(experiences))
    items.extend(validate_overlaps(experiences))
    items.extend(validate_age_tenure(age, candidate.get("tenure_summary", {}).get("full_time_months", 0)))
    items.extend(validate_work_start_age(experiences, age))
    items.extend(validate_frequent_job_changes(experiences))
    items.extend(validate_job_hopping_pattern(experiences))
    items.extend(validate_education_completeness(candidate.get("education", [])))
    items.extend(validate_experience_credibility(experiences))
    items.extend(validate_resume_freshness(candidate))

    candidate["stability_scores"] = calculate_stability_scores(experiences)
    level_order = {"P0": 0, "P1": 1, "P2": 2}
    items.sort(key=lambda item: level_order.get(item["level"], 9))
    candidate["anomalies"] = items
    return items


if __name__ == "__main__":
    sample = {
        "basic_info": {"name": "王五", "age": 23},
        "education": [{"school": "XX学院", "degree": "大专"}],
        "experiences": [
            {"type": "正式工作", "company": "A", "job_title": "电话销售", "standardized_job_title": "电话销售", "start_date": "2022.01", "end_date": "2022.05", "description": "电话销售，负责销售工作"},
            {"type": "正式工作", "company": "B", "job_title": "销售顾问", "standardized_job_title": "销售", "start_date": "2022.06", "end_date": "至今", "description": "负责金融产品外呼，日均拨打120通，月均转化15单，服务C端客户"},
        ],
    }
    print(run_all_validations(sample))
    print(sample["stability_scores"])
