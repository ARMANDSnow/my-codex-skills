#!/usr/bin/env python3
"""Evidence-based recommendation engine for HR candidate screening."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

try:
    from .standardize_job_title import SALES_TITLES, get_job_similarity, standardize_job_title
    from .validate_anomalies import PERFORMANCE_RE, CUSTOMER_RE, run_all_validations
except ImportError:
    from standardize_job_title import SALES_TITLES, get_job_similarity, standardize_job_title
    from validate_anomalies import PERFORMANCE_RE, CUSTOMER_RE, run_all_validations


DEGREE_ORDER = {"不限": 0, "高中": 1, "中专": 1, "大专": 2, "本科": 3, "硕士": 4, "博士": 5}
SALES_JOB_PATTERNS = ["电话销售", "电销", "销售顾问", "销售代表", "客户经理", "大客户销售", "渠道销售", "招商", "BD", "商务拓展", "面销", "销售"]


def parse_jd(jd_text: str) -> Dict:
    result = {
        "min_degree": None,
        "skills": [],
        "min_experience_months": 0,
        "job_title": None,
        "accept_no_experience": False,
        "raw_text": jd_text or "",
    }
    text = jd_text or ""
    if not text:
        return result

    if re.search(r"学历不限|不限学历", text):
        result["min_degree"] = "不限"
    else:
        for degree in ["博士", "硕士", "本科", "大专", "高中", "中专"]:
            if re.search(degree + r"(及以上|以上|优先|学历)?", text):
                result["min_degree"] = "高中" if degree == "中专" else degree
                break

    for pattern in SALES_JOB_PATTERNS:
        if re.search(pattern, text, re.I):
            result["job_title"] = standardize_job_title(pattern)
            break
    if not result["job_title"]:
        title_match = re.search(r"(招聘|岗位|职位)[:：]?\s*([\u4e00-\u9fa5A-Za-z]{2,12})", text)
        if title_match:
            result["job_title"] = standardize_job_title(title_match.group(2))

    skills = ["销售", "电销", "面销", "客户转化", "客户沟通", "外呼", "成交", "回款", "渠道", "招商", "BD", "大客户"]
    result["skills"] = [skill for skill in skills if skill.lower() in text.lower()]

    year_match = re.search(r"(\d+)\s*年(以上|及以上)?", text)
    month_match = re.search(r"(\d+)\s*个?月(以上|及以上)?", text)
    half_year = re.search(r"半年(以上|及以上)?", text)
    if year_match:
        result["min_experience_months"] = int(year_match.group(1)) * 12
    elif month_match:
        result["min_experience_months"] = int(month_match.group(1))
    elif half_year:
        result["min_experience_months"] = 6

    if re.search(r"接受应届|无经验可|经验不限|不限经验", text):
        result["accept_no_experience"] = True
        result["min_experience_months"] = 0

    return result


def is_sales_position(job_title: str, jd: Dict) -> bool:
    target = standardize_job_title(job_title or jd.get("job_title") or "")
    return target in SALES_TITLES or "销售" in target or any(skill in jd.get("skills", []) for skill in ["销售", "电销", "面销", "客户转化"])


def _candidate_degree_level(candidate: Dict) -> int:
    levels = [DEGREE_ORDER.get(edu.get("degree", ""), 0) for edu in candidate.get("education", [])]
    return max(levels) if levels else 0


def _required_degree_level(jd: Dict) -> int:
    return DEGREE_ORDER.get(jd.get("min_degree") or "不限", 0)


def _sorted_experiences(candidate: Dict) -> List[Dict]:
    try:
        from .calculate_tenure import parse_date
    except ImportError:
        from calculate_tenure import parse_date
    return sorted(candidate.get("experiences", []), key=lambda exp: parse_date(exp.get("start_date")) or parse_date("1900.01"))


def related_experiences(candidate: Dict, job_title: str, threshold: float = 0.5) -> List[Dict]:
    result = []
    for exp in candidate.get("experiences", []):
        title = exp.get("standardized_job_title") or exp.get("job_title", "")
        if get_job_similarity(title, job_title) >= threshold:
            result.append(exp)
    return result


def _has_sales_evidence(exp: Dict) -> bool:
    desc = exp.get("description", "") or ""
    return bool(PERFORMANCE_RE.search(desc) or CUSTOMER_RE.search(desc))


def check_strong_criteria(candidate: Dict, jd: Dict, job_title: str) -> Tuple[bool, List[str], Dict]:
    unmet: List[str] = []
    evidence: Dict = {}
    target = standardize_job_title(job_title or jd.get("job_title") or "销售")
    sales_position = is_sales_position(target, jd)

    required_level = _required_degree_level(jd)
    candidate_level = _candidate_degree_level(candidate)
    if required_level > 0 and candidate_level < required_level:
        unmet.append(f"学历未达最低要求：要求{jd.get('min_degree')}，候选人最高学历不足")

    relevant = related_experiences(candidate, target)
    min_months = jd.get("min_experience_months") or (6 if sales_position and not jd.get("accept_no_experience") else 0)
    credible_relevant = [exp for exp in relevant if exp.get("credibility_score", 0) >= 0.4 and exp.get("type") in {"正式工作", "实习"}]
    high_credible_relevant = [exp for exp in relevant if exp.get("credibility_score", 0) >= 0.7]
    credible_months = sum(exp.get("duration_months", 0) for exp in credible_relevant)
    evidence["credible_relevant_months"] = credible_months
    evidence["high_credible_relevant_count"] = len(high_credible_relevant)

    if credible_months < min_months:
        unmet.append(f"高/中可信相关经验不足{min_months}个月（当前{credible_months}个月）")

    sorted_exps = _sorted_experiences(candidate)
    last_exp = sorted_exps[-1] if sorted_exps else None
    if last_exp and get_job_similarity(last_exp.get("standardized_job_title") or last_exp.get("job_title", ""), target) < 0.5:
        unmet.append("最近一段经历与目标岗位不相关")
    elif not last_exp:
        unmet.append("缺少经历信息")

    p0 = [item for item in candidate.get("anomalies", []) if item.get("level") == "P0"]
    p1 = [item for item in candidate.get("anomalies", []) if item.get("level") == "P1"]
    if p0:
        unmet.append(f"存在{len(p0)}个P0异常")
    if len(p1) > 1:
        unmet.append(f"P1异常超过1项（当前{len(p1)}项）")

    if sales_position:
        stability = candidate.get("stability_scores", {})
        stability_score = stability.get("stability_score", 0)
        gap_score = stability.get("gap_score", 0)
        if stability_score < 60:
            unmet.append(f"履历稳定分不足60分（当前{stability_score}）")
        if gap_score < 70:
            unmet.append(f"Gap分不足70分（当前{gap_score}）")
        if relevant and not high_credible_relevant and not any(_has_sales_evidence(exp) for exp in credible_relevant):
            unmet.append("销售相关经历缺少强证据，不能强推荐")

    return len(unmet) == 0, unmet, evidence


def check_weak_criteria(candidate: Dict, jd: Dict, job_title: str) -> List[str]:
    satisfied: List[str] = []
    experiences = candidate.get("experiences", [])
    text = "\n".join(exp.get("description", "") or "" for exp in experiences)
    if re.search(r"客户|用户|沟通|谈判|服务|维护|回访", text):
        satisfied.append("有客户沟通经验")
    if candidate.get("parsing_confidence", 0) >= 0.75:
        satisfied.append("简历表达和字段完整度较好")
    stability = candidate.get("stability_scores", {})
    if stability.get("stability_score", 0) >= 80 and stability.get("gap_score", 0) >= 80:
        satisfied.append("稳定性优秀")
    elif stability.get("stability_score", 0) >= 60 and stability.get("gap_score", 0) >= 70:
        satisfied.append("稳定性尚可")
    if any(PERFORMANCE_RE.search(exp.get("description", "") or "") for exp in experiences):
        satisfied.append("有销售或业务结果指标")
    if related_experiences(candidate, job_title, threshold=0.3):
        satisfied.append("过往行业或职能可迁移")
    return satisfied


def check_downgrade_factors(candidate: Dict, jd: Dict, job_title: str) -> List[str]:
    factors: List[str] = []
    relevant = related_experiences(candidate, job_title)
    if len(relevant) == 1 and relevant[0].get("credibility_score", 0) < 0.4:
        factors.append("仅有一段低可信相关经历")
    if relevant and not any(exp in relevant for exp in _sorted_experiences(candidate)[-2:]):
        factors.append("相关经历较久以前，最近岗位不相关")
    if any("时间" in item.get("type", "") or "重叠" in item.get("type", "") for item in candidate.get("anomalies", [])):
        factors.append("时间线异常")
    if any("跳槽" in item.get("type", "") for item in candidate.get("anomalies", [])):
        factors.append("近期跳槽频率偏高")
    stability = candidate.get("stability_scores", {})
    if is_sales_position(job_title, jd):
        if stability.get("stability_score", 0) < 50:
            factors.append(f"履历稳定分低（{stability.get('stability_score', 0)}）")
        if stability.get("gap_score", 0) < 60:
            factors.append(f"Gap分低（{stability.get('gap_score', 0)}）")
    return factors


def calculate_recommendation_score(strong_met: bool, weak: List[str], downgrade: List[str], anomalies: List[Dict]) -> float:
    score = 0.5 if strong_met else 0.0
    score += min(len(weak) * 0.1, 0.3)
    score -= min(len(downgrade) * 0.1, 0.3)
    score -= len([item for item in anomalies if item.get("level") == "P1"]) * 0.15
    score -= len([item for item in anomalies if item.get("level") == "P2"]) * 0.05
    return round(max(0.0, min(1.0, score)), 2)


def recommend(candidate: Dict, jd_text: Optional[str] = None, job_title: Optional[str] = None) -> Dict:
    jd = parse_jd(jd_text or "")
    target = standardize_job_title(job_title or jd.get("job_title") or "销售")

    run_all_validations(candidate)
    strong_met, unmet, evidence = check_strong_criteria(candidate, jd, target)
    weak = check_weak_criteria(candidate, jd, target)
    downgrade = check_downgrade_factors(candidate, jd, target)
    anomalies = candidate.get("anomalies", [])
    score = calculate_recommendation_score(strong_met, weak, downgrade, anomalies)
    p0 = [item for item in anomalies if item.get("level") == "P0"]

    if strong_met and score >= 0.7 and not p0:
        result = "强推荐"
    elif score >= 0.35 or p0 or unmet:
        result = "待审核"
    else:
        result = "暂不推荐"

    if any("低可信相关经历" in item for item in downgrade) and result == "强推荐":
        result = "待审核"

    reason_parts = []
    reason_parts.append("满足强判据" if strong_met else "强判据未满足：" + "、".join(unmet[:4]))
    if weak:
        reason_parts.append("优势：" + "、".join(weak[:4]))
    if downgrade:
        reason_parts.append("风险：" + "、".join(downgrade[:4]))
    if p0:
        reason_parts.append(f"存在{len(p0)}个P0异常，需强制复核")

    parsing_confidence = candidate.get("parsing_confidence", 0.75)
    confidence = round(max(0.0, min(1.0, parsing_confidence * 0.65 + score * 0.35)), 2)
    return {
        "result": result,
        "reason": "；".join(reason_parts),
        "confidence": confidence,
        "score": score,
        "target_job_title": target,
        "details": {
            "strong_criteria_met": strong_met,
            "unmet_strong_criteria": unmet,
            "weak_criteria": weak,
            "downgrade_factors": downgrade,
            "evidence": evidence,
            "p0_count": len(p0),
            "p1_count": len([item for item in anomalies if item.get("level") == "P1"]),
            "p2_count": len([item for item in anomalies if item.get("level") == "P2"]),
        },
    }


if __name__ == "__main__":
    sample = {
        "basic_info": {"name": "李四", "age": 26, "phone": "13800138000"},
        "education": [{"school": "XX学院", "degree": "大专"}],
        "experiences": [
            {"type": "正式工作", "company": "A公司", "job_title": "电话销售", "standardized_job_title": "电话销售", "start_date": "2022.01", "end_date": "2023.08", "description": "负责金融产品外呼，日均拨打120通，月均转化15单，服务C端客户"},
            {"type": "正式工作", "company": "B公司", "job_title": "销售顾问", "standardized_job_title": "销售", "start_date": "2023.09", "end_date": "至今", "description": "维护客户并跟进成交，月销售额20万"},
        ],
        "parsing_confidence": 0.9,
    }
    print(recommend(sample, "招聘电话销售，大专及以上，半年以上销售经验"))
