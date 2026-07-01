# 候选人卡片（填空模板）

> 用法：这是给模型**照着填**的示意模板，不是自动渲染引擎。把 `<...>` 替换成脚本 JSON 里对应字段的值；
> 列表型（教育、经历、空窗明细、异常）按实际条数**逐条重复**那一行/那一节。
> 所有数值直接取自脚本输出，**不要自己改算**；字段缺失就写“未说明”。

## 基本信息
- 姓名：<basic_info.name>
- 年龄：<basic_info.age>
- 联系方式：<basic_info.phone> / <basic_info.email>
- 出生日期：<basic_info.birth_date>
- 语言：<basic_info.languages>（未提及为“未说明”）

## HR 快筛结论
> 推荐等级由匹配分单调推导，二者永远一致：`🟢 强推荐` ≥ 门槛（默认 75）；`🟡 待审核` 门槛-10 起（默认 65–75）；
> `🟠 谨慎` 门槛-20 起；`🔴 不推荐` 更低。存在 P0 数据红旗时等级后带 `⚠️`，只提示不改变分档。
- 匹配分：<recommendation.score_100> / 100
- 推荐等级：<recommendation.tier_display>（强推荐门槛 <recommendation.pass_threshold>）
- 目标岗位：<recommendation.target_job_title>
- P0 高亮（有 ⚠️ 徽标时非空，请加粗呈现）：**<recommendation.p0_remark>**
- 推荐理由：<recommendation.reason>
- 置信度：<recommendation.confidence>

## 销售证据
- 中高可信相关经验：<recommendation.details.evidence.credible_relevant_months> 个月
- 高可信相关经历数：<recommendation.details.evidence.high_credible_relevant_count>
- 未满足强判据：<recommendation.details.unmet_strong_criteria>
- 降权因子：<recommendation.details.downgrade_factors>

## 工龄拆分
- 正式工作：<tenure_summary.full_time_months> 个月（<tenure_summary.full_time_years> 年）
- 实习：<tenure_summary.internship_months> 个月
- 校园项目：<tenure_summary.project_months> 个月
- 自由职业/创业：<tenure_summary.freelance_months> 个月
- 待确认：<tenure_summary.pending_months> 个月

## 稳定性与 Gap
- 履历稳定分：<stability_scores.stability_score>（<stability_scores.stability_label>）
- Gap 分：<stability_scores.gap_score>（<stability_scores.gap_label>）
- Gap 分构成：<stability_scores.gap_score_breakdown>
- Gap 总体说明：<stability_scores.gap_summary>
- 平均在岗月数：<stability_scores.stability_metrics.avg_duration_months>
- 中位在岗月数：<stability_scores.stability_metrics.median_duration_months>
- 最近两段平均在岗月数：<stability_scores.stability_metrics.recent_2_avg_months>
- 短任职段数：<stability_scores.stability_metrics.short_tenure_count>
- 近 5 年 Gap：<stability_scores.gap_metrics.recent_5y_gap_months> 个月
- 最长 Gap：<stability_scores.gap_metrics.longest_gap_months> 个月

### 空窗明细（逐段说明）
（按 stability_scores.gap_details 每段一行，直接复制该段的 note 字段；没有空窗时改写一行：照抄 stability_scores.gap_summary）
- <gap_details[0].note>
- <gap_details[1].note>

## 教育背景
（按 education 每条一行）
- <education[0].school> / <education[0].degree> / <education[0].major> / <education[0].start_date> 至 <education[0].end_date>

## 经历明细
（按 experiences 每段一节）
### <experiences[0].company>（<experiences[0].type>）
- 岗位：<experiences[0].job_title>（标准化：<experiences[0].standardized_job_title>）
- 时间：<experiences[0].start_date> 至 <experiences[0].end_date>（<experiences[0].duration_months> 个月）
- 可信度：<experiences[0].credibility_score>（<experiences[0].credibility_level>）
- 重叠标记：<experiences[0].overlap_tag>
- 描述：<experiences[0].description>

## 异常与复核动作
（按 anomalies 每条一行；带“不参与评分”的属合规/提醒类，不影响分数）
- [<anomalies[0].level>] <anomalies[0].type>：<anomalies[0].description>；动作：<anomalies[0].action>

## 解析质量
- 解析置信度：<parsing_confidence>
- 字段完整度：<field_completeness>%
- 低可信经历比例：<low_credibility_ratio>%
- 简历时效：最新信息为 <resume_recency.latest_year_in_text> 年（距今约 <resume_recency.years_since_latest> 年）；当 resume_recency.is_stale 为 true 时按“简历信息可能未更新”在异常区与总结中提醒
- 生成时间：<generation_time>

## 总结（可选附表）
> 需要时附下表；数值一律取自脚本 JSON，缺失项写“未说明”，不要自己填数。
> 简历时效一栏：is_stale 为 true 写“⚠️ 可能未更新，建议确认近况”，否则写“较新”。

| 项目 | 内容 |
| --- | --- |
| 候选人 | <basic_info.name> |
| 匹配分 | <recommendation.score_100> / 100 |
| 推荐等级 | <recommendation.tier_display>（门槛 <recommendation.pass_threshold>） |
| P0 高亮 | **<recommendation.p0_remark>**（无则写“无”） |
| 正式工龄 | <tenure_summary.full_time_years> 年 |
| 履历稳定分 | <stability_scores.stability_score>（<stability_scores.stability_label>） |
| Gap 分 | <stability_scores.gap_score>（<stability_scores.gap_label>） |
| Gap 说明 | <stability_scores.gap_summary> |
| 简历时效 | 最新 <resume_recency.latest_year_in_text> 年；<较新 或 ⚠️ 可能未更新，建议确认近况> |
| 语言 | <basic_info.languages> |
| 解析置信度 | <parsing_confidence> |
| 需人工复核 | <recommendation.details.unmet_strong_criteria> / 见异常区 |
