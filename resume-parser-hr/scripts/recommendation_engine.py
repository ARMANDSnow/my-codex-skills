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
    # 学历维度（0-1）：无要求给满分，否则按候选人/要求比例给部分分（差一级不再一票压零）。
    evidence["required_degree_level"] = required_level
    evidence["candidate_degree_level"] = candidate_level
    evidence["degree_ratio"] = 1.0 if required_level <= 0 else min(candidate_level / required_level, 1.0)
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
    last_similarity = get_job_similarity(
        last_exp.get("standardized_job_title") or last_exp.get("job_title", ""), target
    ) if last_exp else 0.0
    evidence["last_similarity"] = last_similarity  # 最近一段相关度（0-1），喂经验维度
    if last_exp and last_similarity < 0.5:
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


# —— 0-100「匹配分」：四维平滑加权（经验/学历/稳定/置信度）− 软扣分（降权/P1/P2）——
# 与旧「BASE 全有或全无」不同：缺一项判据只按比例扣分，不再直接归零，
# 避免真实资深候选人（如描述单薄的多年销售）被压到低分。
# P0 不进分数，只由 fit_tier 追加 ⚠️ 徽标（数据红旗，不改变分档）。
DIM_EXPERIENCE_W = 40.0    # 经验匹配度：相关月数 + 最近一段相关度 + 高可信段数
DIM_EDUCATION_W = 15.0     # 学历匹配：候选人学历 / JD 要求
DIM_STABILITY_W = 25.0     # 履历稳定性：稳定分 + Gap 分
DIM_CONFIDENCE_W = 20.0    # 置信度/证据质量：解析置信度 + 相关经历可信占比
EXP_MONTHS_FULL = 30.0     # 相关经验满 30 个月即拿满「月数」分（平滑饱和）
DOWNGRADE_PEN = 3.0        # 每个降权因子扣分
DOWNGRADE_PEN_CAP = 9.0
P1_PEN = 6.0               # 每个 P1 异常扣分
P1_PEN_CAP = 18.0
P2_PEN = 3.0               # 每个 P2 异常扣分
P2_PEN_CAP = 9.0
DEFAULT_PASS_THRESHOLD = 75.0   # 强推荐门槛（可 CLI / 环境变量覆盖）

# 推荐等级：匹配分单调分档。待审核 = 门槛-10，谨慎 = 门槛-20，其余不推荐。
TIER_STEP = 10.0
TIER_DOTS = {"强推荐": "🟢", "待审核": "🟡", "谨慎": "🟠", "不推荐": "🔴"}


def resolve_threshold(cli_value: Optional[float] = None) -> float:
    """强推荐门槛优先级：CLI 显式值 > 环境变量 HR_PASS_THRESHOLD > 默认 75。"""
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
    evidence: Dict,
    stability_scores: Dict,
    anomalies: List[Dict],
    parsing_confidence: float,
    downgrade: Optional[List[str]] = None,
) -> float:
    """0-100「匹配分」：四维平滑加权 − 软扣分。复用推荐引擎已算好的信号。

    四维（各归一到 0-1 后 × 权重，合计满分 100）：
      D1 经验匹配度 = 相关月数(饱和) + 最近一段相关度 + 高可信段数；
      D2 学历      = 候选人学历 / JD 要求（无要求给满分）；
      D3 稳定性     = 稳定分×0.6 + Gap 分×0.4；
      D4 置信度     = 解析置信度×0.75 + 相关经历可信占比×0.25。
    软扣分：降权因子、P1/P2 异常（均封顶）。P0 不扣分（由 fit_tier 追加 ⚠️ 徽标）。
    """
    downgrade = downgrade or []
    scoring_anomalies = [
        item for item in anomalies if "不参与评分" not in (item.get("action") or "")
    ]
    p1_count = len([item for item in scoring_anomalies if item.get("level") == "P1"])
    p2_count = len([item for item in scoring_anomalies if item.get("level") == "P2"])

    # —— D1 经验匹配度 ——（兼容旧 evidence 仅有 credible_relevant_months 的情况）
    relevant_months = evidence.get("relevant_months", evidence.get("credible_relevant_months", 0)) or 0
    high_credible_count = evidence.get("high_credible_relevant_count", 0) or 0
    last_similarity = min(max(float(evidence.get("last_similarity", 0.0) or 0.0), 0.0), 1.0)
    months_ratio = min(relevant_months / EXP_MONTHS_FULL, 1.0)
    quality_ratio = min(high_credible_count / 2.0, 1.0)
    experience = 0.55 * months_ratio + 0.25 * last_similarity + 0.20 * quality_ratio
    d_experience = DIM_EXPERIENCE_W * experience

    # —— D2 学历匹配 ——
    degree_ratio = min(max(float(evidence.get("degree_ratio", 1.0) or 0.0), 0.0), 1.0)
    d_education = DIM_EDUCATION_W * degree_ratio

    # —— D3 履历稳定性 ——
    stability_score = float(stability_scores.get("stability_score") or 0) / 100.0
    gap_score = float(stability_scores.get("gap_score") or 0) / 100.0
    d_stability = DIM_STABILITY_W * (0.6 * stability_score + 0.4 * gap_score)

    # —— D4 置信度 / 证据质量 ——
    conf = min(max(float(parsing_confidence or 0.0), 0.0), 1.0)
    credible_months = evidence.get("credible_relevant_months", 0) or 0
    credible_ratio = min(credible_months / relevant_months, 1.0) if relevant_months else 0.5
    d_confidence = DIM_CONFIDENCE_W * (0.75 * conf + 0.25 * credible_ratio)

    raw = d_experience + d_education + d_stability + d_confidence

    downgrade_penalty = min(len(downgrade) * DOWNGRADE_PEN, DOWNGRADE_PEN_CAP)
    anomaly_penalty = min(p1_count * P1_PEN, P1_PEN_CAP) + min(p2_count * P2_PEN, P2_PEN_CAP)

    score = raw - downgrade_penalty - anomaly_penalty
    return round(max(0.0, min(100.0, score)), 1)


def fit_tier(score_100: float, threshold: float, p0_items: Optional[List[Dict]] = None) -> Tuple[str, str, str]:
    """匹配分 → 推荐等级（单调）：强推荐 / 待审核 / 谨慎 / 不推荐。

    返回 (等级, 色点, 徽标)。存在 P0 时徽标为 ⚠️（数据红旗），不改变分档——
    同一匹配分永远对应同一等级，彻底消除「高分低等级」脱钩。
    """
    if score_100 >= threshold:
        tier = "强推荐"
    elif score_100 >= threshold - TIER_STEP:
        tier = "待审核"
    elif score_100 >= threshold - 2 * TIER_STEP:
        tier = "谨慎"
    else:
        tier = "不推荐"
    badge = "⚠️" if p0_items else ""
    return tier, TIER_DOTS[tier], badge


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
    parsing_confidence = candidate.get("parsing_confidence", 0.75)
    # 匹配分为唯一底层分数：四维平滑加权（经验/学历/稳定/置信度）− 降权/P1/P2 软扣分。
    # 不再用「强判据全有或全无」把分数归零；解析置信度已并入 D4，低置信度自然拉低分数。
    score_100 = calculate_evidence_score(
        evidence, candidate.get("stability_scores", {}), anomalies,
        parsing_confidence, downgrade,
    )
    # 推荐等级由匹配分单调推导；P0 只追加 ⚠️ 徽标（红旗），不改变分档、不再单独降级。
    tier, tier_dot, tier_badge = fit_tier(score_100, threshold, p0)
    status = tier                     # status 保持干净等级名（供排序/兼容），徽标单列
    tier_display = f"{tier_dot} {tier}" + (f" {tier_badge}" if tier_badge else "")
    p0_remark = "；".join(
        f"{item.get('type')}：{item.get('description')}" for item in p0
    )

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
        reason_parts.append(f"存在{len(p0)}个P0异常（⚠️ 数据红旗），建议关注")

    confidence = round(max(0.0, min(1.0, parsing_confidence * 0.65 + score * 0.35)), 2)
    return {
        "result": status,            # 兼容旧键：置为 tier（推荐等级），供下游排序/读取
        "status": status,            # 推荐等级：强推荐 / 待审核 / 谨慎 / 不推荐
        "tier": tier,                # 同 status，语义更明确
        "tier_dot": tier_dot,        # 色点 🟢🟡🟠🔴
        "tier_badge": tier_badge,    # 有 P0 时为 ⚠️，否则空
        "tier_display": tier_display,  # 直接展示用：色点 + 等级(+ ⚠️)
        "score_100": score_100,      # 0-100 统一「匹配分」（唯一底层分数）
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
