# Failure Taxonomy 工程规格

本文档定义 FIIR Crystal 的失败标注工程契约。目标是让任意候选晶体结构得到标准化、可序列化、可被 FSAL 和 Discovery 复用的 failure vector。本文档不要求实现深度学习训练、DFT、MLIP 调用、Materials Project API、CSLLM 或任何外部数据下载。

## 职责边界

`fiir_crystal.failure` 负责把候选结构转为失败标签，不负责训练生成模型或执行发现 pipeline。

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `failure.taxonomy` | 定义 F1-F5 轴、Calibration Tier、严重度区间、数据结构字段 | 具体检测算法 |
| `failure.geometry` | 计算 F1 几何合法性规则分数 | 化学价态、稳定性、MLIP |
| `failure.chemistry` | 计算 F2 化学合法性规则分数 | 热力学稳定性、数据库查询 |
| `failure.stability` | 接收外部或本地适配器提供的能量/`E_above_hull` 结果并标准化为 F3 | 第一阶段不直接运行 MLIP、DFT 或 Materials Project API |
| `failure.labeler` | 编排 pre-filter、F1/F2/F3、可选 F4/F5、tier、metadata，输出 `FailureLabel` | pair mining、DPO、ranking |
| `predictor` | 定义 Failure Predictor 的训练/推理接口 | 第一阶段不实现 GNN 训练 |

## 失败轴定义

F1-F5 是完整的 failure representation，但角色不同：F1/F2/F3 是 FSAL 训练主轴；F4 用于泄漏/novelty 约束和 pair 前过滤；F5 用于 discovery 筛选和后验分析，不进入 DPO loss。

| 轴 | 字段 | 范围与单位 | 方向 | 角色 |
| --- | --- | --- | --- | --- |
| F1 | `f1_geometry` | `[0, 1]`，无单位 | 越低越好 | 几何合法性，训练主轴 |
| F2 | `f2_chemistry` | `[0, 1]`，无单位 | 越低越好 | 化学合法性，训练主轴 |
| F3 | `f3_stability` | `eV/atom`，可为空 | 越低越好 | 热力学稳定性，训练主轴 |
| F4 | `f4_novelty_leakage` | `[0, 1]`，可为空 | 越低越好 | novelty/leakage 风险；用于过滤、benchmark 可信度和评估 |
| F5 | `f5_synthesizability` | `[0, 1]`，可为空 | 越低越好 | 可合成性失败风险；用于 discovery 筛选和评估 |

F3 的稳定性区间：

| 区间 | 条件 | 标签 |
| --- | --- | --- |
| stable | `f3_stability < 0.1` | 可作为 winner 候选 |
| near-miss | `0.1 <= f3_stability <= 0.2` | FSAL 优先负样本 |
| moderate | `0.2 < f3_stability <= 0.5` | 中等失败 |
| catastrophic | `f3_stability > 0.5` | 严重失败 |
| unknown | `f3_stability is null` | F3 不可用于稳定性判定 |

F1/F2/F4/F5 的默认严重度区间：

| 区间 | 条件 |
| --- | --- |
| pass | `< 0.1` |
| mild | `0.1-0.3` |
| moderate | `0.3-0.7` |
| severe | `> 0.7` |

## Pre-filter 规格

Pre-filter 用于在 FSAL pair 构造前移除明显非法结构。这些结构仍要进入 benchmark 统计，但不得进入 DPO preference dataset。

| 检查 | 默认阈值 | `reject_reason` |
| --- | --- | --- |
| 空结构 | 原子数为 0 | `empty_structure` |
| 原子重叠 | 任意非零原子间距 `< 0.5 Å` | `atom_overlap` |
| 极端晶格角 | 任一角 `< 20°` 或 `> 160°` | `extreme_angle` |
| 异常密度 | `< 0.5 g/cm3` 或 `> 25 g/cm3` | `abnormal_density` |
| 解析失败 | 结构对象缺少必要晶格、坐标、元素信息 | `parse_error` |
| F4 泄漏风险过高 | `f4_novelty_leakage` 高于配置阈值 | `leakage_risk` |

## 核心数据结构

### CandidateRecord

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sample_id` | string | 是 | 全局唯一或批内唯一 ID |
| `structure` | object/ref | 是 | 晶体结构对象或可解析引用，具体类型由 adapter 决定 |
| `source_model` | string | 否 | 生成该结构的模型名 |
| `round_id` | string | 否 | semi-on-policy 迭代轮次 |
| `metadata` | map | 否 | 生成温度、seed、原始文件路径、离线 F4/F5 证据等 |

### FailureScore

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `axis` | enum | `F1_GEOMETRY`、`F2_CHEMISTRY`、`F3_STABILITY`、`F4_NOVELTY_LEAKAGE`、`F5_SYNTHESIZABILITY` |
| `value` | float or null | 分数、风险值或 `E_above_hull` |
| `unit` | string | F1/F2/F4/F5 为 `unitless`，F3 为 `eV/atom` |
| `severity` | enum | `pass`、`mild`、`moderate`、`severe`、`unknown` |
| `confidence` | float | `[0, 1]`，该轴标签可信度 |
| `uncertainty` | float or null | 估计不确定性 |
| `evidence` | map | 子检查结果、外部适配器摘要 |
| `unavailable_reason` | string or null | 该轴不可计算时的原因 |

### FailureLabel / FailureVector

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sample_id` | string | 对应 `CandidateRecord.sample_id` |
| `structure_ref` | string | 结构引用或序列化位置 |
| `f1_geometry` | float | `[0, 1]` |
| `f2_chemistry` | float | `[0, 1]` |
| `f3_stability` | float or null | `E_above_hull`，单位 `eV/atom` |
| `f4_novelty_leakage` | float or null | 泄漏/近重复风险；低值表示更 novel/更可信 |
| `f5_synthesizability` | float or null | 可合成性失败风险；低值表示更可能可合成 |
| `axis_scores` | list | 可审计的 `FailureScore` 证据 |
| `uncertainty` | float | 聚合不确定性 |
| `confidence` | float | 聚合置信度 |
| `calibration_tier` | int | 1、2、3、4；0 仅用于 invalid/hard failure |
| `tier_source` | string | `dft_provided`、`multi_adapter_agreement`、`single_adapter`、`rules_only`、`disagreement` 等 |
| `pre_filtered` | bool | 是否被 pre-filter 判为明显非法 |
| `reject_reason` | string or null | pre-filter 原因 |
| `is_stable` / `is_near_miss` / `is_moderate` / `is_catastrophic` | bool/null | F3 派生状态 |
| `metadata` | map | scorer 版本、阈值、时间戳、离线证据来源等 |

## Calibration Tier

Calibration Tier 决定 FSAL pair confidence。第一阶段只允许消费已提供的校准或适配器结果，不主动运行 DFT/MLIP/API。

| Tier | 来源 | 默认置信权重 | 说明 |
| --- | --- | --- | --- |
| 1 | `dft_provided` | 1.0 | DFT 或等价高保真验证，最可靠 |
| 2 | `multi_adapter_agreement` | 0.8 | 多个独立 oracle 一致 |
| 3 | `single_adapter` | 0.5 | 单代理 + 规则一致，或 chemistry-aware discount 后降级 |
| 4 | `rules_only` / `disagreement` / `mock_only` | 0.2 | 仅规则、mock、F3 缺失或 oracle 分歧大 |
| 0 | `invalid` | 0.0 | 明显非法结构；只用于工程 sentinel，不是论文 tier |

Tier 不能伪造来源：没有 DFT 结果时不得标为 Tier 1；没有外部稳定性结果时 F3 应为 `null` 或来自 mock/test adapter，并明确 `tier_source`。

## 接口契约

| 接口 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `PreFilter.check` | `CandidateRecord` | `PreFilterResult` | 判断明显非法结构 |
| `GeometryScorer.score` | `CandidateRecord` | `FailureScore` | 输出 F1 |
| `ChemistryScorer.score` | `CandidateRecord` | `FailureScore` | 输出 F2 |
| `StabilityScorer.score` | `CandidateRecord` + 已提供的稳定性结果 | `FailureScore` | 输出 F3；不得自行调用外部计算 |
| `NoveltyLeakageScorer.score` | `CandidateRecord` + 本地 known index/离线证据 | `FailureScore` | 输出 F4；不得调用外部数据库 |
| `SynthesizabilityScorer.score` | `CandidateRecord` + 离线模型结果 | `FailureScore` | 输出 F5；不得调用 CSLLM |
| `FailureLabeler.label` | `CandidateRecord` | `FailureLabel` | 单结构完整标注 |
| `FailurePredictor.predict` | `CandidateRecord` | F1-F5 预测和不确定性 | 第一阶段可用 mock/offline |

接口必须可替换：真实 scorer、mock scorer、离线结果 reader 应能共享同一输出结构。

## FIIR 最小闭环中的位置

1. 输入候选晶体结构。
2. 计算或导入 F1-F5 failure vector；F4/F5 可为空。
3. 将非 pre-filter 样本交给 FSAL 构造 matched F1/F2/F3 axis-aligned preference pairs。
4. 将 F4 用作 pair 前过滤或 pair quality 因子；F5 不进入 DPO。
5. 将标签统计交给 evaluation metrics。
6. 将标签和预测接口交给 discovery pipeline 做 screening、ranking 和 feedback。

## 第一阶段验收标准

- F1/F2/F3、uncertainty、confidence、calibration tier 字段完整。
- F4/F5 字段可序列化、可为空、可由离线证据或 metadata 填充。
- F3/F4/F5 不可用时不会触发外部 API 或真实 MLIP/DFT/CSLLM。
- 同一 `FailureLabel` 可直接被 `fsal_algorithm.md` 的 `PreferencePair` 引用。
- 规格支持 mock/test scorer，因此不依赖大型数据集或外部服务。

## 当前 Lightweight 实现说明

当前代码已实现一个不依赖 pymatgen/ASE/MLIP/DFT 的轻量闭环：

- `FailureOracle` 直接计算 F1/F2/F3，并从 metadata 透传可选 F4/F5。
- `FailureVector` / `FailureLabel` 已支持可选 `f4_novelty_leakage` 和 `f5_synthesizability`。
- FSAL pair mining 只在 F1/F2/F3 上构造训练 pair；F4 可作为可选过滤和 pair quality 因子。
- 当前实际 tier 逻辑为：tier 0 invalid/hard failure，tier 4 mock/rules/unavailable，tier 3 local rule-based fallback；tier 1/2 保留给未来 DFT 或多 oracle 离线证据。
- `fiir_crystal.validation.ValidationResult` 可以离线导入未来 MLIP/DFT/人工验证结果，并通过 `candidate_id` 与 `FailureVector`、ranking 和 feedback 记录 join。
