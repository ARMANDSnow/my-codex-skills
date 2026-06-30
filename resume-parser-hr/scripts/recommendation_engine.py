#!/usr/bin/env python3
"""Evidence-based recommendation engine for HR candidate screening."""

from __future__ import annotations

import os
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

# 相关经验「计入厚度」的可信度下限：只要是相关岗位 + 正式/实习 + 有效时长即计入。
# 描述是否详实（量化业绩）只影响可信度/证据强度，不应让真实长年限经验被算成 0（见 R1）。
RELEVANT_CRED_FLOOR = 0.3
# 相关经验达到该月数即视为「长年限本身即证据」，不再因缺量化业绩而判“缺少强证据”。
SUBSTANTIAL_RELEVANT_MONTHS = 24


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


def _score_impact_anomalies(candidate: Dict) -> List[Dict]:
    return [
        item for item in candidate.get("anomalies", [])
        if "不参与评分" not in (item.get("action") or "")
    ]


def related_experiences(candidate: Dict, job_title: str, threshold: float = 0.5) -> List[Dict]:
    result = []
    for exp in candidate.get("experiences", []):
        title = exp.get("standardized_job_title") or exp.get("job_title", "")
        if get_job_similarity(title, job_title) >= threshold:
            result.append(exp)
    return result


def relevant_experience_months(candidate: Dict, job_title: str, cred_floor: float = 0.4) -> int:
    """相关经验月数（按时间区间取并集，避免同期多段被重复累加）。

    单份强判据与批量筛选表共用此口径（修 R6 口径不一致）。``cred_floor`` 控制计入门槛：
    强判据/展示用 RELEVANT_CRED_FLOOR(0.3)——“岗位名+有效时间”即算数；
    高可信加分桶另用 0.7 单独统计，互不影响。
    """
    try:
        from .calculate_tenure import months_between, parse_date
    except ImportError:
        from calculate_tenure import months_between, parse_date

    intervals = []
    for exp in related_experiences(candidate, job_title):
        if exp.get("credibility_score", 0) >= cred_floor and exp.get("type") in {"正式工作", "实习"}:
            start = parse_date(exp.get("start_date"))
            end = parse_date(exp.get("end_date"))
            if start and end and start <= end:
                intervals.append((start, end))
    if not intervals:
        return 0
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:  # 与上一段重叠则合并
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return sum(months_between(s, e) for s, e in merged)


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
    # 相关经验厚度：相关岗位 + 正式/实习 + 有效时长即计入（区间并集）。描述是否详实只影响
    # 可信度/证据强度，不再让真实长年限经验被算成 0（见 R1）。高可信另用 0.7 单独统计加分。
    relevant_months = relevant_experience_months(candidate, target, cred_floor=RELEVANT_CRED_FLOOR)
    credible_months = relevant_experience_months(candidate, target, cred_floor=0.4)
    credible_relevant = [exp for exp in relevant if exp.get("credibility_score", 0) >= 0.4 and exp.get("type") in {"正式工作", "实习"}]
    high_credible_relevant = [exp for exp in relevant if exp.get("credibility_score", 0) >= 0.7]
    evidence["relevant_months"] = relevant_months
    evidence["credible_relevant_months"] = credible_months
    evidence["high_credible_relevant_count"] = len(high_credible_relevant)

    if relevant_months < min_months:
        unmet.append(f"相关经验不足{min_months}个月（当前{relevant_months}个月）")

    sorted_exps = _sorted_experiences(candidate)
    last_exp = sorted_exps[-1] if sorted_exps else None
    if last_exp and get_job_similarity(last_exp.get("standardized_job_title") or last_exp.get("job_title", ""), target) < 0.5:
        unmet.append("最近一段经历与目标岗位不相关")
    elif not last_exp:
        unmet.append("缺少经历信息")

    scoring_anomalies = _score_impact_anomalies(candidate)
    p0 = [item for item in scoring_anomalies if item.get("level") == "P0"]
    p1 = [item for item in scoring_anomalies if item.get("level") == "P1"]
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
        if (
            relevant
            and relevant_months < SUBSTANTIAL_RELEVANT_MONTHS
            and not high_credible_relevant
            and not any(_has_sales_evidence(exp) for exp in credible_relevant)
        ):
            # 长年限相关经历本身即证据：仅短经历且无量化业绩时才判“缺少强证据”，
            # 避免资深销售因没写业绩数字被归零 BASE（描述单薄改由低可信 P1/降权体现）。
            unmet.append("销售相关经历缺少强证据")

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
    scoring_anomalies = _score_impact_anomalies(candidate)
    if any("时间" in item.get("type", "") or "重叠" in item.get("type", "") for item in scoring_anomalies):
        factors.append("时间线异常")
    if any("跳槽" in item.get("type", "") for item in scoring_anomalies):
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
    scoring_anomalies = [item for item in anomalies if "不参与评分" not in (item.get("action") or "")]
    score -= len([item for item in scoring_anomalies if item.get("level") == "P1"]) * 0.15
    score -= len([item for item in scoring_anomalies if item.get("level") == "P2"]) * 0.05
    return round(max(0.0, min(1.0, score)), 2)


# —— 0-100「证据强度综合评分」与「免复核通过」阈值 ——
# 满分 100：BASE(强判据) + WEAK(弱判据) + RELEVANT(相关经验厚度) + STABILITY(稳定/Gap)
#           - DOWNGRADE(降权) - ANOMALY(P1/P2) - P0_DAMPEN(P0 软抑制)
EVIDENCE_BASE = 45.0          # 强判据满足的地基分（单独满足仍不足 75）
WEAK_UNIT = 3.6              # 每项弱判据加分
WEAK_CAP = 5                 # 弱判据当前最多 5 项 → 满档 18
REL_MONTHS_FULL = 12.0      # 可信相关经验满 12 个月给满月数分
REL_MONTHS_PTS = 12.0       # 月数桶满分
REL_COUNT_UNIT = 4.0        # 每段高可信相关经历加分
REL_COUNT_CAP = 2           # 高可信相关经历封顶 2 段 → 满档 8（月数+段数合计 20）
STABILITY_W = 10.0          # 履历稳定分权重（吃 0-100 连续值）
GAP_W = 7.0                 # Gap 分权重（吃 0-100 连续值）
DOWNGRADE_UNIT = 6.0        # 每个降权因子扣分
DOWNGRADE_CAP = 3           # 降权封顶 3 项 → -18
P1_PENALTY = 8.0            # 每个 P1 异常扣分
P2_PENALTY = 3.0            # 每个 P2 异常扣分
P0_DAMPEN_UNIT = 6.0        # 每个 P0 软抑制（不硬拦截，由 status 标签兜底）
P0_DAMPEN_CAP = 12.0        # P0 软抑制封顶，保证证据极强者仍可能 ≥ 阈值落入 ✅⚠️
DEFAULT_PASS_THRESHOLD = 75.0


def resolve_threshold(cli_value: Optional[float] = None) -> float:
    """免复核通过阈值优先级：CLI 显式值 > 环境变量 HR_PASS_THRESHOLD > 默认 75。"""
    if cli_value is not None:
        try:
            return float(cli_value)
        except (TypeError, ValueError):
            pass
    env_value = os.environ.get("HR_PASS_THRESHOLD")
    if env_value:
        try:
            return float(env_value)
        except ValueError:
            pass
    return DEFAULT_PASS_THRESHOLD


def calculate_evidence_score(
    strong_met: bool,
    weak: List[str],
    downgrade: List[str],
    evidence: Dict,
    stability_scores: Dict,
    anomalies: List[Dict],
) -> float:
    """0-100 证据强度综合评分。复用推荐引擎已算好的信号，不新增抽取。

    P0 仅软抑制分数（不硬拦截）——是否免复核交给 evidence_status 的状态标签。
    与 calculate_recommendation_score 一致，仅对「参与评分」的异常计扣分。
    """
    scoring_anomalies = [
        item for item in anomalies if "不参与评分" not in (item.get("action") or "")
    ]
    p0_count = len([item for item in scoring_anomalies if item.get("level") == "P0"])
    p1_count = len([item for item in scoring_anomalies if item.get("level") == "P1"])
    p2_count = len([item for item in scoring_anomalies if item.get("level") == "P2"])

    base = EVIDENCE_BASE if strong_met else 0.0
    weak_pts = min(len(weak), WEAK_CAP) * WEAK_UNIT

    # 月数桶吃「相关经验厚度」(relevant_months，含描述单薄但真实的长年限)；
    # 高可信段数桶单独奖励证据质量。兼容旧 evidence 仅有 credible_relevant_months 的情况。
    relevant_months = evidence.get("relevant_months", evidence.get("credible_relevant_months", 0)) or 0
    high_credible_count = evidence.get("high_credible_relevant_count", 0) or 0
    relevant_pts = (
        min(relevant_months / REL_MONTHS_FULL, 1.0) * REL_MONTHS_PTS
        + min(high_credible_count, REL_COUNT_CAP) * REL_COUNT_UNIT
    )

    stability_score = float(stability_scores.get("stability_score") or 0)
    gap_score = float(stability_scores.get("gap_score") or 0)
    stability_pts = (stability_score / 100) * STABILITY_W + (gap_score / 100) * GAP_W

    downgrade_penalty = min(len(downgrade), DOWNGRADE_CAP) * DOWNGRADE_UNIT
    anomaly_penalty = p1_count * P1_PENALTY + p2_count * P2_PENALTY
    p0_dampen = min(min(p0_count, 2) * P0_DAMPEN_UNIT, P0_DAMPEN_CAP)

    score = (
        base + weak_pts + relevant_pts + stability_pts
        - downgrade_penalty - anomaly_penalty - p0_dampen
    )
    return round(max(0.0, min(100.0, score)), 1)


def evidence_status(score_100: float, threshold: float, p0_items: List[Dict]) -> str:
    """证据分 → 状态标签：✅ 通过 / ✅⚠️（达标但有 P0）/ 待筛选。"""
    if score_100 >= threshold:
        return "✅⚠️" if p0_items else "✅ 通过"
    return "待筛选"


def recommend(
    candidate: Dict,
    jd_text: Optional[str] = None,
    job_title: Optional[str] = None,
    pass_threshold: Optional[float] = None,
) -> Dict:
    jd = parse_jd(jd_text or "")
    target = standardize_job_title(job_title or jd.get("job_title") or "销售")

    run_all_validations(candidate)
    strong_met, unmet, evidence = check_strong_criteria(candidate, jd, target)
    weak = check_weak_criteria(candidate, jd, target)
    downgrade = check_downgrade_factors(candidate, jd, target)
    anomalies = candidate.get("anomalies", [])
    scoring_anomalies = _score_impact_anomalies(candidate)
    score = calculate_recommendation_score(strong_met, weak, downgrade, anomalies)
    p0 = [item for item in scoring_anomalies if item.get("level") == "P0"]

    threshold = resolve_threshold(pass_threshold)
    # BASE 只看实质性强判据（学历/经验/相关性/稳定性/销售证据），把「异常门」剥离：
    # P0 改为软抑制 + ✅⚠️ 标签，P1 数量改为扣分——否则带 P0 者 BASE 归零、永远到不了阈值，
    # ✅⚠️ 兜底态形同虚设。
    core_unmet = [u for u in unmet if "P0异常" not in u and "P1异常超过" not in u]
    strong_core_met = len(core_unmet) == 0
    score_100 = calculate_evidence_score(
        strong_core_met, weak, downgrade, evidence,
        candidate.get("stability_scores", {}), anomalies,
    )
    status = evidence_status(score_100, threshold, p0)
    p0_remark = "；".join(
        f"{item.get('type')}：{item.get('description')}" for item in p0
    )

    # —— 三档推荐等级（强推荐/待审核/暂不推荐）已下线，改用证据分 + status 标签。
    #    保留以下逻辑以便回溯，如需恢复取消注释即可。 ——
    # if strong_met and score >= 0.7 and not p0:
    #     result = "强推荐"
    # elif score >= 0.35 or p0 or unmet:
    #     result = "待审核"
    # else:
    #     result = "暂不推荐"
    # if any("低可信相关经历" in item for item in downgrade) and result == "强推荐":
    #     result = "待审核"

    reason_parts = []
    rel_m = int(evidence.get("relevant_months", 0) or 0)
    if rel_m > 0:
        yrs, mos = divmod(rel_m, 12)
        span = (f"{yrs}年" if yrs else "") + (f"{mos}个月" if mos else "")
        thin = rel_m >= SUBSTANTIAL_RELEVANT_MONTHS and evidence.get("high_credible_relevant_count", 0) == 0
        reason_parts.append(
            f"相关销售经历约{span}" + ("（但缺少量化业绩，建议人工核验）" if thin else "")
        )
    reason_parts.append("满足强判据" if strong_met else "强判据未满足：" + "、".join(unmet[:4]))
    if weak:
        reason_parts.append("优势：" + "、".join(weak[:4]))
    if downgrade:
        reason_parts.append("风险：" + "、".join(downgrade[:4]))
    if p0:
        reason_parts.append(f"存在{len(p0)}个P0异常，已在状态高亮，建议关注")

    parsing_confidence = candidate.get("parsing_confidence", 0.75)
    confidence = round(max(0.0, min(1.0, parsing_confidence * 0.65 + score * 0.35)), 2)
    return {
        "result": status,            # 兼容旧键：置为 status，供下游排序/读取
        "status": status,            # ✅ 通过 / ✅⚠️ / 待筛选
        "score_100": score_100,      # 0-100 统一证据强度综合评分
        "pass_threshold": threshold,
        "p0_items": [
            {"type": item.get("type"), "description": item.get("description")}
            for item in p0
        ],
        "p0_remark": p0_remark,
        "reason": "；".join(reason_parts),
        "confidence": confidence,
        "score": score,              # 保留 0-1 内部分（confidence 计算/兼容下游）
        "target_job_title": target,
        "details": {
            "strong_criteria_met": strong_met,
            "unmet_strong_criteria": unmet,
            "weak_criteria": weak,
            "downgrade_factors": downgrade,
            "evidence": evidence,
            "p0_count": len(p0),
            "p1_count": len([item for item in scoring_anomalies if item.get("level") == "P1"]),
            "p2_count": len([item for item in scoring_anomalies if item.get("level") == "P2"]),
            "compliance_review_count": len(anomalies) - len(scoring_anomalies),
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
