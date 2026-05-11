# Discovery Pipeline 工程规格

本文档定义 FIIR Crystal 的 discovery pipeline skeleton：在固定计算预算下，从 FSAL 模型或任意 generator 产生候选，经过 failure predictor、筛选、ranking、validation task metadata 和 feedback 形成主动发现闭环。第一阶段只实现接口与数据流，不运行 DFT、MLIP、CSLLM、Materials Project 或数据库 API，不下载数据集。

## 职责边界

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `discovery.pipeline` | 编排 generate -> prefilter -> screen -> rank -> export -> feedback | 具体外部计算 |
| `discovery.screening` | 定义 Failure Predictor、MLIP、synthesizability、novelty screening adapter 接口 | 第一阶段不调用真实模型/API |
| `discovery.ranking` | 多目标 ranking、Pareto layer、代表性选择 | 不把所有目标硬压成单一 `f1+f2+f3` |
| `discovery.validation` | 生成 validation task metadata，接收离线 validation result | 不生成真实 DFT 输入并提交任务 |
| `discovery.feedback` | 将验证结果回写为 failure buffer 和主动学习记录 | 不训练 predictor 或 generator |
| `evaluation` | 计算 funnel、novelty、diversity、stability 等指标 | 不负责 pipeline 编排 |

## Pipeline 输入与输出

输入：

- `GeneratorWrapper` 或离线候选列表。
- `FailureLabeler` 或 `FailurePredictor` 接口。
- 可选 screening adapters。第一阶段默认是 mock、offline 或 unavailable adapter。
- 预算配置：生成数量、Top-K、每层保留数、validation task 数。
- 可选已知结构索引，用于 novelty。该索引必须由本地文件或调用方提供。

输出：

- `DiscoveryRun`：完整运行记录。
- `RankedCandidate` 列表。
- `ValidationTask` 列表。
- `FeedbackRecord` 列表。
- evaluation metric report。

## 核心数据结构

### DiscoveryCandidate

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `candidate_id` | string | pipeline 内唯一 ID |
| `sample_id` | string | 来源候选 ID |
| `structure_ref` | string | 结构引用 |
| `source_model` | string | generator 名称 |
| `round_id` | string | active loop 轮次 |
| `failure_label` | `FailureLabel` or null | 已计算标签 |
| `predicted_failure` | map or null | Failure Predictor 输出 |
| `screening_records` | list | 各筛选层记录 |
| `ranking_record` | map or null | ranking 结果 |
| `metadata` | map | 生成参数、条件、化学空间 |

### AcquisitionScore

Failure Predictor 在 discovery 中作为 critic 和 acquisition function，不只是二元筛选器。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `utility` | float | 综合探索价值 |
| `success_score` | float | 预测成功概率或 `1 - normalized_failure` |
| `novelty_score` | float | 与已知结构的差异，`[0, 1]` |
| `diversity_score` | float | 对低频组成或结构区域的奖励 |
| `uncertainty_bonus` | float | predictor 不确定性探索奖励 |
| `cost_score` | float | 验证成本估计，越高越贵 |
| `pred_f1` | float or null | 预测 F1 |
| `pred_f2` | float or null | 预测 F2 |
| `pred_f3` | float or null | 预测 F3 |
| `metadata` | map | 权重、版本、feature 摘要 |

默认 utility 采用可配置加权：

`0.4 * success_score + 0.2 * novelty_score + 0.15 * diversity_score + 0.15 * uncertainty_bonus - 0.1 * cost_score`

### ScreeningDecision

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `layer` | string | `pre_filter`、`failure_predictor`、`mlip_adapter`、`synth_adapter`、`novelty_adapter` 等 |
| `adapter_name` | string | 适配器名称 |
| `status` | enum | `pass`、`reject`、`defer`、`unavailable` |
| `score` | float or null | 该层分数 |
| `reason` | string | 通过、拒绝或不可用原因 |
| `evidence` | map | 可审计证据 |

### RankedCandidate

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `candidate_id` | string | 候选 ID |
| `acquisition` | `AcquisitionScore` | acquisition 结果 |
| `pareto_layer` | int | 0 表示第一 Pareto front |
| `rank` | int | 最终排序 |
| `selection_reason` | string | `pareto_front`、`representative`、`near_miss_repair_candidate` 等 |
| `objectives` | map | stability、novelty、diversity、cost 等目标值 |

### ValidationTask

第一阶段只生成任务元数据，不执行真实外部计算。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | string | 验证任务 ID |
| `candidate_id` | string | 对应候选 |
| `task_type` | enum | `mlip_validation`、`dft_validation`、`novelty_check`、`synthesizability_check` |
| `priority` | int | 数字越小越优先 |
| `requested_inputs` | map | 结构引用、目标属性、建议设置 |
| `budget_tier` | enum | `cheap`、`medium`、`expensive` |
| `status` | enum | `planned`、`exported`、`completed_offline`、`failed_offline` |
| `metadata` | map | 生成时间、pipeline 版本 |

### ValidationResult

由离线计算或人工导入，不由第一阶段代码产生真实结果。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | string | 对应任务 |
| `candidate_id` | string | 候选 ID |
| `result_type` | string | `dft_e_hull`、`mlip_e_hull`、`band_gap`、`novelty`、`synth_score` 等 |
| `value` | scalar/map | 结果值 |
| `unit` | string or null | 单位 |
| `confidence` | float | `[0, 1]` |
| `provenance` | map | 结果来源、计算设置、导入时间 |

### FeedbackRecord

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `feedback_id` | string | 反馈记录 ID |
| `candidate_id` | string | 候选 ID |
| `validation_results` | list | 导入的验证结果 |
| `updated_failure_label` | `FailureLabel` or null | 根据结果更新后的标签 |
| `use_for_predictor` | bool | 是否可进入 predictor 后续训练集 |
| `use_for_fsal` | bool | 是否可进入后续 preference dataset |
| `notes` | string | 风险、异常、人工审核备注 |

## Pipeline 流程

最小 active discovery loop：

1. `generate`：从 FSAL model adapter 或离线列表获得候选。
2. `pre_filter`：调用 failure taxonomy 中的 pre-filter，记录被移除比例和原因。
3. `score`：调用 Failure Predictor 或 mock predictor，得到 predicted F1/F2/F3、uncertainty。
4. `acquire`：计算 acquisition score。
5. `screen`：按可用 adapter 追加筛选记录。不可用 adapter 必须返回 `unavailable`，不能隐式跳过。
6. `rank`：在 stability、novelty、diversity、cost 等目标上做 Pareto ranking。
7. `select`：用 Top-K、Pareto layer 和代表性选择生成 validation 候选。
8. `export_tasks`：生成 `ValidationTask` 元数据。
9. `import_results`：读取离线验证结果。
10. `feedback`：形成 `FeedbackRecord`，更新 failure buffer 和下一轮候选上下文。

## Screening Adapter 规格

| Adapter | 输入 | 输出 | 第一阶段行为 |
| --- | --- | --- | --- |
| `FailurePredictorAdapter` | `DiscoveryCandidate` | `AcquisitionScore` + `ScreeningDecision` | 可用 mock 或离线预测 |
| `MLIPValidationAdapter` | `DiscoveryCandidate` | `ScreeningDecision` / `ValidationTask` | 只生成任务，不运行 MLIP |
| `SynthesizabilityAdapter` | `DiscoveryCandidate` | `ScreeningDecision` / `ValidationTask` | 不调用 CSLLM |
| `NoveltyAdapter` | `DiscoveryCandidate` + 本地 known index | `ScreeningDecision` | 不调用 MP/ICSD/GNoME API |
| `DFTValidationAdapter` | `RankedCandidate` | `ValidationTask` | 只生成任务元数据 |

Adapter 返回 `unavailable` 时，pipeline 应继续运行并在报告中记录缺失能力。

## Ranking 规格

主 ranking 不使用单一硬阈值。默认目标：

| 目标 | 方向 | 来源 |
| --- | --- | --- |
| stability / predicted success | 越高越好 | Failure Predictor 或 failure label |
| novelty | 越高越好 | 本地 known structure index 或 adapter |
| diversity | 越高越好 | 组成频率、结构簇覆盖 |
| uncertainty | 可作为探索奖励 | Failure Predictor |
| cost | 越低越好 | 原子数、元素数、验证层级估计 |

Pareto ranking 输出 `pareto_layer`。当同一 layer 候选过多时，使用代表性选择策略，默认在目标空间上做 medoid-like selection；第一阶段可只定义接口和确定性排序。

## Near-Miss Repair 边界

Repair 是 discovery 的扩展点，不是第一阶段核心实现。

- 只允许对 `F3 near-miss` 候选生成 repair task metadata。
- 不改变化学组成。
- 不运行局部弛豫、Wyckoff 优化或 MLIP。
- repair 后的结果必须通过 `ValidationResult` 离线导入。

## FIIR 最小闭环中的位置

Discovery 使用前面模块的结果形成闭环末端：

1. 输入候选晶体结构或 FSAL 模型引用。
2. 调用 failure labeler / predictor 得到 failure score。
3. 调用 screening adapter 产生筛选记录。
4. 调用 ranking 接口做多目标排序。
5. 导出 Top-K validation task metadata。
6. 导入 validation result。
7. 写出 feedback record，供 Failure Predictor 或 FSAL 后续迭代使用。

## 第一阶段验收标准

- Pipeline 可在 mock candidates 和 mock predictor 上跑通数据流。
- 所有外部能力都通过 adapter 表达，默认不调用真实服务。
- Ranking 输出 Pareto layer、rank 和 selection reason。
- Validation 只生成任务元数据，不执行 DFT/MLIP/CSLLM。
- FeedbackRecord 能被后续 failure buffer 和 FSAL preference mining 消费。

## 当前 Lightweight 实现说明

当前 `MockDiscoveryPipeline` 已实现本地 active discovery skeleton：

- 输入 `StructureLike` / `CrystalRecord` 或已有 `DiscoveryCandidate`。
- 使用 `FailureOracle` 生成 `FailureVector` 和兼容 `FailureLabel`。
- `MockScreeningAdapter` 按 validity 和 aggregate failure score 筛选。
- `MockRanker` 使用 utility-style ranking，考虑 lower F1/F2/F3、higher confidence、validity、novelty placeholder、diversity placeholder 和简单 cost。
- `MockValidationAdapter` 只生成 validation task metadata，不运行外部验证。
- `MockFeedbackSink` 输出 top-k feedback records，包含 candidate id、selected rank、failure vector、decision、reason 和 metadata。
- `MockRanker` 当前支持 `utility` 和轻量 `pareto` ranking mode。
- `scripts/run_fiir_experiment.py` 读取配置与 JSONL 输入，输出 candidates、failure vectors、preference pairs、evaluation report、discovery ranking、feedback records、experiment summary 和 Markdown report。

## 当前 Offline Validation 与 Active Loop 实现

新增 `fiir_crystal.validation.ValidationResult` 用于导入本地 JSONL 验证结果。字段覆盖 validation source、status、validated、stable verdict、`e_above_hull`、band gap、relaxed、novelty label、synthesizability score、error message 和 metadata。导入逻辑只读文件，不运行 MLIP、DFT、Materials Project、CSLLM 或外部服务。

`fiir_crystal.feedback.FeedbackBuffer` 将 discovery feedback 和 offline validation results 转为 `FeedbackEvent`：

- stable validation -> `positive_evidence`；
- unstable 或 failed validation -> `negative_evidence`；
- pending/unknown validation -> `pending_evidence`。

`scripts/run_mock_active_loop.py` 实现 mock 多轮闭环：

1. Round 1 读取 JSONL candidates，运行完整 FIIR experiment。
2. 如果提供 validation JSONL，则导入结果并更新 feedback buffer。
3. 后续 round 不生成真实新结构，只根据 feedback buffer 对已有 mock candidates 的 metadata 进行确定性重采样/排序提示。
4. 每轮仍产出标准 experiment output directory。
5. 总输出包括 `feedback_buffer.jsonl`、`active_loop_state.json`、`active_loop_summary.json` 和 `active_loop_report.md`。

该 active loop 是工程数据流模拟，不代表真实主动学习训练。
