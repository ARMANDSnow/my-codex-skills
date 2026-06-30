#!/usr/bin/env python3
"""Parse resume files or text into an HR candidate card."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .calculate_tenure import calculate_tenure, detect_overlaps, months_between, parse_date
    from .recommendation_engine import recommend, resolve_threshold
    from .standardize_job_title import standardize_job_title
    from .validate_anomalies import calculate_experience_credibility, run_all_validations
except ImportError:
    from calculate_tenure import calculate_tenure, detect_overlaps, months_between, parse_date
    from recommendation_engine import recommend, resolve_threshold
    from standardize_job_title import standardize_job_title
    from validate_anomalies import calculate_experience_credibility, run_all_validations


DATE_RANGE_RE = re.compile(
    r"(?P<start>(?:19|20)\d{2}[./年-]?\s*\d{0,2}月?)\s*[-~至到—–]+\s*(?P<end>至今|现在|目前|present|now|(?:19|20)\d{2}[./年-]?\s*\d{0,2}月?)",
    re.I,
)
PHONE_RE = re.compile(r"(?:(?:手机|电话|联系方式)[:：]?\s*)?((?:\+?86[-\s]?)?1[3-9]\d[-\s]?\d{4}[-\s]?\d{4})")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# 语言能力：基础语种 + 各语种常见证书/等级。命中语种名或其证书即记入该语种。
_LANGUAGE_BASE = [
    ("英语", r"英语|英文|english"),
    ("日语", r"日语|日文|日本语"),
    ("韩语", r"韩语|韩文|韩国语"),
    ("法语", r"法语|法文"),
    ("德语", r"德语|德文"),
    ("西班牙语", r"西班牙语|西语"),
    ("俄语", r"俄语|俄文"),
    ("粤语", r"粤语|广东话"),
    ("普通话", r"普通话|国语"),
]
_LANGUAGE_CERTS = {
    "英语": [r"CET-?6", r"CET-?4", r"六级", r"四级", r"雅思\s*[\d.]*", r"IELTS\s*[\d.]*",
             r"托福\s*\d*", r"TOEFL\s*\d*", r"专八", r"TEM-?8", r"专四", r"TEM-?4", r"BEC"],
    "日语": [r"JLPT", r"N[1-5]\b"],
    "韩语": [r"TOPIK\s*\d*"],
}
# 仅匹配独立的四位年份（避免命中手机号/工号里的数字片段）。
YEAR_TOKEN_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
PRESENT_TOKEN_RE = re.compile(r"至今|现在|目前|present|now|在职", re.I)
# 在校期间兼职/实习的信号词，用于把"在校期间的销售/兼职"从正式工作降级（见 extract_experiences）。
PART_TIME_RE = re.compile(r"兼职|寒假|暑假|课余|在校期间|勤工俭学|part[\s-]?time", re.I)
# 图片简历后缀，OCR 处理（见 extract_text_from_image）。
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}


def extract_languages(text: str) -> str:
    """提取候选人语言能力，带常见证书；未提及时返回“未说明”。"""
    labels = []
    for name, pattern in _LANGUAGE_BASE:
        certs = []
        for cert_pattern in _LANGUAGE_CERTS.get(name, []):
            match = re.search(cert_pattern, text, re.I)
            if match:
                token = match.group(0).strip()
                if token and token not in certs:
                    certs.append(token)
        if re.search(pattern, text, re.I) or certs:
            labels.append(f"{name}（{'、'.join(certs)}）" if certs else name)
    return "、".join(labels) if labels else "未说明"


def detect_resume_recency(text: str, stale_years: int = 2) -> Dict:
    """判断简历信息新旧：取文本中出现的最新四位年份，距今 ≥ 阈值则视为可能未更新。

    用文本最新年份而非经历结束日期，避免“至今”被解析成当前月份后掩盖陈旧简历。
    """
    now = datetime.now()
    years = [int(y) for y in YEAR_TOKEN_RE.findall(text) if 1990 <= int(y) <= now.year]
    latest_year = max(years) if years else None
    years_since = (now.year - latest_year) if latest_year is not None else None
    has_ongoing = bool(PRESENT_TOKEN_RE.search(text))
    # 标注“至今/在职”的简历默认更可能是近况，临界值放宽 1 年，避免误伤长期在职者。
    effective_threshold = stale_years + 1 if has_ongoing else stale_years
    return {
        "latest_year_in_text": latest_year,
        "years_since_latest": years_since,
        "has_ongoing": has_ongoing,
        "is_stale": bool(latest_year is not None and years_since >= effective_threshold),
        "stale_threshold_years": stale_years,
    }


def extract_text_from_image(path: str) -> str:
    """对图片简历做 OCR；依赖未安装/不可用时抛出可读异常，由上层降级为人工处理。

    依赖均为可选：优先 pytesseract（需系统 tesseract + chi_sim 语言包），
    其次 paddleocr。两者都不可用时抛 RuntimeError。
    """
    # 方案一：pytesseract
    try:
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(path), lang="chi_sim+eng")
        if text and text.strip():
            return text
    except ImportError:
        pass
    except Exception:
        # 库已装但运行失败（如缺 tesseract 二进制），继续尝试 paddleocr。
        pass
    # 方案二：paddleocr
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        result = ocr.ocr(path, cls=True)
        lines = []
        for page in result or []:
            for line in page or []:
                if line and len(line) >= 2 and line[1]:
                    lines.append(line[1][0])
        if lines:
            return "\n".join(lines)
    except ImportError:
        pass
    except Exception:
        pass
    raise RuntimeError("图片简历 OCR 不可用：未安装 pytesseract(+tesseract chi_sim) 或 paddleocr，需人工处理")


def extract_text(path: str) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("需要安装 python-docx 才能解析 .docx") from exc
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs)
    if suffix == ".pdf":
        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError("需要安装 pdfplumber 才能解析 PDF") from exc
        pages_text = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                txt = ""
                try:
                    # layout=True 尽量保留多栏版面的阅读顺序，缓解学历等开头信息错行。
                    txt = page.extract_text(layout=True) or ""
                except Exception:
                    txt = ""
                if not txt.strip():
                    try:
                        # 退化：按字符 (top, x0) 排序后拼接，进一步缓解乱序。
                        chars = sorted(page.chars, key=lambda c: (round(c["top"], 1), c["x0"]))
                        txt = "".join(c["text"] for c in chars)
                    except Exception:
                        txt = page.extract_text() or ""
                pages_text.append(txt)
        return "\n".join(pages_text)
    if suffix in IMAGE_SUFFIXES:
        return extract_text_from_image(str(file_path))
    raise RuntimeError(f"暂不支持文件类型：{suffix}")


def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_basic_info(text: str) -> Dict:
    info = {"name": None, "age": None, "phone": None, "email": None, "birth_date": None, "languages": "未说明"}
    name_match = re.search(r"(?:姓名|名字)[:：]\s*([一-龥A-Za-z]{2,20})", text)
    if name_match:
        info["name"] = name_match.group(1)
    else:
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if re.fullmatch(r"[一-龥]{2,4}", first_line):
            info["name"] = first_line

    phone_match = PHONE_RE.search(text)
    if phone_match:
        info["phone"] = re.sub(r"\D", "", phone_match.group(1))[-11:]
    email_match = EMAIL_RE.search(text)
    if email_match:
        info["email"] = email_match.group(0)

    birth_match = re.search(r"(?:出生|生日|出生日期)[:：]?\s*((?:19|20)\d{2})[./年-]?(\d{1,2})?", text)
    if birth_match:
        year = int(birth_match.group(1))
        month = int(birth_match.group(2) or 1)
        info["birth_date"] = f"{year:04d}-{month:02d}-01"
        info["age"] = datetime.now().year - year
    age_match = re.search(r"(?:年龄|岁数)[:：]?\s*(\d{1,2})\s*岁?", text)
    if age_match:
        info["age"] = int(age_match.group(1))
    elif not info["age"]:
        inline_age = re.search(r"(\d{2})\s*岁", text)
        if inline_age:
            info["age"] = int(inline_age.group(1))
    info["languages"] = extract_languages(text)
    return info


DEGREE_RANK = {"高中": 1, "中专": 1, "大专": 2, "专科": 2, "本科": 3, "研究生": 4, "硕士": 4, "博士": 5}
SCHOOL_RE = r"([一-龥A-Za-z]{2,30}(?:大学|学院|学校|职业技术学院|职校))"


def extract_education(text: str) -> List[Dict]:
    degree_words = ["博士", "硕士", "研究生", "本科", "大专", "专科", "高中", "中专"]

    # 优先在“教育/学历”段落内查找，准确率更高；段落内缺失再全文回退（精确优先、召回兜底）。
    section = re.search(r"(教育背景|教育经历|教育情况|学历信息|院校信息|最高学历|学历)[\s\S]{0,400}", text)
    edu_section = section.group(0) if section else None
    scope = edu_section or text

    schools = re.findall(SCHOOL_RE, scope)
    if not schools and edu_section:
        schools = re.findall(SCHOOL_RE, text)

    # 取所有出现的学历词里等级最高的，避免“先大专后专升本本科”只取到第一个。
    found = [d for d in degree_words if re.search(d, scope)]
    if not found and edu_section:
        found = [d for d in degree_words if re.search(d, text)]
    degree = max(found, key=lambda d: DEGREE_RANK.get(d, 0)) if found else None
    if degree == "专科":
        degree = "大专"
    if degree == "研究生":
        degree = "硕士"

    major_match = re.search(r"专业[:：]\s*([一-龥A-Za-z]{2,30})", scope) \
        or re.search(r"([一-龥A-Za-z]{2,20})专业", scope)

    # 解析教育起止年月，供应届生“在校期间”判定使用（见 extract_experiences）。
    edu_start = edu_end = None
    date_match = DATE_RANGE_RE.search(scope)
    if date_match:
        edu_start = parse_date(date_match.group("start"))
        edu_end = parse_date(date_match.group("end"))

    # 学历层级推断：很多简历只写“院校+专业+起止年月”，不写“本科/大专”字样。
    # 此时按院校类型和学制时长推断，避免出现“有院校却学历缺失”的矛盾展示。
    degree_inferred = False
    if not degree and schools:
        school0 = schools[0]
        span = months_between(edu_start, edu_end) if (edu_start and edu_end) else None
        if any(k in school0 for k in ["职业技术学院", "职业学院", "高等专科", "专科学校", "技工学校", "职校"]):
            degree, degree_inferred = "大专", True
        elif span is not None and span >= 42:
            degree, degree_inferred = "本科", True
        elif span is not None and span >= 24:
            degree, degree_inferred = "大专", True
        elif "大学" in school0:
            degree, degree_inferred = "本科", True

    if not schools and not degree:
        # 降级：返回占位结构（而非 []），让 validate_education_completeness 出“缺失”提示而非完全静默。
        return [{
            "school": None, "degree": None, "major": None,
            "start_date": None, "end_date": None,
            "parse_note": "未解析到明确教育信息",
        }]

    return [{
        "school": schools[0] if schools else None,
        "degree": degree,
        "degree_inferred": degree_inferred,
        "major": major_match.group(1) if major_match else None,
        "start_date": edu_start.strftime("%Y-%m-%d") if edu_start else None,
        "end_date": edu_end.strftime("%Y-%m-%d") if edu_end else None,
    }]


def classify_experience(block: str, title: str) -> str:
    text = f"{title}\n{block}".lower()
    if re.search(r"实习|intern", text):
        return "实习"
    if re.search(r"校园项目|课程项目|毕业设计|课程设计|学校项目|学术项目", text):
        return "校园项目"
    if re.search(r"自由职业|freelance|创业|创始人|合伙人|个体", text):
        return "自由职业/创业"
    if re.search(r"全职|正式|在职|有限公司|公司|集团|门店|中心|销售|客服|行政|招聘|运营", text):
        return "正式工作"
    return "待确认"


def _guess_company(lines: List[str]) -> Optional[str]:
    for line in lines[:5]:
        match = re.search(r"([一-龥A-Za-z0-9]{1,30}(?:公司|集团|有限公司|科技|门店|中心|银行|保险|教育|咨询|贸易))", line)
        if match:
            return match.group(1).strip(" -|")
    return lines[0].strip(" -|") if lines else None


def _guess_title(lines: List[str]) -> Optional[str]:
    explicit_titles = ["电话销售", "电销", "销售顾问", "销售代表", "客户经理", "大客户销售", "渠道销售", "客服专员", "行政专员", "招聘专员", "运营专员", "商务拓展", "BD"]
    for line in lines[:6]:
        for title in explicit_titles:
            if re.search(title, line, re.I):
                return title
        match = re.search(r"([一-龥A-Za-z]{0,8}(?:销售|客服|行政|招聘|运营|市场|商务|顾问|专员|经理|助理|工程师|实习生))", line, re.I)
        if match:
            return match.group(1).strip(" -|")
    return None


def _education_window(education: Optional[List[Dict]]):
    """返回教育经历的最早开始、最晚结束日期（用于判断经历是否在校期间）。"""
    starts, ends = [], []
    for edu in education or []:
        s = parse_date(edu.get("start_date"))
        e = parse_date(edu.get("end_date"))
        if s:
            starts.append(s)
        if e:
            ends.append(e)
    return (min(starts) if starts else None, max(ends) if ends else None)


def _looks_like_education(block: str) -> bool:
    """日期块是否是纯教育条目（含院校+学历、且无任何工作/职责信号）。

    避免把“2012.09-2016.06 XX大学 本科”误当成一段经历，产生虚假的低可信 P1。
    """
    has_school = bool(re.search(r"大学|学院|学校|职校|职业技术学院", block))
    has_degree = bool(re.search(r"博士|硕士|研究生|本科|大专|专科|高中|中专", block))
    has_job_signal = bool(re.search(
        r"公司|集团|门店|银行|保险|岗位|职责|负责|业绩|销售额|客户|实习|项目|运营|客服|行政|招聘",
        block,
    ))
    return has_school and has_degree and not has_job_signal


def extract_experiences(text: str, education: Optional[List[Dict]] = None) -> List[Dict]:
    edu_start, edu_end = _education_window(education)
    matches = list(DATE_RANGE_RE.finditer(text))
    experiences = []
    for idx, match in enumerate(matches):
        block_start = match.start()
        block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[block_start:block_end].strip()
        if _looks_like_education(block):
            # 纯教育条目不计入工作经历，避免虚假的低可信经历异常拉低评分。
            continue
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        header_tail = lines[0][match.end() - match.start():].strip(" -|") if lines else ""
        content_lines = [header_tail] + lines[1:] if header_tail else lines[1:]
        content_lines = [line for line in content_lines if line]
        title = _guess_title(content_lines) or ""
        company = _guess_company(content_lines)
        start_raw = match.group("start")
        end_raw = match.group("end")
        start = parse_date(start_raw)
        end = parse_date(end_raw)
        description = "\n".join(content_lines[1:]) if len(content_lines) > 1 else (content_lines[0] if content_lines else "")
        exp = {
            "type": classify_experience(block, title),
            "company": company,
            "job_title": title,
            "standardized_job_title": standardize_job_title(title),
            "start_date": start.strftime("%Y-%m-%d") if start else start_raw,
            "end_date": end.strftime("%Y-%m-%d") if end else end_raw,
            "duration_months": months_between(start, end),
            "description": description,
        }
        # 应届生识别：被判为"正式工作"但起始在教育期间内、或含兼职信号词的，降级为"实习"，
        # 不计入主工龄/年龄校验/稳定分（但仍参与岗位匹配，避免误伤候选人）。
        if exp["type"] == "正式工作":
            on_campus_by_time = bool(
                edu_end and start and start <= edu_end and (not edu_start or start >= edu_start)
            )
            if on_campus_by_time or PART_TIME_RE.search(block):
                exp["type"] = "实习"
                exp["part_time_note"] = "在校期间兼职/实习（已从正式工作降级）"
        exp["credibility_score"] = calculate_experience_credibility(exp)
        experiences.append(exp)
    detect_overlaps(experiences)
    return experiences


def calculate_parsing_confidence(candidate: Dict) -> float:
    education = candidate.get("education") or []
    has_education = any(edu.get("school") or edu.get("degree") for edu in education)
    fields = [
        candidate.get("basic_info", {}).get("name"),
        candidate.get("basic_info", {}).get("age") or candidate.get("basic_info", {}).get("birth_date"),
        candidate.get("basic_info", {}).get("phone") or candidate.get("basic_info", {}).get("email"),
        has_education,
        any(exp.get("start_date") and exp.get("end_date") for exp in candidate.get("experiences", [])),
        any(exp.get("job_title") for exp in candidate.get("experiences", [])),
    ]
    completeness = sum(1 for item in fields if item) / len(fields)
    experiences = candidate.get("experiences", [])
    low_ratio = 0 if not experiences else sum(1 for exp in experiences if exp.get("credibility_score", 0) < 0.4) / len(experiences)
    candidate["field_completeness"] = round(completeness * 100, 1)
    candidate["low_credibility_ratio"] = round(low_ratio * 100, 1)
    return round(completeness * 0.6 + (1 - low_ratio) * 0.4, 2)


def parse_resume_text(
    text: str,
    jd_text: Optional[str] = None,
    job_title: Optional[str] = None,
    pass_threshold: Optional[float] = None,
) -> Dict:
    text = normalize_text(text)
    education = extract_education(text)
    candidate = {
        "basic_info": extract_basic_info(text),
        "education": education,
        "experiences": extract_experiences(text, education=education),
        "source_text_length": len(text),
        "generation_time": datetime.now().isoformat(timespec="seconds"),
        "version": "2.1",
    }
    candidate["tenure_summary"] = calculate_tenure(candidate["experiences"])
    candidate["parsing_confidence"] = calculate_parsing_confidence(candidate)
    candidate["resume_recency"] = detect_resume_recency(text)
    run_all_validations(candidate)
    if jd_text or job_title:
        candidate["recommendation"] = recommend(candidate, jd_text, job_title, pass_threshold=pass_threshold)
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a resume into a structured HR candidate card.")
    parser.add_argument("resume", help="Path to PDF, DOCX, TXT, MD, or image resume file")
    parser.add_argument("--jd", help="JD text or path to JD text file", default="")
    parser.add_argument("--job-title", help="Target job title", default="")
    parser.add_argument(
        "--pass-threshold",
        type=float,
        default=None,
        help="证据强度免复核通过阈值（0-100），默认 75，可用环境变量 HR_PASS_THRESHOLD 覆盖",
    )
    args = parser.parse_args()

    jd_text = args.jd
    if jd_text and Path(jd_text).exists():
        jd_text = Path(jd_text).read_text(encoding="utf-8", errors="ignore")

    threshold = resolve_threshold(args.pass_threshold)
    card = parse_resume_text(
        extract_text(args.resume), jd_text=jd_text, job_title=args.job_title, pass_threshold=threshold
    )
    print(json.dumps(card, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
