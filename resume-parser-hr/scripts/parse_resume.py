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
    from .recommendation_engine import recommend
    from .standardize_job_title import standardize_job_title
    from .validate_anomalies import calculate_experience_credibility, run_all_validations
except ImportError:
    from calculate_tenure import calculate_tenure, detect_overlaps, months_between, parse_date
    from recommendation_engine import recommend
    from standardize_job_title import standardize_job_title
    from validate_anomalies import calculate_experience_credibility, run_all_validations


DATE_RANGE_RE = re.compile(
    r"(?P<start>(?:19|20)\d{2}[./年-]?\s*\d{0,2}月?)\s*[-~至到—–]+\s*(?P<end>至今|现在|目前|present|now|(?:19|20)\d{2}[./年-]?\s*\d{0,2}月?)",
    re.I,
)
PHONE_RE = re.compile(r"(?:(?:手机|电话|联系方式)[:：]?\s*)?((?:\+?86[-\s]?)?1[3-9]\d[-\s]?\d{4}[-\s]?\d{4})")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


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
        with pdfplumber.open(str(file_path)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    raise RuntimeError(f"暂不支持文件类型：{suffix}")


def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_basic_info(text: str) -> Dict:
    info = {"name": None, "age": None, "phone": None, "email": None, "birth_date": None}
    name_match = re.search(r"(?:姓名|名字)[:：]\s*([\u4e00-\u9fa5A-Za-z]{2,20})", text)
    if name_match:
        info["name"] = name_match.group(1)
    else:
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", first_line):
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
    return info


def extract_education(text: str) -> List[Dict]:
    degrees = "博士|硕士|研究生|本科|大专|专科|高中|中专"
    schools = re.findall(r"([\u4e00-\u9fa5A-Za-z]{2,30}(?:大学|学院|学校|职业技术学院|职校))", text)
    degree_match = re.search(degrees, text)
    major_match = re.search(r"专业[:：]\s*([\u4e00-\u9fa5A-Za-z]{2,30})", text)
    if not major_match:
        major_match = re.search(r"([\u4e00-\u9fa5A-Za-z]{2,20})专业", text)
    if not schools and not degree_match:
        return []
    degree = degree_match.group(0) if degree_match else None
    if degree == "专科":
        degree = "大专"
    if degree == "研究生":
        degree = "硕士"
    return [{
        "school": schools[0] if schools else None,
        "degree": degree,
        "major": major_match.group(1) if major_match else None,
        "start_date": None,
        "end_date": None,
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
        match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{1,30}(?:公司|集团|有限公司|科技|门店|中心|银行|保险|教育|咨询|贸易))", line)
        if match:
            return match.group(1).strip(" -|")
    return lines[0].strip(" -|") if lines else None


def _guess_title(lines: List[str]) -> Optional[str]:
    explicit_titles = ["电话销售", "电销", "销售顾问", "销售代表", "客户经理", "大客户销售", "渠道销售", "客服专员", "行政专员", "招聘专员", "运营专员", "商务拓展", "BD"]
    for line in lines[:6]:
        for title in explicit_titles:
            if re.search(title, line, re.I):
                return title
        match = re.search(r"([\u4e00-\u9fa5A-Za-z]{0,8}(?:销售|客服|行政|招聘|运营|市场|商务|顾问|专员|经理|助理|工程师|实习生))", line, re.I)
        if match:
            return match.group(1).strip(" -|")
    return None


def extract_experiences(text: str) -> List[Dict]:
    matches = list(DATE_RANGE_RE.finditer(text))
    experiences = []
    for idx, match in enumerate(matches):
        block_start = match.start()
        block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[block_start:block_end].strip()
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
        exp["credibility_score"] = calculate_experience_credibility(exp)
        experiences.append(exp)
    detect_overlaps(experiences)
    return experiences


def calculate_parsing_confidence(candidate: Dict) -> float:
    fields = [
        candidate.get("basic_info", {}).get("name"),
        candidate.get("basic_info", {}).get("age") or candidate.get("basic_info", {}).get("birth_date"),
        candidate.get("basic_info", {}).get("phone") or candidate.get("basic_info", {}).get("email"),
        candidate.get("education"),
        any(exp.get("start_date") and exp.get("end_date") for exp in candidate.get("experiences", [])),
        any(exp.get("job_title") for exp in candidate.get("experiences", [])),
    ]
    completeness = sum(1 for item in fields if item) / len(fields)
    experiences = candidate.get("experiences", [])
    low_ratio = 0 if not experiences else sum(1 for exp in experiences if exp.get("credibility_score", 0) < 0.4) / len(experiences)
    candidate["field_completeness"] = round(completeness * 100, 1)
    candidate["low_credibility_ratio"] = round(low_ratio * 100, 1)
    return round(completeness * 0.6 + (1 - low_ratio) * 0.4, 2)


def parse_resume_text(text: str, jd_text: Optional[str] = None, job_title: Optional[str] = None) -> Dict:
    text = normalize_text(text)
    candidate = {
        "basic_info": extract_basic_info(text),
        "education": extract_education(text),
        "experiences": extract_experiences(text),
        "source_text_length": len(text),
        "generation_time": datetime.now().isoformat(timespec="seconds"),
        "version": "2.0",
    }
    candidate["tenure_summary"] = calculate_tenure(candidate["experiences"])
    candidate["parsing_confidence"] = calculate_parsing_confidence(candidate)
    run_all_validations(candidate)
    if jd_text or job_title:
        candidate["recommendation"] = recommend(candidate, jd_text, job_title)
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a resume into a structured HR candidate card.")
    parser.add_argument("resume", help="Path to PDF, DOCX, TXT, or MD resume file")
    parser.add_argument("--jd", help="JD text or path to JD text file", default="")
    parser.add_argument("--job-title", help="Target job title", default="")
    args = parser.parse_args()

    jd_text = args.jd
    if jd_text and Path(jd_text).exists():
        jd_text = Path(jd_text).read_text(encoding="utf-8", errors="ignore")

    card = parse_resume_text(extract_text(args.resume), jd_text=jd_text, job_title=args.job_title)
    print(json.dumps(card, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
