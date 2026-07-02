#!/usr/bin/env python3
"""resume-parser-hr 自检 + 单份诊断工具（可独立转发，零三方依赖）。

用途：当 HR 反馈"打分异常 / 多年销售被判无经验"时，先用本脚本判断到底是
  (1) 拿到的是旧版/被破坏的文件，还是 (2) 某份简历踩到解析盲区。

用法：
  # 只做自检（版本/完整性 + 引擎自测 + 已知良好回归），不需要简历：
  python3 scripts/diagnose_resume.py

  # 诊断一份真实简历（看它卡在哪一步）：
  python3 scripts/diagnose_resume.py 简历.txt --jd JD.txt --job-title 销售

  # 校验另一处安装目录（默认本脚本所在的 skill 根目录）：
  python3 scripts/diagnose_resume.py --skill-dir ~/.codex/skills/resume-parser-hr

退出码：0 全部通过；1 检测到旧版/未修复或文件被改动；2 运行出错。
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

# Windows 中文控制台默认 cp936/gbk 编不出 ✅❌⚠️ 等符号，会让 print 抛 UnicodeEncodeError
# 直接崩掉。强制 stdout/stderr 走 utf-8，编不出的字符替换而非报错（兼容旧终端）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 老版本 Python / 已被重定向时忽略
        pass

# 本脚本所在目录（scripts/），把它加入 import 路径，便于 `from parse_resume import ...`。
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

EXPECTED_VERSION = "2.4"

# 发布时生成的完整性清单（相对 skill 根目录）。任何不匹配 = 文件被改动/损坏/旧版。
# 若日后正常改了代码，用 `python3 scripts/diagnose_resume.py --emit-manifest` 重新生成本字典。
EXPECTED_SHA256 = {
    "SKILL.md": "673b6664499fbc1304835716b1bbc2b8c7d3a5e0f31ed356a8ab7ed0cb4f4691",
    "scripts/parse_resume.py": "819ac85a1211e8321bf00ffb67671eb63731dca77775a3fc127192b618c1ce4a",
    "scripts/recommendation_engine.py": "732870f76f874e58b37f2f6630dca10fd235a2e987e7db0aaf2da40bec4eb763",
    "scripts/validate_anomalies.py": "76298c20a992e19970c3f750ea4c052be840b8a93ff8a9a9210c7a684a8e17fe",
    "scripts/calculate_tenure.py": "6c7c74770b9376de9f045533864b522e854d3e8c2d09e8d7c4446519c1cd6a34",
    "scripts/standardize_job_title.py": "bc0a3f05320f9c26d7ee3e50ffcb713d1d31648bddcdca55535178433db19071",
    "scripts/batch_screen_resumes.py": "1efa92c610218d3ad27deddf98c4dd4ef042ab514d5de70714dccaca19d50cfd",
}

# 已知良好的“多年销售、描述单薄”简历（即真实世界最易踩坑的形态）。
# 修复后：relevant_months 应反映真实年限（>0），文案不得出现“无经验/0个月”。
KNOWN_GOOD_RESUME = """姓名：测试候选人
电话：13600136000
学历：本科  示例大学  2008.09-2012.06

工作经历
2012.07-2017.06  A公司  销售代表
2017.07-2023.12  B公司  销售经理
"""

# 版式回归：BOSS 直聘等无 ｜ 分隔的表头，真实岗位在正文里不出现“销售”二字，
# 不得因表头解析回退而漏判销售经验（对应 L2/L3，见 references/troubleshooting.md）。
LAYOUT_RESUMES = {
    "L2 公司/岗位/日期同一行(空格分隔)": """姓名：版式测试L2
电话：13600136001
学历：本科  测试大学  2014.09-2018.06

工作经历
测试网络技术有限公司  客户经理  2022.07-2025.07
内容：
1.客户开发与维护：对接入驻平台未合作企业HR及高管，挖掘招聘服务需求，提供年度招聘产品解决方案；
2.客户服务与续约：解决客户产品使用问题，推动续约指标达成。
""",
    "L3 岗位写在日期下一行": """姓名：版式测试L3
电话：13600136002
学历：本科  测试大学  2016.09-2020.06

工作经历
测试电子科技有限公司  2022/05-2023/05
海外业务员
上海
深入钻研全球电子产品行业，精准锁定核心目标客户，运用电话营销、定制邮件推广、实地拜访等渠道，与海外大客户建立业务合作。
""",
}

OK, BAD, WARN = "✅", "❌", "⚠️"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def emit_manifest(skill_dir: Path) -> None:
    print("EXPECTED_SHA256 = {")
    for rel in EXPECTED_SHA256:
        p = skill_dir / rel
        digest = _sha256(p) if p.exists() else "<MISSING>"
        print(f'    "{rel}": "{digest}",')
    print("}")


def check_version_and_integrity(skill_dir: Path) -> bool:
    print("—— A. 版本 / 完整性 ——")
    ok = True

    # 安装版本号（来自 parse_resume 输出）
    try:
        from parse_resume import parse_resume_text  # noqa: F401
        import parse_resume

        # version 写死在 parse_resume_text 里，跑一次拿到
        ver = parse_resume.parse_resume_text("姓名：x\n2020.01-2021.01 公司 销售").get("version")
    except Exception as exc:  # noqa: BLE001
        print(f"  {BAD} 无法导入/运行 parse_resume：{exc}（文件可能损坏）")
        return False
    flag = OK if ver == EXPECTED_VERSION else BAD
    if ver != EXPECTED_VERSION:
        ok = False
    print(f"  {flag} 安装版本 version={ver}（期望 {EXPECTED_VERSION}）")

    # git 信息（若是 git 工作树）
    try:
        head = subprocess.run(
            ["git", "-C", str(skill_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if head.returncode == 0:
            dirty = subprocess.run(
                ["git", "-C", str(skill_dir), "status", "--porcelain"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            state = "干净" if not dirty else f"有 {len(dirty.splitlines())} 个本地改动"
            print(f"  ·  git HEAD={head.stdout.strip()}（工作区{state}）")
        else:
            print("  ·  非 git 工作树（install.sh 拷贝安装），跳过 git 检查")
    except Exception:  # noqa: BLE001
        print("  ·  未检测到 git，跳过 git 检查")

    # 文件 sha256 校验
    changed, missing = [], []
    for rel, expected in EXPECTED_SHA256.items():
        p = skill_dir / rel
        if not p.exists():
            missing.append(rel)
        elif _sha256(p) != expected:
            changed.append(rel)
    if missing:
        ok = False
        print(f"  {BAD} 缺失文件：{', '.join(missing)}")
    if changed:
        ok = False
        print(f"  {BAD} 文件与发布版不一致（被改动/旧版/损坏）：{', '.join(changed)}")
    if not missing and not changed:
        print(f"  {OK} 7 个核心文件 sha256 全部与发布版一致")
    return ok


def check_engine_self_test() -> bool:
    print("—— B. 引擎自测（已知销售样例应判为有经验）——")
    try:
        from recommendation_engine import recommend
    except Exception as exc:  # noqa: BLE001
        print(f"  {BAD} 无法导入 recommendation_engine：{exc}")
        return False
    sample = {
        "basic_info": {"name": "李四", "age": 26, "phone": "13800138000"},
        "education": [{"school": "XX学院", "degree": "大专"}],
        "experiences": [
            {"type": "正式工作", "company": "A公司", "job_title": "电话销售",
             "standardized_job_title": "电话销售", "start_date": "2022.01", "end_date": "2023.08",
             "description": "负责金融产品外呼，日均拨打120通，月均转化15单，服务C端客户"},
            {"type": "正式工作", "company": "B公司", "job_title": "销售顾问",
             "standardized_job_title": "销售", "start_date": "2023.09", "end_date": "至今",
             "description": "维护客户并跟进成交，月销售额20万"},
        ],
        "parsing_confidence": 0.9,
    }
    try:
        rec = recommend(sample, "招聘电话销售，大专及以上，半年以上销售经验")
    except Exception as exc:  # noqa: BLE001
        print(f"  {BAD} 评分引擎运行报错：{exc}")
        return False
    ev = rec.get("details", {}).get("evidence", {})
    months = ev.get("relevant_months", ev.get("credible_relevant_months", 0))
    # 新模型：强样例（双段高可信销售 + 稳定 + 学历达标）匹配分应达强推荐门槛（默认 75）。
    ok = months and months > 0 and rec.get("score_100", 0) >= 75 and rec.get("tier") == "强推荐"
    print(f"  {OK if ok else BAD} 样例相关经验={months} 个月，匹配分={rec.get('score_100')}，推荐等级={rec.get('tier')}")
    if not ok:
        print(f"     {BAD} 引擎异常：已知销售样例被判经验不足/低分/未达强推荐，文件很可能损坏。")
    return bool(ok)


def check_known_good_regression() -> bool:
    print("—— C. 已知良好回归（多年销售·描述单薄，不得判无经验）——")
    try:
        from parse_resume import parse_resume_text
    except Exception as exc:  # noqa: BLE001
        print(f"  {BAD} 无法导入 parse_resume：{exc}")
        return False
    card = parse_resume_text(KNOWN_GOOD_RESUME, jd_text="招聘销售，大专及以上，1年以上销售经验", job_title="销售")
    rec = card.get("recommendation", {})
    ev = rec.get("details", {}).get("evidence", {})
    months = ev.get("relevant_months", 0)
    reason = rec.get("reason", "")
    bad_phrases = ["无销售经验", "无经验", "当前0个月", "缺少经历信息"]
    hit_bad = [p for p in bad_phrases if p in reason]
    ok = months and months >= 100 and not hit_bad
    print(f"  {OK if ok else BAD} relevant_months={months}，reason=「{reason}」")
    if not ok:
        print(f"     {BAD} 这台机器上的版本仍把多年销售判成无经验 → 是【旧版/未修复版】。")
        print(f"     ▶ 请更新：cd <my-codex-skills 仓库> && git pull && ./install.sh，然后重跑本脚本。")
    return bool(ok)


def check_layout_regression() -> bool:
    print("—— C2. 版式回归（BOSS 无 ｜ 表头：公司/岗位/日期同行 或 岗位在日期下一行）——")
    try:
        from parse_resume import parse_resume_text
    except Exception as exc:  # noqa: BLE001
        print(f"  {BAD} 无法导入 parse_resume：{exc}")
        return False
    bad_phrases = ["无销售经验", "无经验", "当前0个月", "缺少经历信息"]
    all_ok = True
    for name, resume in LAYOUT_RESUMES.items():
        card = parse_resume_text(resume, jd_text="招聘销售/客户经理，2年以上销售或客户相关经验", job_title="销售")
        rec = card.get("recommendation", {})
        ev = rec.get("details", {}).get("evidence", {})
        months = ev.get("relevant_months", 0)
        reason = rec.get("reason", "")
        hit_bad = [p for p in bad_phrases if p in reason]
        ok = bool(months and months > 0 and not hit_bad)
        all_ok = all_ok and ok
        print(f"  {OK if ok else BAD} {name}：relevant_months={months}")
        if not ok:
            print(f"     {BAD} 该版式的真实岗位未被识别为销售 → 表头解析回退（旧版/未修复）。")
    return all_ok


def diagnose_resume(resume_path: str, jd: str, job_title: str) -> None:
    print("—— D. 单份简历诊断 ——")
    from parse_resume import extract_text, parse_resume_text

    p = Path(resume_path)
    if not p.exists():
        print(f"  {BAD} 找不到文件：{resume_path}")
        return
    try:
        text = extract_text(str(p))
    except Exception as exc:  # noqa: BLE001
        print(f"  {BAD} 文本抽取失败：{exc}")
        print("     ▶ 若是 PDF/Word 缺依赖，可先另存为 .txt 再诊断。")
        return

    jd_text = jd
    if jd and Path(jd).exists():
        jd_text = Path(jd).read_text(encoding="utf-8", errors="ignore")

    card = parse_resume_text(text, jd_text=jd_text or None, job_title=job_title or None)
    exps = card.get("experiences", [])
    print(f"  解析出经历段数：{len(exps)}  | 解析置信度：{card.get('parsing_confidence')}")
    for e in exps:
        print(
            f"   · type={e.get('type')} | 原岗位='{e.get('job_title')}' "
            f"| 标准岗位='{e.get('standardized_job_title')}' "
            f"| {e.get('start_date')}~{e.get('end_date')} | 月数={e.get('duration_months')} "
            f"| 可信={e.get('credibility_score')} | 描述长度={len(e.get('description') or '')}"
        )
    rec = card.get("recommendation")
    if not rec:
        print(f"  {WARN} 未生成评分（未提供 --jd / --job-title 时不评分）。请加 --job-title 销售 重跑。")
        return
    ev = rec.get("details", {}).get("evidence", {})
    print(f"  target_job_title={rec.get('target_job_title')}")
    print(f"  relevant_months={ev.get('relevant_months')}  credible_months={ev.get('credible_relevant_months')}  high_credible={ev.get('high_credible_relevant_count')}")
    print(f"  匹配分={rec.get('score_100')}  推荐等级={rec.get('tier')}{'（'+rec.get('tier_badge')+'）' if rec.get('tier_badge') else ''}")
    print(f"  reason={rec.get('reason')}")
    print(f"  未满足强判据={rec.get('details', {}).get('unmet_strong_criteria')}")

    # 卡在哪一步——一句话定位
    print("  —— 定位 ——")
    if not exps:
        print(f"  {BAD} 没解析出任何经历：多半是日期格式/版面问题（如表格版面、英文月份）。把简历发回来排查。")
    elif (ev.get("relevant_months") or 0) == 0:
        sales_like = [e for e in exps if e.get("standardized_job_title") in
                      {"销售", "电话销售", "面销", "大客户销售", "渠道销售", "商务拓展"}]
        if not sales_like:
            print(f"  {WARN} 经历解析出来了，但标准岗位都不算销售：可能是岗位名词典没覆盖（把原岗位名发回来补词典）。")
        else:
            print(f"  {WARN} 销售经历在、但相关月数=0：检查这些段的 type 是否被归成非正式/时长是否为0。")
    else:
        print(f"  {OK} 相关经验已正确计入（{ev.get('relevant_months')} 个月）。若分数偏低多是描述单薄/稳定性/异常项所致，看 reason 与未满足项。")


def main() -> int:
    parser = argparse.ArgumentParser(description="resume-parser-hr 自检 + 单份诊断")
    parser.add_argument("resume", nargs="?", help="（可选）要诊断的简历文件 .txt/.md/.pdf/.docx")
    parser.add_argument("--jd", default="", help="JD 文本或文件路径")
    parser.add_argument("--job-title", default="销售", help="目标岗位，默认 销售")
    parser.add_argument("--skill-dir", default="", help="skill 根目录（默认本脚本所在 skill）")
    parser.add_argument("--emit-manifest", action="store_true", help="（维护用）打印当前文件 sha256 清单")
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).expanduser() if args.skill_dir else _HERE.parent

    if args.emit_manifest:
        emit_manifest(skill_dir)
        return 0

    print(f"skill 目录：{skill_dir}\n")
    a = check_version_and_integrity(skill_dir)
    print()
    b = check_engine_self_test()
    print()
    c = check_known_good_regression()
    print()
    c2 = check_layout_regression()
    print()

    if args.resume:
        try:
            diagnose_resume(args.resume, args.jd, args.job_title)
        except Exception as exc:  # noqa: BLE001
            print(f"{BAD} 诊断过程报错：{exc}")
            return 2
        print()

    verdict_ok = a and b and c and c2
    print("—— 结论 ——")
    if verdict_ok:
        print(f"{OK} 版本为最新（{EXPECTED_VERSION}）、文件完整、引擎正常。若仍有简历打分异常，请用 D 段诊断该简历并把输出发回。")
        return 0
    print(f"{BAD} 检测到问题：可能是旧版/未修复版本，或文件被改动/损坏。请按上面 ▶ 提示更新后重跑。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
