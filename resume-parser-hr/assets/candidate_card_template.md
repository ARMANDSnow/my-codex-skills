# 候选人卡片

## 基本信息
- 姓名：{{basic_info.name}}
- 年龄：{{basic_info.age}}
- 联系方式：{{basic_info.phone}} / {{basic_info.email}}
- 出生日期：{{basic_info.birth_date}}

## HR 快筛结论
- 推荐等级：{{recommendation.result}}
- 目标岗位：{{recommendation.target_job_title}}
- 推荐理由：{{recommendation.reason}}
- 综合评分：{{recommendation.score}}
- 置信度：{{recommendation.confidence}}

## 销售证据
- 中高可信相关经验：{{recommendation.details.evidence.credible_relevant_months}} 个月
- 高可信相关经历数：{{recommendation.details.evidence.high_credible_relevant_count}}
- 未满足强判据：{{recommendation.details.unmet_strong_criteria}}
- 降权因子：{{recommendation.details.downgrade_factors}}

## 工龄拆分
- 正式工作：{{tenure_summary.full_time_months}} 个月（{{tenure_summary.full_time_years}} 年）
- 实习：{{tenure_summary.internship_months}} 个月
- 校园项目：{{tenure_summary.project_months}} 个月
- 自由职业/创业：{{tenure_summary.freelance_months}} 个月
- 待确认：{{tenure_summary.pending_months}} 个月

## 稳定性与 Gap
- 履历稳定分：{{stability_scores.stability_score}}（{{stability_scores.stability_label}}）
- Gap 分：{{stability_scores.gap_score}}（{{stability_scores.gap_label}}）
- 平均在岗月数：{{stability_scores.stability_metrics.avg_duration_months}}
- 中位在岗月数：{{stability_scores.stability_metrics.median_duration_months}}
- 最近两段平均在岗月数：{{stability_scores.stability_metrics.recent_2_avg_months}}
- 短任职段数：{{stability_scores.stability_metrics.short_tenure_count}}
- 近 5 年 Gap：{{stability_scores.gap_metrics.recent_5y_gap_months}} 个月
- 最长 Gap：{{stability_scores.gap_metrics.longest_gap_months}} 个月

## 教育背景
{{#each education}}
- {{school}} / {{degree}} / {{major}} / {{start_date}} 至 {{end_date}}
{{/each}}

## 经历明细
{{#each experiences}}
### {{company}}（{{type}}）
- 岗位：{{job_title}}（标准化：{{standardized_job_title}}）
- 时间：{{start_date}} 至 {{end_date}}（{{duration_months}} 个月）
- 可信度：{{credibility_score}}（{{credibility_level}}）
- 重叠标记：{{overlap_tag}}
- 描述：{{description}}
{{/each}}

## 异常与复核动作
{{#each anomalies}}
- [{{level}}] {{type}}：{{description}}；动作：{{action}}
{{/each}}

## 解析质量
- 解析置信度：{{parsing_confidence}}
- 字段完整度：{{field_completeness}}%
- 低可信经历比例：{{low_credibility_ratio}}%
- 生成时间：{{generation_time}}
