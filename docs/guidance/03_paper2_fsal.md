<aside>
🎯

**Paper 2 科学使命（v2.2 收敛版）**：证明结构化失败信号（F1/F2/F3 为训练主轴，而非标量奖励）可以通过 axis-aligned preference alignment 系统性地改进晶体生成模型——更可诊断、更可解释、更鲁棒。方法在自回归基座上完整验证，在扩散/flow 基座上做 pilot 验证证明可适配性。Paper 2 是 FIIR 体系的旗舰论文。

**执行原则（v2.2）**：先做最小可验证版本（Minimal Viable FSAL = pre-filtering + matched F1/F2/F3 pairs + confidence-weighted DPO + per-dimension evaluation），其他组件作为消融分层加入。

</aside>

---

## 一、核心科学主张

Paper 2 需要回答一个根本问题：**结构化失败信号如何被转化为有效的生成模型训练信号？**

核心主张（按优先级排序）：

1. **Structured > Scalar**：F1/F2/F3 结构化失败反馈优于标量奖励（PPO [1]）或加权总分偏好（PLaID++ [25]）——这是最核心的 claim
2. **Axis-aligned > Weighted-sum**：维度解耦的偏好对优于混合维度的偏好对（head-to-head PLaID++ 对比）
3. **Matched > Random**：因果控制的匹配配对优于随机负样本配对
4. **Training-time > Inference-time**：训练时对齐（FSAL）优于推理时引导（路线 C）
5. **Reward hacking is mitigable**：fixed audit + targeted audit + proxy-true divergence 可有效防止 reward hacking
6. **FSAL is architecture-adaptable**（降级 claim）：在自回归基座上完整验证；扩散/flow 基座做 pilot 验证证明方法思想可迁移，但不要求所有指标打穿

---

## 二、为什么结构化失败 > 标量奖励

### 标量奖励的三个根本问题

现有方法（CrystalFormer-RL [1] 用 MLIP energy 做 PPO，PLaID++ [25] 用 weighted-sum 做 DPO）将多维失败信息压缩为单一标量。这导致：

1. **信息损失**：不同失败原因被混合，模型无法区分"几何坏"和"化学坏"
2. **权重任意性**：$\alpha_1 F_1 + \alpha_2 F_2 + \cdots + \alpha_5 F_5$ 的权重缺乏科学依据，且最优权重可能随训练阶段变化
3. **不可解释性**：模型改进后无法归因到具体失败维度，无法诊断改善来源
4. **Reward hacking 风险**：标量 reward 更容易被模型利用——模型可能学会生成"骗过"MLIP 但物理上不合理的结构（Goodhart's Law [49]）

### FSAL 的核心立场

**多维失败信息应尽可能晚地聚合。** 在训练信号构造层面保留维度解耦信息，让模型分别学习改善各类失败，而不是学习优化一个混合分数。

---

## 三、方法论核心组件

### 3.1 Pre-filtering：移除低级错误

**原则**：明显非法结构（原子重叠、晶格角异常、密度异常等）在偏好对构造前直接过滤，不参与偏好学习。

**方法论理由**：

- 这些结构已被 F1 规则检测以高置信度标记
- 把它们放进偏好对是浪费模型容量学习低级错误
- 模型应该把学习能力集中在 near-miss 区域（"几乎成功但差一点"的结构）

### 3.2 Matched Axis-Aligned Pairing：因果控制的偏好对

这是 FSAL 与 PLaID++ [25] 的核心方法论差异。

**问题**：普通 DPO 随机配对（或仅按分数排序配对）时，一个 pair 中的 chosen 和 rejected 可能同时在多个维度上不同（不同化学体系、不同结构类型）。模型从这样的 pair 中学到的信号是模糊的。

**解决方案——Confounder-Controlled Preference Construction（v2.2 强化表述）**：

- **硬匹配**：pair 中的两个样本必须属于同一化学体系类别（如都是 ABX₃ 型钙钛矿或二元氧化物）+ 原子数接近
- **软加权**：晶系相似度、prototype 相似度纳入 pair quality 评分
- **Axis-aligned**：每个 pair 只在一个失败维度上有显著差异，其他维度保持接近
- **Pair coverage（v2.2 新增）**：pair 须覆盖主要 composition space 和 prototype space，不能集中在少数化学体系。覆盖度不足时加 coverage-aware reweighting
- **目标**：使每个 pair 近似于"只改变一个失败维度的控制实验"
- **与 MODPO/D2-DPO 的本质区别**：MODPO [32] / D2-DPO [50] 等 multi-objective DPO 仅按分数排序构造 pair，不控制混杂变量；FSAL 要求 composition/prototype 匹配后比较单一维度——本质是 **proximal causal inference**（类比 RCT vs 观察性研究）。Paper 2 必须设计直接消融：matched pairing vs unmatched per-objective DPO，量化匹配带来的增量

**Pair quality 综合评分**：

- 主维度差异（越大越好）× 其他维度相似度（越高越好）× 结构匹配度 × 标签置信度
- 低于阈值的 pair 不参与训练

**因果论证的重要性**：

- 类比 RCT（随机对照试验）：控制混杂变量后，观察到的差异才能归因于目标变量
- 参考 Causal Preference Learning [39] 和 Causal DPO [40] 的因果视角
- 这不仅是工程技巧，而是方法论层面的严谨性

### 3.3 Confidence-Weighted Margin DPO

标准 DPO [14] 对所有 pair 使用相同的 margin 和权重。FSAL 引入两个维度的信号感知：

**1. Pair Confidence** $w_{ij}$

- 由 Calibration Tier 决定：Tier 1/2 pair 权重高，Tier 3/4 pair 权重低或剔除
- **Chemistry-aware confidence discount（v2.2 新增）**：MLIP ensemble disagreement 超过阈值的化学体系，F3 的 calibration tier 自动降一级，相应 pair weight 自动降低——防止 MLIP 系统偏差向生成模型传播
- 方法论理由：不确定的标签不应与确定的标签有相同影响力

**2. Adaptive Margin** $m_{ij}$

- 由 failure gap 决定：near-miss pair（failure 差异小）用小 margin，catastrophic pair（差异大）用大 margin
- 方法论理由：near-miss 的偏好关系更微妙，需要更温和的学习信号；catastrophic 的偏好关系更明确
- 借鉴 MADPO [35]（adaptive margin）、γ-PO [36]（dynamic target）、CW-PO [37]（confidence weighting）

**核心公式形式**：

CW-Margin DPO 的损失函数在标准 DPO 基础上引入 $w_{ij}$（pair confidence）和 $m_{ij}$（adaptive margin）两个调制项，使学习信号同时感知标签可靠性和失败程度差异。

### 3.4 Reward Hacking 防护机制（新增）

**问题**：DPO 的 reward 来自 MLIP proxy（$E_{\text{hull}}$ 等），模型可能学会生成"骗过"MLIP 但物理上不合理的结构——即 reward hacking（Goodhart's Law [49]）。

**四层防护**：

1. **DFT spot-check**：每轮 on-policy refresh 随机抽 5–10% 样本做 DFT 验证，监控 MLIP proxy 与 DFT 真值的偏差趋势
2. **Conservative reward estimation**：取 MLIP ensemble 预测的下界（而非均值）作为 E_hull 估计，降低过度乐观风险
3. **Proxy-true divergence 指标**：定义 $\Delta_{\text{proxy-true}} = |E_{\text{hull}}^{\text{MLIP}} - E_{\text{hull}}^{\text{DFT}}|$ 并按轮次追踪。若该指标持续上升，触发 early stopping 或增大 DFT spot-check 比例
4. **Conformal prediction UQ**：参考 [42][44]，为 MLIP 预测提供 distribution-free 的覆盖率保证，替代 ensemble disagreement 的启发式不确定性

**方法论意义**：这是 FSAL 区别于 PLaID++ [25] 和 CrystalFormer-RL [1] 的重要防护层——它们均未显式处理 reward hacking 风险。

**v2.1 实施调整**：从"每轮随机抽 5–10%"改为更高效的分层审计策略：

- **Fixed DFT audit set**：建立固定审计结构集（~50–100 结构），每轮训练后必检 MLIP proxy 与 DFT 的偏差变化
- **Targeted audit**：主动抽查高风险样本——MLIP 预测很好 + novelty 很高 + uncertainty 很高 + 结构分布偏离训练集
- **Proxy-true divergence 作为 early stopping 和模型选择标准**，而非仅训练后补充分析
- 这比随机抽查更省计算，也更能捕捉 Goodhart / proxy hacking

### 3.5 Semi-On-Policy Pair Refresh（优化版）

**原则**：每轮迭代必须重新生成样本、重新计算 failure vector、重新构造 matched pair。

**方法论理由**：

- 模型 M_k 改进后，其失败分布会发生变化（distribution shift）
- 上一轮的 pair 不再代表当前模型的失败模式
- Off-policy pair 会导致训练信号与当前模型不匹配，降低学习效率甚至引入偏差
- 这类似于 online RL 中的 on-policy 要求

**计算成本优化**（原方案约为 PLaID++ 的 10×）：

- **Failure Predictor 快速预筛**：用 Paper 1 训练的轻量级 Failure Predictor 快速估计新生成样本的 failure vector，仅对预测 near-miss 的样本执行完整 MLIP 评估
- **Semi-on-policy 策略**：80% cached pairs（上一轮）+ 20% 新生成 pairs，逐步过渡

### 3.6 Near-miss 优先采样

**原则**：$E_{\text{hull}}$ 在 0.1–0.2 eV/atom 范围的 near-miss 样本通常比 catastrophic failure 更有训练价值。

**方法论理由**：

- Near-miss 结构"几乎成功"，模型只需小幅调整即可改善
- Catastrophic failure 信号太强，容易导致过度回避而牺牲多样性
- 类比 curriculum learning：先学简单的区分，再学困难的
- Near-miss 应在采样中占更大配额

### 3.7 Diversity Preservation

**问题**：偏好学习可能导致模式坍缩（mode collapse）——模型学会只生成少数"安全"结构。

**方法论解决**：

- **Soft Preference Learning [31]**：解耦 entropy 项和 cross-entropy 项，使模型在提升质量的同时保持分布多样性
- **组成熵监控**：持续追踪生成晶体的化学组成多样性
- **训练数据混入**：适度混入原始训练数据，防止遗忘
- **Pareto front 评估**：不只看 stability 一个指标，必须同时报告 stability-diversity Pareto front

### 3.8 Pair Yield + Coverage 保障机制（v2.2 更新）

**问题**：axis-aligned matching 的约束很严（固定其他维度、只变一个维度），实际能匹配到多少有效 pair、pair 能否覆盖足够的化学空间，均未验证。

**解决方案**：

1. **依赖 Paper 1 的 pair yield + coverage pilot study 结果**：确认各 failure axis 的 yield 和 pair 在 composition/prototype space 上的覆盖度
2. **若 yield > 10% 且 coverage 充足**：使用严格匹配
3. **若 yield < 10%**：启用 **soft matching + causal reweighting**（参考 Causal DPO [40]）：放宽匹配条件，用倾向性得分（propensity score）对混杂变量做事后校正
4. **若 coverage 不足**（v2.2 新增）：pair 集中在少数化学体系/prototype → 加 **coverage-aware reweighting**，对低覆盖区域的 pair 提高采样权重
5. **pair quality 综合评分下限**：即使启用 soft matching，pair quality 综合评分仍须高于最低阈值
6. **最终后备（Plan B）**：yield + coverage 均不足 → 转向 objective-conditioned FSAL（适用于 crystal LLM 基座）

### 3.9 MapReduce LoRA variant（实验变体）

**概念**：每个失败维度各训独立 LoRA adapter，推理时合并。

- 借鉴 MapReduce LoRA [29]（多偏好并行训练 + 合并）和 LoRI [41]（减少跨任务干扰）
- 作为消融实验对比 batch-level mixing，而非主方法

---

## 四、Base-Model Agnostic 设计

### 原则（v2.2 降级为"可适配"）

FSAL 不绑定特定生成模型架构，但 Paper 2 不以"全面 base-model agnostic"为生死线：

1. **主实验基座（完整验证）**：CrystalFormer（自回归，token-based）——所有消融实验和 head-to-head 对比在此完成
2. **Pilot 基座（概念验证）**：DiffCSP++ [20] 或 OMatG [4]——较小规模实验，证明方法思想可迁移，但不要求所有指标打穿
3. **可选扩展**：WyckoffDiff [45]（Wyckoff-aware 扩散模型），若资源允许

### 适配考量

- **自回归基座**：偏好学习可直接基于 token-level log-probability，与 LLM DPO 同构
- **扩散/Flow 基座（v2.2 更新——已知风险与应对）**：CrystalFormer 有 token-level log-prob，但 OMatG/DiffCSP++ 的 log-likelihood 需 ODE 积分，成本高且不稳定。FlowDPO [46] 实为 LLM 方法，非扩散模型 DPO。**应对方案**：扩散/flow pilot 使用 **denoising score matching loss** 作为 implicit log-prob proxy（类比 DiffusionDPO, Wallace et al. 2024），或用 **reward-weighted regression** 替代严格 DPO。Pilot 定位为概念验证，不要求所有指标打穿
- 若 pilot 结果好，base-model agnostic 可升级为完整 claim；若不好，仍可作为"architecture-adaptable with promising pilot"报告

---

## 五、与 PLaID++ 的 Head-to-Head 对比

PLaID++ [25] 是最直接的竞品，也使用 iterative DPO 改进晶体生成。核心差异：

| 维度                    | PLaID++             | FSAL                                                                             |
| ----------------------- | ------------------- | -------------------------------------------------------------------------------- |
| **失败表示**            | Weighted-sum scalar | 五维 failure vector (F1–F5) + calibration tier                                   |
| **偏好对构造**          | 按总分排序配对      | Matched axis-aligned pairing（因果控制）                                         |
| **DPO 变体**            | 标准 DPO            | Confidence-Weighted Margin DPO                                                   |
| **多样性保护**          | 未明确处理          | Soft Preference Learning [31] + 组成熵监控                                       |
| **Reward hacking 防护** | 无                  | DFT spot-check + conservative reward + proxy-true divergence 监控 + conformal UQ |
| **基座覆盖**            | 仅 crystal LLM      | 自回归 + 扩散/flow 双基座（可选 WyckoffDiff [45] 第三基座）                      |

**这个 head-to-head 对比是 Paper 2 最关键的实验**——必须在相同训练集、相同基座、相同评测框架下严格对比。

---

## 六、Claim-Based 消融矩阵

| Claim                                                         | 消融对比                                                                                   | 预期结论                                                                           |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| **结构化反馈 > 二值/标量反馈**                                | FSAL vs Binary DPO / Energy-only PPO [1] / Rejection Sampling                              | FSAL 在所有维度上更优                                                              |
| **Axis-aligned > weighted-sum**                               | FSAL vs Weighted-Sum DPO / PLaID++ 复现 [25]                                               | 维度解耦显著优于混合维度                                                           |
| **Matched（confounder-controlled） > 无匹配（uncontrolled）** | Matched pairing vs unmatched per-objective DPO（MODPO/D2-DPO 风格）vs random negative      | confounder-controlled 配对显著优于 unmatched per-objective DPO，量化匹配带来的增量 |
| **CW-Margin > 标准 DPO**                                      | CW-Margin DPO vs 标准 DPO（同样的 pair）                                                   | 置信度加权 + adaptive margin 更稳健                                                |
| **Near-miss 有训练价值**                                      | Near-miss 为主 vs catastrophic 为主 vs 混合                                                | Near-miss 优先采样效率最高                                                         |
| **训练时对齐 > 推理时引导**                                   | FSAL vs 推理时 Failure-Guided Sampling（路线 C）                                           | 训练时对齐的增量价值显著                                                           |
| **On-policy > off-policy**                                    | Semi-on-policy refresh vs 固定 pair 不刷新 vs 全量 on-policy                               | Semi-on-policy 平衡效果与成本                                                      |
| **Reward hacking 可缓解**                                     | 有 DFT spot-check + conservative reward vs 无防护；$\Delta_{\text{proxy-true}}$ 随轮次变化 | 有防护时 proxy-true divergence 保持稳定                                            |
| **Base-model agnostic**                                       | CrystalFormer + DiffCSP++/OMatG 双基座；可选 WyckoffDiff [45] 第三基座                     | 两类（或三类）基座上均有效                                                         |
| **质量不牺牲多样性**                                          | Stability-Diversity Pareto front 分析                                                      | FSAL 推进 Pareto front 而非单点                                                    |
| **Repair 作为互补**                                           | FSAL alone vs FSAL + Repair（路线 B）                                                      | Repair 对 near-miss 有额外收益                                                     |

---

## 七、评价框架

### 必须报告的指标

- **质量**：Stable Rate / SUN Rate（↑）；各维度失败率 F1–F5（↓）
- **多样性**：Unique / Novel / 空间群覆盖 / 组成熵（→ 不坍缩）
- **标准评测**：LeMat-GenBench [18] leaderboard 上的完整报告
- **Pareto 分析**：stable rate vs novelty/diversity Pareto front
- **泄漏控制**：StructureMatcher 去重 + F4 定量泄漏评估
- **Reward hacking 监控**：$\Delta_{\text{proxy-true}}$ 随训练轮次变化曲线
- **Per-dimension 改善**：分别报告 F1–F5 的改善幅度，而非只报告总分

### 对比方法

1. **Base model**（无任何对齐）
2. **Rejection Sampling**（生成后按 $E_{\text{hull}}$ 筛选）
3. **CrystalFormer-RL [1]**（MLIP PPO）
4. **PLaID++ [25]**（weighted-sum iterative DPO）——需要在我们的基座上复现
5. **OMatG-IRL [26]**（推理时 RL）
6. **推理时 Failure Guidance**（路线 C baseline）
7. **FSAL**（我们的方法）

---

## 八、论文写作定位

### 目标 Venue

NeurIPS / ICML

### 核心卖点

1. **首个将结构化失败归因引入晶体生成对齐的方法**：不只用 scalar reward 做 DPO，而是用五维解耦的失败信号
2. **因果控制的偏好对构造**：借鉴因果推理 [39][40] 的控制变量思想，使每个 pair 信号更纯净
3. **Confidence-Weighted Margin DPO**：结合标签置信度和失败幅度的自适应偏好学习
4. **Reward Hacking 显式防护**：首个在晶体生成偏好学习中引入 proxy-true divergence 监控和 DFT spot-check 的方法
5. **Base-model agnostic**：在自回归和扩散/flow 基座上均验证（可选 WyckoffDiff 第三基座）
6. **严格 head-to-head PLaID++ 对比**：在相同条件下证明结构化失败信号的价值
7. **Chemistry-aware confidence discount**：MLIP 高偏差体系自动降低标签置信度，全链路防止系统偏差传播
8. **已知方法论风险显式建档**：五大风险（pair 泛化性、counterfactual 可行性、MODPO 边界、扩散 DPO 适配、MLIP 偏差）均有明确预案

### 关键叙事

> 现有晶体生成模型的对齐方法将多维失败信息压缩为单一标量——这就像医生只告诉病人"你不健康"而不说明是心脏问题还是肺部问题。FSAL 是第一个保留诊断信息的对齐方法：它告诉模型不仅"这个结构不好"，还告诉它"在哪个维度上不好、有多不好、这个判断有多可靠"，同时显式监控模型是否在"骗过"代理评估器。

### 论文结构建议

1. Introduction：为什么 scalar reward 不够？
2. Background：DPO + 晶体生成
3. FSAL Method（Pre-filtering → Matched Pairing → CW-Margin DPO → Reward Hacking Guard → Semi-On-Policy Refresh → Diversity Preservation）
4. Base-Model Adaptation（自回归 vs 扩散/flow vs 可选 WyckoffDiff）
5. Experiments（Head-to-head PLaID++ + 完整消融矩阵 + Reward Hacking 分析）
6. Analysis（per-dimension 改善 + Pareto front + failure pattern shift + proxy-true divergence 曲线）

### 参考文献

[1] CrystalFormer-RL, [3] MatterGen leakage, [4] OMatG, [14] DPO, [18] LeMat-GenBench, [20] DiffCSP++, [25] PLaID++, [26] OMatG-IRL, [27] DAO, [28] Self-Correcting Search, [29] MapReduce LoRA, [31] Soft Preference Learning, [32] MODPO, [35] MADPO, [36] γ-PO, [37] CW-PO, [38] AlphaDPO, [39] Causal Preference Learning, [40] Causal DPO, [41] LoRI, [42] MLIP uncertainty calibration, [44] Conformal Prediction, [45] WyckoffDiff, [46] FlowDPO, [47] PackFlow, [49] Reward Hacking Survey, [50] D2-DPO
