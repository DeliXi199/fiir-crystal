# Failure Taxonomy 工程规格

本文档定义 FIIR Crystal 第一阶段的失败标注工程契约。目标是让任意候选晶体结构得到标准化、可序列化、可被 FSAL 和 Discovery 复用的 failure vector。本文档不是论文介绍，也不要求实现深度学习训练、DFT、MLIP 调用、Materials Project API 或任何外部数据下载。

## 职责边界

`fiir_crystal.failure` 负责把候选结构转为失败标签，不负责训练生成模型或执行发现 pipeline。

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `failure.taxonomy` | 定义 F1/F2/F3 轴、Calibration Tier、严重度区间、数据结构字段 | 具体检测算法 |
| `failure.geometry` | 计算 F1 几何合法性规则分数 | 化学价态、稳定性、MLIP |
| `failure.chemistry` | 计算 F2 化学合法性规则分数 | 热力学稳定性、数据库查询 |
| `failure.stability` | 接收外部或本地适配器提供的能量/`E_above_hull` 结果并标准化为 F3 | 第一阶段不直接运行 MLIP、DFT 或 Materials Project API |
| `failure.labeler` | 编排 pre-filter、F1/F2/F3、tier、metadata，输出 `FailureLabel` | pair mining、DPO、ranking |
| `predictor` | 定义 Failure Predictor 的训练/推理接口 | 第一阶段不实现 GNN 训练 |

## 失败轴定义

| 轴 | 字段 | 范围与单位 | 方向 | 用途 |
| --- | --- | --- | --- | --- |
| F1 | `f1_geometry` | `[0, 1]`，无单位 | 越低越好 | 原子重叠、晶格角异常、密度异常、基础结构合法性 |
| F2 | `f2_chemistry` | `[0, 1]`，无单位 | 越低越好 | 电荷平衡、价态可行性、配位合理性、SMACT/BVS/CrystalNN 类规则接口 |
| F3 | `f3_stability` | `eV/atom`，可为空 | 越低越好 | 热力学稳定性，通常表示 `E_above_hull` |

F3 的稳定性区间：

| 区间 | 条件 | 标签 |
| --- | --- | --- |
| stable | `f3_stability < 0.1` | 可作为 winner 候选 |
| near-miss | `0.1 <= f3_stability <= 0.2` | FSAL 优先负样本 |
| moderate | `0.2 < f3_stability <= 0.5` | 中等失败 |
| catastrophic | `f3_stability > 0.5` | 严重失败 |
| unknown | `f3_stability is null` | F3 不可用于稳定性判定 |

F1/F2 的默认严重度区间：

| 区间 | 条件 |
| --- | --- |
| pass | `< 0.1` |
| mild | `0.1-0.3` |
| moderate | `0.3-0.7` |
| severe | `> 0.7` |

## Pre-filter 规格

Pre-filter 用于在 FSAL pair 构造前移除明显非法结构。这些结构仍要进入 benchmark 统计，但不得进入 DPO 训练。

| 检查 | 默认阈值 | `reject_reason` |
| --- | --- | --- |
| 空结构 | 原子数为 0 | `empty_structure` |
| 原子重叠 | 任意非零原子间距 `< 0.5 Å` | `atom_overlap` |
| 极端晶格角 | 任一角 `< 20°` 或 `> 160°` | `extreme_angle` |
| 异常密度 | `< 0.5 g/cm3` 或 `> 25 g/cm3` | `abnormal_density` |
| 解析失败 | 结构对象缺少必要晶格、坐标、元素信息 | `parse_error` |

Pre-filter 输出 `PreFilterResult`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `is_valid` | bool | 是否允许继续标注和进入 pair mining |
| `reject_reason` | string or null | 上表枚举值 |
| `evidence` | map | 最小距离、异常角、密度等可审计值 |

## 核心数据结构

### CandidateRecord

候选结构在 failure 模块中的最小输入记录。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sample_id` | string | 是 | 全局唯一或批内唯一 ID |
| `structure` | object/ref | 是 | 晶体结构对象或可解析引用，具体类型由 adapter 决定 |
| `source_model` | string | 否 | 生成该结构的模型名 |
| `round_id` | string | 否 | on-policy 迭代轮次 |
| `metadata` | map | 否 | 生成温度、seed、原始文件路径等 |

### FailureScore

单个失败轴的可审计输出。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `axis` | enum | `F1_GEOMETRY`、`F2_CHEMISTRY`、`F3_STABILITY` |
| `value` | float or null | 分数或 `E_above_hull` |
| `unit` | string | F1/F2 为 `unitless`，F3 为 `eV/atom` |
| `severity` | enum | `pass`、`mild`、`moderate`、`severe`、`unknown` |
| `confidence` | float | `[0, 1]`，该轴标签可信度 |
| `uncertainty` | float or null | 估计不确定性 |
| `evidence` | map | 子检查结果、外部适配器摘要 |
| `unavailable_reason` | string or null | 该轴不可计算时的原因 |

### FailureLabel

单个候选结构的完整失败标签。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sample_id` | string | 对应 `CandidateRecord.sample_id` |
| `structure_ref` | string | 结构引用或序列化位置 |
| `f1_geometry` | float | `[0, 1]` |
| `f2_chemistry` | float | `[0, 1]` |
| `f3_stability` | float or null | `E_above_hull`，单位 `eV/atom` |
| `f3_normalized` | float or null | 可选的 `[0, 1]` 稳定性归一化分数 |
| `axis_scores` | list | 三个 `FailureScore` 的详细证据 |
| `uncertainty` | float | 聚合不确定性；默认来自 F3 ensemble disagreement 或适配器 |
| `confidence` | float | 聚合置信度 |
| `calibration_tier` | int | 1、2、3、4 |
| `tier_source` | string | `dft_provided`、`multi_adapter_agreement`、`single_adapter`、`rules_only`、`disagreement` |
| `pre_filtered` | bool | 是否被 pre-filter 判为明显非法 |
| `reject_reason` | string or null | pre-filter 原因 |
| `is_stable` | bool or null | F3 已知时是否 `< 0.1` |
| `is_near_miss` | bool | F3 是否在 `0.1-0.2` |
| `is_moderate` | bool | F3 是否在 `0.2-0.5` |
| `is_catastrophic` | bool | F3 是否 `> 0.5` 或 pre-filter 严重非法 |
| `metadata` | map | scorer 版本、阈值、时间戳等 |

### FailureLabelBatch

批量输出容器。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `labels` | list | `FailureLabel` 列表 |
| `summary` | map | 失败率、pre-filter 比例、tier 分布 |
| `config` | map | 本次标注使用的阈值与 scorer 配置 |

## Calibration Tier

Calibration Tier 决定 FSAL pair confidence。第一阶段只允许消费已提供的校准或适配器结果，不主动运行 DFT/MLIP/API。

| Tier | 来源 | 默认置信权重 | 说明 |
| --- | --- | --- | --- |
| 1 | `dft_provided` | 1.0 | DFT 结果已由用户或离线数据提供 |
| 2 | `multi_adapter_agreement` | 0.8 | 三个或更多稳定性适配器一致，默认 `std < 0.05 eV/atom` |
| 3 | `single_adapter` | 0.5 | 单个/少量适配器结果，或 `std < 0.15 eV/atom` |
| 4 | `rules_only` / `disagreement` | 0.2 | 仅规则、F3 缺失、或适配器明显分歧 |

Tier 不能伪造来源：没有 DFT 结果时不得标为 Tier 1；没有外部稳定性结果时 F3 应为 `null` 或来自 mock/test adapter，并明确 `tier_source`。

## 接口契约

| 接口 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `PreFilter.check` | `CandidateRecord` | `PreFilterResult` | 判断明显非法结构 |
| `GeometryScorer.score` | `CandidateRecord` | `FailureScore` | 输出 F1 |
| `ChemistryScorer.score` | `CandidateRecord` | `FailureScore` | 输出 F2 |
| `StabilityScorer.score` | `CandidateRecord` + 已提供的稳定性结果 | `FailureScore` | 输出 F3；不得自行调用外部计算 |
| `FailureLabeler.label` | `CandidateRecord` | `FailureLabel` | 单结构完整标注 |
| `FailureLabeler.label_many` | `list[CandidateRecord]` | `FailureLabelBatch` | 批量标注和摘要 |
| `FailurePredictor.predict` | `CandidateRecord` | `FailureLabel` 或三轴预测 | 仅定义推理接口；第一阶段可用 mock |

接口必须可替换：真实 scorer、mock scorer、离线结果 reader 应能共享同一输出结构。

## 输入与输出格式

推荐输出为 JSONL 或 Parquet。每行对应一个 `FailureLabel`，必须包含 `sample_id`、F1/F2/F3、`calibration_tier`、`pre_filtered` 和 `metadata`。

批量标注时必须保留以下统计：

- 总样本数。
- pre-filter 移除数和原因分布。
- F1/F2 failure rate。
- F3 stable / near-miss / moderate / catastrophic / unknown 比例。
- Calibration Tier 分布。
- 结构来源模型分布。

## FIIR 最小闭环中的位置

Failure Taxonomy 提供闭环的第 2 步：

1. 输入候选晶体结构。
2. 计算 F1/F2/F3 failure vector。
3. 将非 pre-filter 样本交给 FSAL 构造 matched axis-aligned preference pairs。
4. 将标签统计交给 evaluation metrics。
5. 将标签和预测接口交给 discovery pipeline 做 screening、ranking 和 feedback。

## 第一阶段验收标准

- 四类 pre-filter 原因可被表达和统计。
- F1/F2/F3、uncertainty、confidence、calibration tier 字段完整。
- F3 不可用时不会触发外部 API 或真实 MLIP/DFT。
- 同一 `FailureLabel` 可直接被 `fsal_algorithm.md` 的 `PreferencePair` 引用。
- 规格支持 mock/test scorer，因此不依赖大型数据集或外部服务。

## 当前 Lightweight 实现说明

当前代码已实现一个不依赖 pymatgen/ASE/MLIP/DFT 的轻量闭环：

- `StructureLike` / `CrystalRecord` 支持 `candidate_id`、composition、atom count、space group、prototype、lattice lengths、lattice angles、fractional coordinates 和 mock scores。
- `GeometryFailureLabeler` 实现 F1：最小 mock 原子距离、晶格长度、晶格角度、缺失坐标/晶格和空结构 hard constraints。
- `ChemistryFailureLabeler` 实现 F2：空 composition、composition 字符串解析、metadata/mock chemistry score，并预留 chemistry rule protocol。
- `StabilityFailureLabeler` 实现 F3：从 metadata/mock stability score 读取占位稳定性分数，并预留 future stability adapter。
- `FailureOracle` 组合 F1/F2/F3，输出 `FailureVector`，包含 confidence、calibration tier、`is_valid`、`hard_failures` 和 metadata。
- 当前实际 tier 逻辑为：tier 0 invalid/hard failure，tier 1 mock-only，tier 2 rule-based。tier 3 ensemble/calibrated 和 tier 4 DFT-calibrated 仅保留为未来占位。
