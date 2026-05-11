# Evaluation Metrics 工程规格

本文档定义 FIIR Crystal 第一阶段的评估指标、报告结构和接口边界。评估模块只消费候选、failure labels、preference datasets、discovery records 和离线导入结果；不运行深度学习训练、DFT、MLIP、Materials Project、CSLLM 或外部数据库 API。

## 职责边界

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `evaluation.failure_metrics` | failure rate、failure distribution、tier 分布、pre-filter 统计 | 标注结构 |
| `evaluation.preference_metrics` | pair quality、axis balance、near-miss 比例、confounder leakage | 构造 pair |
| `evaluation.generation_metrics` | stable rate、valid rate、unique、novel、diversity、composition entropy | 生成结构 |
| `evaluation.discovery_metrics` | funnel retention、Top-K 命中、validation task 统计、feedback 统计 | 执行验证任务 |
| `evaluation.reports` | 统一 `MetricReport` 和对比表 | 论文绘图和重型分析 |

## 核心数据结构

### MetricValue

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 指标名 |
| `value` | scalar | 指标值 |
| `unit` | string or null | 单位 |
| `direction` | enum | `higher_is_better`、`lower_is_better`、`target_range`、`diagnostic` |
| `n` | int or null | 样本量 |
| `confidence_interval` | pair or null | 可选置信区间 |
| `metadata` | map | 阈值、来源、过滤条件 |

### MetricReport

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `report_id` | string | 报告 ID |
| `scope` | enum | `failure`、`fsal`、`generation`、`discovery`、`comparison` |
| `subject_id` | string | 模型、数据集、轮次或 pipeline run ID |
| `metrics` | list | `MetricValue` 列表 |
| `tables` | map | 分组表，例如按模型或按 axis |
| `warnings` | list | 数据缺失、样本量不足、adapter unavailable |
| `config` | map | 评估阈值、匹配容差、版本 |

### ComparisonReport

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `baseline_id` | string | 基线模型或基线 run |
| `method_id` | string | 待比较方法 |
| `delta_metrics` | list | 差值或相对提升 |
| `pareto_summary` | map | stability-diversity 或多目标 Pareto 对比 |
| `significance` | map | 可选 bootstrap 或置信区间摘要 |

## Failure Metrics

| 指标 | 定义 | 方向 | 备注 |
| --- | --- | --- | --- |
| `pre_filter_rate` | pre-filter 样本数 / 总样本数 | lower | 同时报告原因分布 |
| `f1_fail_rate` | `f1_geometry >= threshold` 的比例 | lower | 默认阈值 `0.1`，可配置 |
| `f2_fail_rate` | `f2_chemistry >= threshold` 的比例 | lower | 默认阈值 `0.1` |
| `stable_rate` | `f3_stability < 0.1` 的比例 | higher | 仅统计 F3 已知样本，另报 unknown 数 |
| `near_miss_rate` | `0.1 <= f3_stability <= 0.2` 的比例 | diagnostic | FSAL 样本池质量 |
| `moderate_failure_rate` | `0.2 < f3_stability <= 0.5` 的比例 | lower |  |
| `catastrophic_failure_rate` | `f3_stability > 0.5` 或 pre-filter severe 的比例 | lower |  |
| `failure_vector_mean` | F1/F2/F3 均值 | lower | F3 单位保持 `eV/atom` |
| `failure_vector_quantiles` | F1/F2/F3 的 p10/p50/p90 | diagnostic | 观察分布形状 |
| `calibration_tier_distribution` | Tier 1-4 占比 | diagnostic | Tier 1 不应由代码伪造 |
| `uncertainty_distribution` | uncertainty 均值和分位数 | diagnostic | 用于发现低置信标签 |

F3 unknown 必须单独报告，不得当作稳定或失败静默计入。

## Preference Dataset Metrics

| 指标 | 定义 | 方向 | 用途 |
| --- | --- | --- | --- |
| `pair_count_by_axis` | F1/F2/F3/MIXED pair 数 | target_range | 检查 axis balance |
| `pair_quality_mean` | `pair_quality` 均值 | higher | 训练信号质量 |
| `pair_quality_quantiles` | p10/p50/p90 | diagnostic | 发现低质 pair |
| `main_axis_gap_mean` | 主轴差值均值 | target_range | 过小信号弱，过大可能偏 catastrophic |
| `other_axis_leakage` | 非主轴差值均值或超阈值比例 | lower | 检查 axis-aligned 是否干净 |
| `label_confidence_mean` | pair confidence 均值 | higher | 由 calibration tier 决定 |
| `tier_pair_distribution` | pair 中最低 tier 的分布 | diagnostic | 检查低置信 pair 占比 |
| `failure_bucket_ratio` | near/moderate/catastrophic pair 比例 | target_range | 默认目标 `60/30/10` |
| `chemical_bucket_coverage` | 参与 pair 的化学桶数量 | higher | 防止只覆盖少数体系 |
| `winner_loser_atom_count_shift` | winner 与 loser 原子数差分布 | lower | 检查短序列偏置 |

## Generation 与 FSAL Metrics

| 指标 | 定义 | 方向 | 备注 |
| --- | --- | --- | --- |
| `valid_rate` | 未被 pre-filter 的比例 | higher | 与 `pre_filter_rate` 互补 |
| `stable_rate_delta` | 方法 stable rate - baseline stable rate | higher | 同一评估配置下比较 |
| `f1_fail_delta` | 方法 F1 fail rate - baseline | lower | 负值表示改善 |
| `f2_fail_delta` | 方法 F2 fail rate - baseline | lower |  |
| `f3_fail_delta` | 方法 F3 fail rate - baseline | lower |  |
| `unique_formula_rate` | unique reduced formula 数 / 总样本数 | higher | 粗粒度多样性 |
| `structure_unique_rate` | 去重后结构数 / 总样本数 | higher | 依赖本地 StructureMatcher 或 adapter 结果 |
| `novel_rate` | 与训练/已知结构不匹配的比例 | higher | 只使用本地 provided index，不调用外部 DB |
| `space_group_coverage` | 出现的空间群数量或比例 | higher | 可选 |
| `composition_entropy` | reduced formula 或元素组合分布熵 | target_range | 监控 mode collapse |
| `element_coverage` | 出现元素数或目标元素覆盖率 | target_range | 依赖任务空间 |
| `pareto_front_size` | stability-diversity-novelty front 的样本数 | higher | 多目标质量 |

Novelty 和 uniqueness 的匹配容差必须写入 `MetricReport.config`。默认 StructureMatcher 容差：

- `ltol = 0.2`
- `stol = 0.3`
- `angle_tol = 5`

第一阶段若没有本地 known structure index，应报告 `novel_rate` 为 unavailable，而不是调用 Materials Project、ICSD、GNoME 或 Alexandria API。

## Discovery Metrics

| 指标 | 定义 | 方向 | 备注 |
| --- | --- | --- | --- |
| `funnel_retention_by_layer` | 每个 screening layer 的保留率 | diagnostic | 显示 generate -> rank -> validation 的流量 |
| `adapter_unavailable_count` | unavailable screening adapter 数 | lower | 第一阶段常见但必须透明 |
| `top_k_task_count` | 导出的 validation task 数 | target_range | 预算约束 |
| `task_type_distribution` | MLIP/DFT/novelty/synth task 数 | diagnostic | 不代表已执行 |
| `feedback_import_rate` | 已导入结果 task 数 / exported task 数 | higher | 离线结果回写覆盖率 |
| `offline_validated_stable_rate` | 导入结果中 DFT/MLIP stable 比例 | higher | 只基于导入结果 |
| `offline_novel_stable_count` | 同时 novel 和 stable 的导入结果数 | higher | Discovery 终端指标 |
| `acquisition_utility_distribution` | utility 的均值与分位数 | diagnostic | 监控 acquisition |
| `cost_estimate_total` | validation task 估计成本总和 | lower | 用于预算 |

## LeMat-GenBench 对齐边界

项目后续需要能输出与标准评测框架对齐的字段，但第一阶段不提交 leaderboard、不下载数据、不运行官方 evaluator。Evaluation 模块应预留字段：

- validity。
- stability。
- novelty。
- diversity。
- uniqueness。
- property-conditioned metrics。
- method metadata。

这些字段可以来自本地 adapter、mock 或离线导入结果。

## 接口契约

| 接口 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `FailureMetricComputer.compute` | `FailureLabelBatch` | `MetricReport` | 失败分布和 tier 统计 |
| `PreferenceMetricComputer.compute` | `PreferenceDataset` | `MetricReport` | pair 质量和轴平衡 |
| `GenerationMetricComputer.compute` | candidates、labels、本地 known index | `MetricReport` | 质量、多样性、新颖性 |
| `DiscoveryMetricComputer.compute` | `DiscoveryRun`、`ValidationResult` 列表 | `MetricReport` | funnel 和反馈 |
| `MetricComparator.compare` | baseline report、method report | `ComparisonReport` | 差值、相对提升、Pareto 摘要 |

所有 metric computer 必须支持缺失字段，并在 `warnings` 中说明 unavailable 指标。

## FIIR 最小闭环评估

最小闭环必须至少报告：

1. 输入候选数与 pre-filter rate。
2. F1/F2/F3 failure rates 和 stable rate。
3. Matched axis-aligned pair 数、axis 分布、pair quality。
4. FSAL trainer 调用后的训练摘要占位指标。
5. Novelty、diversity、composition entropy。
6. Discovery funnel retention、Top-K validation task 数、feedback record 数。

## 第一阶段验收标准

- 所有指标能基于本地对象或 mock/offline 结果计算。
- F3 unknown、新颖性 unavailable、外部 adapter unavailable 都被显式报告。
- Metric report 可序列化，并包含阈值和匹配容差。
- 评估不触发训练、MLIP、DFT、外部 API 或数据下载。
- 指标足以支撑 FSAL 消融：binary vs weighted-sum vs axis-aligned、standard DPO vs CW-Margin、matched vs score-aligned、on-policy vs off-policy。

## 当前 Lightweight 实现说明

当前 `EvaluationReport` 已覆盖可配置 mock 实验需要的核心指标：

- candidate count、valid rate、failure rate、hard failure count；
- average/max F1/F2/F3；
- calibration tier distribution；
- pair count、pairs by axis、pairs by mode；
- average pair margin、average pair confidence、valid pair ratio；
- top-k average failure、top-k valid rate、ranking utility stats。
- validation metrics availability、validation count、validation success rate；
- validated stable count/rate、average validated `e_above_hull`；
- validated novel count/rate、validation failure count；
- top-k validated stable rate、top-k validation coverage。

报告支持 JSON 输出，并被 experiment runner 和 Markdown report generator 复用。

如果未提供 offline validation results，validation-aware metrics 会显式标记为 unavailable；评估不会报错，也不会隐式调用任何外部验证能力。
