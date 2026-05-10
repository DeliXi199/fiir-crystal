# FSAL Algorithm 工程规格

本文档定义 FSAL-v2 的工程接口：从带 failure vector 的候选集合构造 matched axis-aligned preference pairs，并调用可替换的 trainer 接口。第一阶段只整理数据结构、pair mining 和训练入口，不实现深度学习训练、不下载基座模型、不运行 MLIP、DFT、Materials Project、CSLLM 或其他外部 API。

## 职责边界

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `fsal.preference_data` | 定义 `PreferencePair`、`PreferenceDataset`、序列化格式 | 生成结构、计算 failure vector |
| `fsal.pair_mining` | 构造 matched axis-aligned pairs，计算质量、权重和 margin | DPO 梯度更新 |
| `fsal.losses` | 定义 standard DPO、confidence-weighted DPO、margin DPO 的接口契约 | 第一阶段不写张量实现 |
| `fsal.dpo` | 定义 `FSALTrainer` skeleton 和训练摘要 | 不实现完整训练循环 |
| `fsal.adapters` | 定义 per-axis adapter bank、model log-prob adapter 接口 | 不下载或加载真实模型 |
| `generation` | 定义 `GeneratorWrapper` 接口 | 不绑定 CrystalFormer、DiffCSP 或 OMatG 代码 |

## 输入前置条件

FSAL 只消费 `failure_taxonomy.md` 定义的 `FailureLabel`。进入 pair mining 的样本必须满足：

- `pre_filtered == false`。
- 至少一个主轴存在可比较数值。
- `calibration_tier` 在 1 到 4 之间。
- `sample_id` 可追踪到结构对象或结构引用。

Pre-filter 样本只进入统计报告，不进入 DPO preference dataset。

## 核心数据结构

### LabeledCandidate

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sample_id` | string | 候选 ID |
| `structure_ref` | string | 结构引用 |
| `failure_label` | `FailureLabel` | 完整失败标签 |
| `chemical_bucket` | string | 硬匹配桶，例如 `ABO3`、`binary_oxide`、化学体系类别 |
| `atom_count` | int | 原子数 |
| `space_group` | int or null | 可选空间群 |
| `prototype` | string or null | 可选 prototype 标签 |
| `metadata` | map | 来源模型、轮次、生成参数 |

### MatchedPairConfig

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `main_axis_threshold` | `0.3` | 主轴差值下限 |
| `other_axis_threshold` | `0.15` | 非主轴最大允许差值 |
| `atom_count_tolerance` | `0.2` | 原子数相对差不超过 20% |
| `min_structure_match_score` | `0.0` | 结构软匹配下限 |
| `min_pair_quality` | `0.3` | 低于该值的 pair 丢弃 |
| `max_pairs_per_axis` | configurable | 每个轴最大 pair 数 |
| `tier_weights` | `{1:1.0, 2:0.8, 3:0.5, 4:0.2}` | 从 calibration tier 到 label confidence |
| `failure_bucket_quota` | `near:0.6, moderate:0.3, catastrophic:0.1` | 负样本采样目标比例 |
| `axis_batch_ratio` | `F1:0.3, F2:0.3, F3:0.3, mixed:0.1` | batch 采样目标比例 |

### PreferencePair

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `pair_id` | string | 稳定可复现 ID |
| `winner_id` | string | 主轴 failure 更低的样本 |
| `loser_id` | string | 主轴 failure 更高的样本 |
| `axis` | enum | `F1_GEOMETRY`、`F2_CHEMISTRY`、`F3_STABILITY`、`MIXED` |
| `winner_failure` | map | winner 的 F1/F2/F3 摘要 |
| `loser_failure` | map | loser 的 F1/F2/F3 摘要 |
| `main_axis_gap` | float | 主轴差值 |
| `other_axis_delta` | map | 非主轴差值 |
| `other_axis_similarity` | float | `1 - mean(other_axis_delta)`，裁剪到 `[0, 1]` |
| `structure_match_score` | float | 晶系、原子数、元素重叠、prototype 等软匹配分 |
| `label_confidence` | float | 两个样本 tier weight 的较小值 |
| `pair_quality` | float | 综合质量分 |
| `margin` | float | DPO margin |
| `weight` | float | DPO pair weight，默认等于 `label_confidence` 或 `pair_quality` 的配置化组合 |
| `failure_bucket` | enum | `near_miss`、`moderate`、`catastrophic`、`mixed` |
| `metadata` | map | bucket、round、miner version、过滤原因 |

`pair_quality` 默认定义为：

`main_axis_gap * other_axis_similarity * structure_match_score * label_confidence`

### PreferenceDataset

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dataset_id` | string | 数据集 ID |
| `pairs` | list | `PreferencePair` 列表 |
| `pairs_by_axis` | map | 按 F1/F2/F3/MIXED 分组 |
| `candidate_index` | map | `sample_id -> LabeledCandidate` |
| `stats` | map | pair 数、质量分布、tier 分布、bucket 覆盖 |
| `source_round_id` | string | on-policy 轮次 |
| `config` | map | pair mining 配置快照 |

## Matched Axis-Aligned Pair Mining

Pair mining 目标：构造“主轴差异大，其他轴相近，化学/结构匹配”的偏好对，避免把 F1/F2/F3 压成单一 weighted sum。

流程：

1. 过滤 `pre_filtered == true` 样本。
2. 根据 `chemical_bucket` 分桶。桶的实现可从化学式类型、元素集合、原型标签中选择，但必须可审计。
3. 桶内按主轴值排序。
4. 只比较原子数相对差不超过 `atom_count_tolerance` 的样本。
5. 要求主轴差值不小于 `main_axis_threshold`。
6. 要求所有非主轴差值不超过 `other_axis_threshold`。
7. 计算 `structure_match_score`，至少包括原子数相似度和元素重叠；如可用，可加入晶系和 prototype 相似度。
8. 从两个样本的 `calibration_tier` 得到 `label_confidence`，取较小者。
9. 计算 `pair_quality`，低于 `min_pair_quality` 则丢弃。
10. 主轴 failure 更低者为 winner，更高者为 loser。
11. 根据 `main_axis_gap` 赋予 margin：
    - `< 0.15`：`0.1`
    - `0.15-0.4`：`0.3`
    - `>= 0.4`：`0.5`
12. 写入 `PreferenceDataset`，并记录所有过滤统计。

`MIXED` pairs 只用于 baseline 或兜底实验。主方法必须以 F1/F2/F3 axis-aligned pairs 为核心。

## Trainer 与 Loss 接口

第一阶段只定义接口，不写训练实现。

| 接口 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `GeneratorWrapper.generate` | 生成数量、seed、条件 | `CandidateRecord` 列表 | 用于 on-policy refresh；可为 mock |
| `ModelLogProbAdapter.score` | 结构引用列表 | log-prob 向量或 unavailable | DPO 需要；不支持时 trainer 应返回明确错误 |
| `DPOLossSpec.compute` | policy/reference winner/loser log-prob、weight、margin | loss 标量 | 只定义参数和返回语义 |
| `FSALTrainer.fit` | `PreferenceDataset`、policy adapter、reference adapter、训练配置 | `TrainingRunSummary` | 第一阶段可返回占位摘要 |
| `FSALTrainer.evaluate` | policy adapter、评估配置 | metric report | 调用 evaluation 接口，不直接算全部指标 |

支持的 loss 名称：

- `standard_dpo`：无 weight、无 margin，用于消融。
- `confidence_weighted_dpo`：使用 `weight`。
- `margin_dpo`：使用 `margin`。
- `cw_margin_dpo`：主方法，同时使用 `weight` 和 `margin`。

`cw_margin_dpo` 的工程输入必须包含：

- `policy_winner_logp`
- `policy_loser_logp`
- `reference_winner_logp`
- `reference_loser_logp`
- `pair_weight`
- `pair_margin`
- `beta`

## On-Policy Refresh

FSAL 最小训练闭环按轮次组织：

1. 使用当前 generator 生成候选。
2. 调用 failure labeler 得到 `FailureLabelBatch`。
3. 丢弃 pre-filter 样本，构造 F1/F2/F3 matched axis-aligned pairs。
4. 生成 `PreferenceDataset`。
5. 调用 `FSALTrainer.fit` 接口。
6. 调用 evaluation 接口记录 stable rate、failure rates、novelty、diversity、pair quality。
7. 下一轮使用更新后的 policy 重新生成、重新标注、重新配对。

第一阶段允许 trainer 不更新模型，但必须保留 round-level 输入输出和日志结构，以便后续替换为真实训练。

## 模式坍缩监控

FSAL 不只优化稳定性，还必须监控多样性。每轮训练摘要至少包含：

- composition entropy。
- unique formula rate。
- space group coverage。
- pair axis 分布。
- winner/loser 原子数分布。
- stable rate 与 failure rates。

如果连续两轮 composition entropy 下降超过 10%，trainer 配置必须能表达降低学习率、增加原始数据混入或启用 soft preference learning 的策略；第一阶段只记录建议，不实现训练逻辑。

## FIIR 最小闭环中的位置

FSAL 覆盖闭环第 3 和第 4 步：

1. 输入候选晶体结构。
2. 使用 failure taxonomy 输出 F1/F2/F3 failure vector。
3. 构造 matched axis-aligned preference pairs。
4. 调用 FSAL trainer 接口，产生训练摘要或占位模型引用。
5. 将新模型或模型引用交给 evaluation 与 discovery pipeline。

## 必须保留的实验扩展点

- binary DPO baseline。
- weighted-sum DPO baseline。
- random negative baseline。
- near-miss only / catastrophic only / mixed negative sampling。
- matched pairing vs score-aligned pairing。
- standard DPO vs CW-Margin DPO。
- on-policy vs off-policy pair refresh。
- per-axis adapter bank 或 LoRA adapter bank。
- 第二基座模型 adapter，但第一阶段不加载真实模型。

## 第一阶段验收标准

- `PreferencePair` 能完整引用 `FailureLabel`。
- Pair mining 规则能解释为什么一个 pair 被接受或过滤。
- 所有阈值和 tier weight 可配置、可记录。
- Trainer 接口不触发真实深度学习训练。
- 无外部 API、无数据集下载、无 MLIP/DFT 调用。

## 当前 Lightweight 实现说明

当前 `AxisAlignedPairMiner` 已实现轻量 matched axis-aligned preference dataset 构造：

- 输入 `LabeledCandidate`，可同时携带 `FailureLabel` 和 `FailureVector`。
- 支持 F1/F2/F3 三个 axis 的 pair mining。
- 支持 prototype match、num_atoms tolerance、可选 space group match、可选 composition family match。
- pair 输出 winner、loser、axis、margin、confidence、`match_metadata`、reason 和 failure summaries。
- pair confidence 综合 winner/loser failure confidence、main-axis margin 和结构匹配程度。
- 当前仍不实现 DPO/LoRA/adapter 训练；`FSALTrainer` 仍是可替换接口。
- `build_preference_dataset` 统一支持 `axis_aligned`、`weighted_sum`、`random_negative` 和 `binary_success_failure` 四种 pair construction mode，全部输出 `PreferencePair`，并记录 mode、reason、margin、confidence、match constraints 和 score details。
- `random_negative` 使用配置 seed 保证可复现；`weighted_sum` 支持 F1/F2/F3 权重配置。
