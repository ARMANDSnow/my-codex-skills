# knowledge/ —— 岗位 JD 库

这里存放各招聘岗位的 JD（岗位描述），供批量/单份筛选在运行时通过 `--jd` 显式指定。
**脚本不会自动扫描本目录**；要用哪份 JD，必须在命令行把它的路径传给 `--jd`。

## 命名约定

- 每个岗位一个文件，扩展名 `.txt`，**文件名 = 岗位名**（与 `--job-title` 对应）。
  - 例：`电话销售.txt`、`大客户销售.txt`、`渠道销售.txt`。
- 一份 JD 写清：**学历要求、经验年限、核心技能/关键词、岗位职责**——脚本 `parse_jd()`
  会从中解析出最低学历、最低经验月数、技能关键词等门槛。

## 用法

```bash
# 批量筛选某目录简历，用本目录里的 JD 作门槛
python3 scripts/batch_screen_resumes.py path/to/resumes \
  --jd knowledge/电话销售.txt --job-title 电话销售

# 单份解析同理
python3 scripts/parse_resume.py path/to/resume.txt \
  --jd knowledge/电话销售.txt --job-title 电话销售
```

## 给 agent 的约定

1. 用户/HR 指明要筛的岗位后，**先来 `knowledge/` 找对应岗位的 JD 文件**，把它的**路径**作为 `--jd` 传入再运行。
2. **不要凭记忆编造 JD**。若这里没有对应岗位的 JD，就向用户确认 JD 文件位置或让其补一份，而不是默认。
3. 仅当确实没有 JD、也没传 `--job-title` 时，脚本才按“销售”通用口径兜底（此时不读取本目录）。
