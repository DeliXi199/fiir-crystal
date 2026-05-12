<aside>
🎯

**Paper 1 科学使命（v2.2 收敛版）**：证明晶体生成失败可以被结构化分解为诊断上可分解的维度（diagnostically separable, not assumed causally independent），且该表示是数据驱动可验证的（以 bottom-up factor discovery + counterfactual perturbation 为主验证，PCA 为辅）、可预测的、跨模型可泛化的。Paper 1 同时承担 Paper 2 的前置可行性验证（go/no-go gates）。

</aside>

---

## 一、核心科学贡献

Paper 1 需要建立三个层次的贡献：

1. **定义层**：提出 Failure Taxonomy（F1–F5 五维失败分类）+ Multi-Fidelity Labeling + Calibration Tier 分级体系
2. **验证层**：通过多层级数据驱动方法（Top-down PCA + Bottom-up SOAP/Matminer 因子发现 + Counterfactual 扰动实验）证明该分类不是任意的先验假设，而是数据中内在存在的结构
3. **预测层**：训练 Failure Predictor 直接从晶体结构预测五维 failure vector，证明失败模式是可学习的
4. **Pair Yield 评估层**：通过 pilot study 统计各 failure axis 的 matched pair yield，为 Paper 2 的偏好对构造提供可行性保证

---

## 二、Failure Taxonomy 设计原则

### 为什么需要多维失败分类

现有工作（CrystalFormer-RL [1]、PLaID++ [25]）使用单一标量（如 $E_{\text{hull}}$）评估生成质量。这有三个根本局限：

- **归因不可能**：一个结构不好，是因为几何不合法、化学不合理、还是热力学不稳定？标量 reward 无法回答
- **改善不可追踪**：模型改进后，是哪个维度变好了？哪个维度可能变差了？
- **跨模型不可比**：不同基座模型的失败模式分布不同，标量比较没有诊断价值

### 五维分类体系

| 维度                 | 科学问题                                     | 输出           | 关键设计考量                                                                                                                                                                          | 标注工具                                                    |
| -------------------- | -------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| **F1: 几何合法性**   | 结构在物理空间中是否合理？                   | 连续 (0–1)     | 原子间距异常、晶格参数不合理、对称性畸变、密度异常等；规则检测通常高置信，但边界结构需特别处理                                                                                        | pymatgen + spglib + 自定义规则                              |
| **F2: 化学合法性**   | 组成和局域化学环境是否合理？                 | 连续 (0–1)     | 价态平衡（BVS [15]）、配位合理性（CrystalNN [16]）、元素组合约束（SMACT [12]）；对复杂多元体系置信度降低                                                                              | SMACT + BVS + CrystalNN                                     |
| **F3: 热力学稳定性** | 结构在能量景观中是否稳定？                   | 连续 (eV/atom) | $E_{\text{hull}}$ 由 **self-consistent MLIP hull** 评估：用同一 MLIP 对生成结构和 MP 参考结构统一重算，保证标注一致性（参考 LeMat-GenBench [18]）；多代理模型一致→高置信，分歧→低置信 | MACE-MP-0 / CHGNet / M3GNet ensemble + self-consistent hull |
| **F4: 新颖性与泄漏** | 生成结构是否为训练集近重复或已知结构的微扰？ | 连续 (0–1)     | 直接回应 MatterGen 泄漏批评 [3]；用 StructureMatcher 去重 + Fingerprint 距离度量；与训练集相似度高→高置信判定为泄漏                                                                   | StructureMatcher + Fingerprint 距离                         |
| **F5: 可合成性**     | 结构是否具备实验合成可达性？                 | 连续 (0–1)     | 区别于 F3 热力学稳定性：亚稳但可合成（如金刚石）vs 稳定但无法合成；CLscore 边界区域需 CSLLM 二次验证                                                                                  | CLscore（PU Learning）[43] + CSLLM [17] 二次验证            |

### 分类体系的设计约束

1. **维度必须可解释**：每个维度对应明确的物理/化学含义
2. **维度应诊断上可分解**（diagnostically separable and partially controllable）：通过数据驱动验证确认各维度在诊断和干预上有用，但不假设因果独立。验证以 bottom-up + counterfactual 为主，PCA 为辅。v2.2 新增：counterfactual 不追求完全隔离单轴，而是量化**主效应比**（τ ≥ 3）
3. **每个维度必须是连续的**：不使用二值标签，保留失败程度信息
4. **每个维度必须附带置信度估计**：边界情况需降低标签权重
5. **F4/F5 的差异化角色**：F4（泄漏）主要用于 benchmark 可信度保证和 Paper 2 中过滤训练集近重复；F5（可合成性）主要用于 Paper 3 validation ladder 中 DFT 前的一级筛选

---

## 三、Multi-Fidelity Labeling 方法论

### 核心原则

失败标签的质量决定下游一切方法的上限。标签系统必须满足：

- **多来源交叉验证**：不依赖单一工具或代理模型
- **不确定性量化**：每个标签附带置信度，来源分歧应被编码而非忽略
- **层级校准**：低成本标签由高成本标签校准，形成 calibration chain

### 标注信息源层级

| 层级              | 方法角色                                                                        | 成本 |
| ----------------- | ------------------------------------------------------------------------------- | ---- |
| **规则检测**      | 捕获明显非法结构（原子重叠、晶格异常等），用于 pre-filtering                    | 极低 |
| **单代理模型**    | 快速估计 F3（能量稳定性），但可能有系统偏差                                     | 低   |
| **MLIP Ensemble** | 多个独立代理模型（MACE [8]、CHGNet [9]、M3GNet [10]）交叉验证，分歧度即不确定性 | 中   |
| **DFT 校准集**    | 少量结构进行高保真计算，校准代理模型偏差，确定 Calibration Tier 边界            | 高   |

### Calibration Tier 分级原则

| Tier       | 来源                   | 在下游的方法角色                                |
| ---------- | ---------------------- | ----------------------------------------------- |
| **Tier 1** | DFT 校准集验证         | 最高置信度标签，作为校准基准和评测 ground truth |
| **Tier 2** | 多代理模型一致         | 高置信度标签，可用于偏好学习的高权重 pair       |
| **Tier 3** | 单代理 + 规则一致      | 中等置信度，偏好学习中适度降权                  |
| **Tier 4** | 仅规则或 oracle 分歧大 | 低置信度，偏好学习中大幅降权或剔除              |

### Chemistry-Aware Confidence Discount（v2.2 新增）

MLIP 对不同化学体系的准确度差异很大（如过渡金属氧化物、含 f 电子体系、分子晶体偏差较高）。Paper 1 需在 Calibration Tier 体系中内置自动化置信度折扣机制：

- **检测**：利用 MLIP ensemble disagreement（σ_ensemble）和已知 domain of applicability 信息，识别高偏差化学体系
- **降级**：σ_ensemble 超过阈值的结构，F3 的 calibration tier 自动降一级（如 Tier 2 → Tier 3）
- **效果**：高偏差体系的标签在下游偏好学习（Paper 2）中被降权，减少系统偏差传播
- **成本**：零额外 DFT 开销，只利用 MLIP ensemble 已有的分歧信号
- **验证**：在 DFT 校准集上验证降级后的标签准确率是否提升

---

## 四、数据驱动验证框架（增强版三层验证）

Failure taxonomy 的最关键验证：**F1–F5 不是我们强加的先验分类，而是数据中内在存在的结构。**

<aside>
⚠️

**PCA 循环论证风险**：F1/F2/F3 分别由不同物理方法计算（规则检测 vs SMACT/BVS vs MLIP），PCA 显示多个主成分可能仅反映计算方法差异而非物理独立性。**必须**用以下三层验证排除此风险。

</aside>

### 第一层（主验证）：Bottom-up Descriptor 因子发现

1. **从原子级描述符出发**：使用 SOAP / Matminer / graph descriptors 等原子级特征（**不使用 F1–F5 标签**）
2. **独立因子分析**：在描述符空间上做因子分析，看能否自发涌现与 F1–F5 对应的潜在维度
3. **交叉比对**：若 bottom-up 因子与 F1–F5 高度对齐（如几何因子对应 F1、化学因子对应 F2），则说明维度反映数据内在结构而非先验偏见
4. **方法论意义**：这排除了"PCA 只反映计算方法差异"的循环论证风险

### 第二层（主验证）：Counterfactual 扰动实验

**关键立场（v2.2）**：不追求完全隔离单轴（物理耦合是真实的），而是量化**主效应比** ≡ ΔF_target / max(ΔF_other)，验证修复操作的主效应集中在目标维度。

**三种具体操作**：

1. **几何 counterfactual（targeting F1）**：对 F1 失败结构，做 constrained MLIP relaxation（仅弛豫原子位置，固定晶格参数 + 化学组成）。预期：ΔF1 ≫ ΔF2 ≈ 0，ΔF3 变化是次要效应
2. **化学 counterfactual（targeting F2）**：对 F2 失败结构，做 isovalent substitution（同 prototype 不同组成，SMACT 确保价态合理）。预期：ΔF2 ≫ ΔF1 ≈ 0，ΔF3 随组成变化
3. **稳定性 counterfactual（targeting F3）**：对 F1/F2 合格但 F3 失败的结构，做 full MLIP relaxation（弛豫位置 + 晶格）。预期：ΔF3 ≫ ΔF1 ≈ ΔF2 ≈ 0

**验证标准**：主效应比 > τ（建议 τ ≥ 3），在各化学体系和 prototype 上统计该比值的分布；若分布集中在 τ 以上，则支持该轴的部分可控性

### 第三层（辅助）：Top-down PCA/Factor Analysis

1. **收集大量失败样本**：从多个生成模型生成候选，计算每个样本的 F1–F5
2. **PCA / Factor Analysis**：对 failure vector 矩阵做降维分析，作为辅助探索
3. **PCA 局限性警告**：若输入本身就是 5 维 failure vector，前 5 主成分天然解释全部方差——因此 PCA 不能作为维度可分解性的主要证据，仅用于探索性分析和可视化

### 辅助验证

1. **跨模型稳定性**：分别对每个生成模型的失败样本做因子分析，验证因子结构的一致性
2. **相关性分析**：检验 F1–F5 之间的相关系数。注意：我们不要求弱相关（物理耦合是真实的），而是验证各维度在诊断和干预上提供增量信息

### Cross-Model Failure Profiling

这是 Paper 1 的独特贡献之一：

- 对同一化学体系，不同生成模型产生不同的失败模式分布
- 用 failure vector 空间中的分布聚类（如 HDBSCAN + UMAP 可视化）揭示模型特异性失败模式
- 这为 "为什么不同模型需要不同的改善策略" 提供了实证基础
- F4（泄漏）维度在此尤为重要：可定量比较不同模型的泄漏程度，直接回应 MatterGen 批评 [3]

### Pair Yield Pilot Study（新增）

Paper 1 需要为 Paper 2 提供配对可行性保证：

1. **统计各 failure axis 的 matched pair yield**：在严格匹配条件下（同化学体系类别 + 原子数接近），每个 failure axis（仅 F1/F2/F3）能产出多少有效 pair
2. **报告 yield 分布**：不同化学体系、不同结构复杂度下的 yield 差异
3. **报告 pair coverage（v2.2 新增）**：pair 是否覆盖主要 composition space 和 prototype space，不能集中在少数化学体系。coverage 不足时需加 coverage-aware reweighting
4. **验证 soft matching 补救效果**：若严格匹配 yield < 10%，测试放宽匹配条件 + causal reweighting [40] 后的 pair 数量和质量
5. **Pair quality 形式化**：将 pair construction 定义为 weighted bipartite matching 问题，pair quality score = 主维度差异 × 其他维度相似度 × composition/prototype 相似度 × label confidence × F4 合格性
6. **方法论意义**：这是 FSAL（Paper 2）可行性的前置验证，也是 go/no-go gate 的关键输入

---

## 八、Go/No-Go Gates（v2.1 新增）

Paper 1 的结果决定 Paper 2 的执行策略。以下是明确的决策门：

| Gate 条件                                           | 通过 → 执行                                                                 | 未通过 → 调整                                                                                                                  |
| --------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **主要 axis pair yield > 10% + pair coverage 充足** | 使用 strict axis-aligned DPO（pair 须覆盖主要 composition/prototype space） | 转向 soft matching + causal reweighting（Plan A）+ coverage-aware reweighting；若仍不足转 objective-conditioned FSAL（Plan B） |
| **Failure Predictor F3 ranking 泛化良好**           | 用于 on-policy refresh 预筛                                                 | 不用于预筛，改用完整 MLIP 评估（计算成本更高但更可靠）                                                                         |
| **F4/F5 标签噪声可控**                              | F4 用于 pair 过滤，F5 用于 Paper 3 筛选                                     | F4/F5 仅作为评估指标，不参与任何训练/过滤流程                                                                                  |
| **MLIP 与 DFT 偏差稳定**                            | 正常执行 FSAL                                                               | Paper 2 必须优先实施 reward hacking guard（fixed audit + targeted audit），而非追求更高 stable rate                            |
| **Multi-fidelity 标签优于单一 MLIP**                | 使用完整 calibration tier 体系                                              | 简化为 MLIP ensemble only，移除低层级标签                                                                                      |

---

## 五、Failure Predictor 的科学角色

### 为什么需要 Failure Predictor

Multi-Fidelity Oracle（规则检测 + MLIP ensemble + DFT）虽然准确，但计算成本高。Failure Predictor 的角色：

1. **加速标注**：从晶体结构直接预测 failure vector，避免每次都调用 MLIP ensemble 弛豫
2. **跨模型泛化**：一个在多模型失败样本上训练的 Predictor 应能泛化到新的生成模型
3. **服务下游**：在 Paper 3 中作为 acquisition function 的核心组件

### Predictor 的方法定位

- **输入**：晶体结构（原子坐标 + 晶格 + 元素）
- **输出**：预测的 failure vector (f1, f2, f3, f4, f5, uncertainty)
- **架构原则**：使用等变图神经网络（如 SchNet/PaiNN [21] 架构族），利用晶体的周期性和对称性；F4/F5 可使用辅助头（auxiliary head）避免主任务干扰
- **训练数据**：Multi-Fidelity Oracle 标注的大量失败样本（跨多个生成模型）

### 必须验证的性质

1. **预测精度**：在 held-out 失败样本上的 MAE / Ranking accuracy（F1–F5 各维度分别报告）
2. **跨模型泛化**：在模型 A 的失败样本上训练，在模型 B 的失败样本上测试
3. **推理加速比**：相对 MLIP ensemble full relaxation 的加速倍数
4. **不确定性校准**：Predictor 的不确定性估计与真实误差的校准度；可选用 conformal prediction [42][44] 提供 distribution-free 的覆盖率保证
5. **F4 泄漏检测效果**：在已知泄漏数据集（如 MatterGen 被批评的结构 [3]）上的 recall + precision
6. **F5 与 F3 的非冗余性**：验证 F5（可合成性）和 F3（热力学稳定性）在信息论意义上提供互补信号（条件互信息 > 0）

---

## 六、Claim-Based 实验设计

每个实验必须对应一个明确的科学 claim。

| Claim                           | 验证方法                                                   | 成功标准                                                                                                                |
| ------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **F1–F5 对齐数据内在结构**      | Top-down PCA + Bottom-up SOAP/Matminer 因子发现            | 前 5 主成分方差解释率 >85%，与预设维度高度对齐；bottom-up 因子与 top-down 维度一致                                      |
| **五维度诊断可分解且部分可控**  | Counterfactual 扰动实验（三种具体操作）+ 主效应比统计      | 主效应比 τ ≥ 3；各化学体系和 prototype 上分布集中在 τ 以上                                                              |
| **PCA 非循环论证**              | Bottom-up descriptor 独立因子分析（不使用 F1–F5 标签）     | 自发涌现的因子与 F1–F5 对应                                                                                             |
| **Calibration Tier 有效**       | 各 Tier 标签 vs DFT ground truth 的一致率                  | Tier 1 > Tier 2 > Tier 3 > Tier 4，单调递减                                                                             |
| **F4 泄漏检测有效**             | 在已知泄漏数据集（MatterGen 被批评的结构 [3]）上测试       | Recall > 90%，Precision > 80%                                                                                           |
| **F5 与 F3 非冗余**             | 条件互信息分析 + 案例分析（亚稳但可合成的结构）            | 条件互信息 > 0；存在大量 F3 失败但 F5 通过的结构                                                                        |
| **Pair yield + coverage 充足**  | 各 failure axis 的 matched pair yield + pair coverage 统计 | 主要 axis yield > 10%；pair 覆盖主要 composition/prototype space；soft matching + coverage-aware reweighting 可有效补救 |
| **失败模式跨模型有差异**        | 不同模型的 failure distribution 聚类分析                   | 模型特异性失败模式可被识别                                                                                              |
| **Failure Predictor 准确**      | held-out MAE + ranking accuracy（F1–F5 各维度）            | F1/F2 MAE < 0.1, F3 ranking Spearman > 0.85, F4/F5 AUC > 0.85                                                           |
| **Predictor 跨模型泛化**        | cross-model transfer test                                  | 在未见模型上性能下降 < 15%                                                                                              |
| **Predictor 加速有效**          | 推理时间 vs MLIP ensemble                                  | 加速比 >10×                                                                                                             |
| **Multi-Fidelity 优于单一来源** | 多来源标签 vs 单一 MLIP vs 仅规则                          | Multi-Fidelity 标签在 DFT 校准集上更准确                                                                                |

---

## 七、论文写作定位

### 目标 Venue

NeurIPS Datasets & Benchmarks / ICLR（取决于 Predictor 方法贡献的深度）

### 核心卖点

1. **首个系统化的晶体生成失败分析框架**：不是只报告 "stable rate"，而是诊断 "为什么不 stable"（五维诊断）
2. **三层数据驱动验证的 failure taxonomy**：Top-down PCA + Bottom-up descriptor 因子发现 + Counterfactual 扰动，排除循环论证
3. **F4 泄漏检测维度**：直接回应 MatterGen 泄漏批评 [3]，为社区提供定量泄漏评估工具
4. **跨模型 failure profiling**：首次系统比较不同生成模型的失败模式分布
5. **Failure Predictor 作为通用工具**：可被任何生成模型使用，服务整个社区
6. **Pair yield + coverage pilot study**：为偏好对齐方法提供配对可行性和分布覆盖度的首个定量评估
7. **Chemistry-aware confidence discount**：MLIP ensemble 自动降低高偏差化学体系的标签置信度，防止系统偏差传播

### 与社区的关系

- **互补 LeMat-GenBench [18]**：LeMat-GenBench 评估生成质量，我们评估失败结构——不是竞品，而是互补
- **互补 matbench-genmetrics [22]**：他们提供 success metrics，我们提供 failure diagnostics
- **服务 Paper 2/3**：failure representation 和 Predictor 是 FSAL 和 Discovery 的基础

### 论文结构建议

1. Introduction：为什么需要理解晶体生成失败（而非只计算成功率）
2. Failure Taxonomy 定义（F1–F5）+ Multi-Fidelity Labeling + Self-Consistent Hull
3. 三层数据驱动验证（PCA + Bottom-up + Counterfactual）
4. Cross-Model Failure Profiling + F4 泄漏分析
5. Pair Yield Pilot Study
6. Failure Predictor（五维预测 + 不确定性校准）
7. CrystalFail-Bench benchmark 发布

### 参考文献

[1] CrystalFormer-RL, [2] MatterGen, [3] MatterGen leakage, [4] OMatG, [8] MACE, [9] CHGNet, [10] M3GNet, [11] spglib, [12] SMACT, [15] BVS, [16] CrystalNN, [17] CSLLM, [18] LeMat-GenBench, [19] CDVAE, [20] DiffCSP++, [21] SchNet/PaiNN, [22] matbench-genmetrics, [25] PLaID++, [33] MLIP eval framework, [40] Causal DPO, [42] MLIP uncertainty calibration, [43] CLscore, [44] Conformal Prediction, [48] SyntheFormer
