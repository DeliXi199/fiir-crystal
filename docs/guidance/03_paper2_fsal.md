## GitHub/Codex 导出信息

- Repository name: `fiir-crystal`
- Repository role: Paper 2 指导文档
- Export path: `docs/guidance/03_paper2_fsal.md`
- Document type: implementation guidance
- Main code module: `fiir_crystal.fsal`
- Related modules:
  - `fiir_crystal.failure`
  - `fiir_crystal.generation`
  - `fiir_crystal.evaluation`
- Main spec file to generate:
  - `docs/specs/fsal_algorithm.md`

---

## 工程实现边界

本页面用于指导 FSAL 模块实现。代码实现应围绕以下组件展开：

1. `fiir_crystal.fsal.preference_data`
   - 定义 preference pair 数据结构。
   - 支持 winner、loser、axis、margin、confidence、metadata。
2. `fiir_crystal.fsal.pair_mining`
   - 实现 matched axis-aligned pair mining。
   - 不只比较 F1/F2/F3 分数，还要支持 composition、atom count、space group、prototype 等匹配条件。
3. `fiir_crystal.fsal.dpo`
   - 实现 DPO trainer 接口。
   - 第一阶段只实现 trainer skeleton，不实现完整深度学习训练。
4. `fiir_crystal.fsal.losses`
   - 预留 standard DPO、confidence-weighted DPO、margin DPO 等损失接口。
5. `fiir_crystal.fsal.adapters`
   - 预留 per-axis LoRA / adapter bank 接口。
   - F1/F2/F3 可分别对应不同 adapter。
6. `fiir_crystal.generation`
   - 定义生成模型 wrapper。
   - 支持 CrystalFormer 或其他模型接入，但第一阶段只做抽象接口。

---

## 实施目标

<aside>
🎯

实现 **FSAL-v2（Failure-Structured Alignment Learning）**——通过 **Matched Axis-Aligned Pairing + Confidence-Weighted Margin DPO + On-Policy Refresh**，显著优于 binary/energy-only/weighted-sum feedback 来对齐晶体生成模型。FIIR-v2 核心升级：pair 构造从纯 score-aligned 升级为化学/结构匹配后的因果配对；DPO 从 uniform-weight 升级为 CW-Margin；每轮迭代 on-policy 刷新。

</aside>

**目标 Venue**：NeurIPS / ICML 主会

**预估工期**：3–5 个月

**前置依赖**：Paper 1 的 failure taxonomy 和标注数据

---

## Step 1：准备基座模型

### 1.1 主实验：CrystalFormer

```bash
# 克隆并安装 CrystalFormer (Cao & Wang, 2025) [1]
git clone https://github.com/deepmodeling/CrystalFormer.git
cd CrystalFormer
pip install -e .

# 下载预训练权重（Alex-20 训练集）
# 参考仓库 README 中的 model checkpoint 链接
wget <checkpoint_url> -O checkpoints/crystalformer_alex20.pt
```

**为什么选 CrystalFormer**：

- 开源，有 RL 版本可直接 head-to-head 对比 [1]
- 自回归结构天然支持 DPO 训练（序列级别的偏好学习）
- 与我们的训练数据集（Alex-20）一致

### 1.2 第二基座（FIIR-v2 必做：验证 base-model agnostic）

<aside>
🔴

**FIIR-v2 核心升级**：多基座验证从"可选"升级为"必做"（实验 #17）。选择一个扩散/flow 基座，证明 FSAL 不是只在自回归模型上有效。

</aside>

- **首选 DiffCSP++** (Jiao et al., ICLR 2024) [20]：扩散模型代表，开源成熟
- **备选 OMatG** (Höllmer et al., ICML 2025) [4]：当前 LeMat-GenBench [18] SOTA，flow-based

**扩散/flow 模型的 DPO 适配要点**：

- 扩散模型没有显式 token-level log probability → 使用 DDPM-style ELBO 作为序列级 log likelihood 的代理
- 或采用 DiffDPO 策略：在去噪轨迹上定义偏好，比较 winner/loser 的去噪轨迹 likelihood
- 关键：保持与 CrystalFormer 实验的控制变量（同数据、同 failure labels、同 pair 构造）

<aside>
⚠️

**不用 MatterGen (Zeni et al., _Nature_ 2025) [2]** 的原因：Materials Horizons 2026 已确认其训练集泄漏问题 (_Materials Horizons_ 2026) [3]——声称的"新颖"结构实为训练集已知化合物。且 adapter 机制与 preference learning 难以公平对比。

</aside>

---

## Step 2：构造 Near-miss 偏好数据

### 2.1 生成候选 + 失败标注

```python
def generate_and_label(model, num_samples=10000):
    """使用基座模型生成候选并进行失败标注"""
    candidates = model.generate(num_samples)

    success_pool = []  # E_hull < 0.1 eV/atom
    failure_pool = []  # E_hull >= 0.1 eV/atom

    for struct in candidates:
        fv = generate_failure_vector(struct)  # Paper 1 的标注函数
        if fv["f3_stability"] < 0.1:
            success_pool.append((struct, fv))
        else:
            failure_pool.append((struct, fv))

    return success_pool, failure_pool
```

### 2.2 Pre-filtering + 按 $E_{\text{hull}}$ 分三档

```python
def generate_and_label_v2(model, num_samples=10000, mlip_calculators=None):
    """
    FIIR-v2 升级版：增加 pre-filtering + calibration tier。
    """
    candidates = model.generate(num_samples)

    success_pool = []
    failure_pool = []
    pre_filtered = []  # 被 pre-filter 移除的明显非法结构

    for struct in candidates:
        fv = generate_failure_vector(struct, mlip_calculators)

        if fv.get("pre_filtered", False):
            pre_filtered.append((struct, fv))
            continue  # 不参与 DPO 训练

        if fv["f3_stability"] < 0.1:
            success_pool.append((struct, fv))
        else:
            failure_pool.append((struct, fv))

    print(f"Pre-filtered: {len(pre_filtered)}, "
          f"Success: {len(success_pool)}, Failure: {len(failure_pool)}")
    return success_pool, failure_pool, pre_filtered

def categorize_failures(failure_pool):
    """将失败样本分为 near-miss / moderate / catastrophic"""
    near_miss = []    # 0.1-0.2 eV/atom → ~60% 配额
    moderate = []     # 0.2-0.5 eV/atom → ~30% 配额
    catastrophic = [] # >0.5 eV/atom   → ~10% 配额

    for struct, fv in failure_pool:
        e_hull = fv["f3_stability"]
        if 0.1 <= e_hull <= 0.2:
            near_miss.append((struct, fv))
        elif 0.2 < e_hull <= 0.5:
            moderate.append((struct, fv))
        else:
            catastrophic.append((struct, fv))

    print(f"Near-miss: {len(near_miss)}, "
          f"Moderate: {len(moderate)}, "
          f"Catastrophic: {len(catastrophic)}")
    return near_miss, moderate, catastrophic
```

---

## Step 3：Matched Axis-Aligned Preference Construction（FIIR-v2 核心升级）

<aside>
🔑

**FIIR-v2 三重升级**：① 从纯 score-aligned 升级为 **Matched Pairing**（化学/结构匹配后的因果配对）；② 引入 `pair_quality` 综合评分过滤低质量 pair；③ 融入 **calibration tier** 作为 label confidence。不将多维失败压成加权标量——我们构造**单维度主导、混杂变量受控**的偏好对。

</aside>

### 3.1 Matched Axis-Aligned Pair 构造（FIIR-v2）

```python
import numpy as np
from typing import List, Tuple, Dict

def compute_structure_match_score(struct_a, struct_b) -> float:
    """
    计算两个结构的匹配度（软加权部分）。
    综合考虑晶系相似度 + prototype 相似度。
    返回 0-1，越高越匹配。
    """
    score = 0.0

    # (a) 化学体系匹配（硬匹配已在外层处理）
    # (b) 晶系相似度
    sg_a = struct_a.get_space_group_info()[1]
    sg_b = struct_b.get_space_group_info()[1]
    crystal_sys_a = get_crystal_system(sg_a)  # cubic/hexagonal/...
    crystal_sys_b = get_crystal_system(sg_b)
    if crystal_sys_a == crystal_sys_b:
        score += 0.5
    elif are_related_systems(crystal_sys_a, crystal_sys_b):
        score += 0.25

    # (c) 原子数相似度
    n_a, n_b = len(struct_a), len(struct_b)
    atom_ratio = min(n_a, n_b) / max(n_a, n_b)
    score += 0.3 * atom_ratio

    # (d) 组成相似度（元素重叠）
    els_a = set(str(e) for e in struct_a.composition.elements)
    els_b = set(str(e) for e in struct_b.composition.elements)
    jaccard = len(els_a & els_b) / len(els_a | els_b)
    score += 0.2 * jaccard

    return min(score, 1.0)

def construct_matched_axis_aligned_pairs(
    success_pool: list,
    failure_pool: list,
    dim: int,  # 0=F1, 1=F2, 2=F3
    threshold_main: float = 0.3,
    threshold_other: float = 0.15,
    min_pair_quality: float = 0.3,
    max_pairs: int = 5000
) -> List[Dict]:
    """
    FIIR-v2 Matched Axis-Aligned Pair 构造。
    两层匹配：硬匹配（同化学体系+原子数±20%）+ 软加权（结构匹配度）。
    返回带 pair_quality 的偏好对列表。
    """
    pairs = []
    dims = ["f1_geometry", "f2_chemistry", "f3_stability"]
    main_dim = dims[dim]
    other_dims = [d for i, d in enumerate(dims) if i != dim]

    all_samples = [(s, fv) for s, fv in success_pool + failure_pool
                   if not fv.get("pre_filtered", False)]

    # 按化学体系分桶（硬匹配第一层）
    buckets = {}  # chemsys_type -> list of (struct, fv)
    for struct, fv in all_samples:
        chemsys = get_chemsys_type(struct)  # e.g., "ABO3", "binary_oxide"
        buckets.setdefault(chemsys, []).append((struct, fv))

    for chemsys, bucket in buckets.items():
        # 桶内按主维度排序
        bucket.sort(key=lambda x: x[1][main_dim])

        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                si, fvi = bucket[i]
                sj, fvj = bucket[j]

                # 硬匹配：原子数差 ≤20%
                n_i, n_j = len(si), len(sj)
                if abs(n_i - n_j) / max(n_i, n_j) > 0.2:
                    continue

                # 主维度差异要足够大
                main_diff = abs(fvi[main_dim] - fvj[main_dim])
                if main_diff < threshold_main:
                    continue

                # 其他维度差异要足够小
                other_similarity = 1.0 - np.mean([
                    abs(fvi[d] - fvj[d]) for d in other_dims
                ])
                if any(abs(fvi[d] - fvj[d]) > threshold_other
                       for d in other_dims):
                    continue

                # 结构匹配度
                struct_match = compute_structure_match_score(si, sj)

                # Label confidence（取两者 calibration tier 中较低的）
                tier_i = fvi.get("calibration_tier", 4)
                tier_j = fvj.get("calibration_tier", 4)
                tier_weight = {1: 1.0, 2: 0.8, 3: 0.5, 4: 0.2}
                label_conf = min(tier_weight[tier_i], tier_weight[tier_j])

                # pair_quality 综合评分
                pair_quality = (
                    main_diff * other_similarity *
                    struct_match * label_conf
                )

                if pair_quality < min_pair_quality:
                    continue

                # Winner = 主维度分数更低的那个
                if fvi[main_dim] < fvj[main_dim]:
                    winner, loser = si, sj
                    w_fv, l_fv = fvi, fvj
                else:
                    winner, loser = sj, si
                    w_fv, l_fv = fvj, fvi

                pairs.append({
                    "winner": winner, "loser": loser,
                    "w_fv": w_fv, "l_fv": l_fv,
                    "pair_quality": pair_quality,
                    "label_confidence": label_conf,
                    "main_axis_gap": main_diff,
                    "axis": dim
                })

                if len(pairs) >= max_pairs:
                    return pairs

    return pairs
```

<aside>
⚡

**配对效率优化**：按化学体系分桶后桶内搜索，复杂度从 $O(n^2)$ 降至 $O(\sum_k n_k^2)$，其中 $n_k$ 为各桶大小。进一步优化：桶内按主维度排序后做双指针扫描。

</aside>

### 3.2 为什么比 weighted-sum / 纯 score-aligned 更好

1. **因果推断视角**：matched pairing 控制混杂变量（化学体系、原子数），使 main axis gap 成为近似的"处理效应"
2. **可独立消融**：删除 F1-aligned pairs → 观察 F1 指标下降（实验 #8 核心消融）
3. **避免超参**：不需要调 $\alpha_1, \alpha_2, \alpha_3$ 权重
4. **pair_quality 过滤**：低质量 pair 自动被排除，提高训练信号纯度
5. **label_confidence 传递**：calibration tier 信息从 Paper 1 流入 Paper 2，实现端到端的不确定性感知
6. **审稿人友好**：每个维度的贡献可单独可视化

---

## Step 4：Confidence-Weighted Margin DPO 训练（FIIR-v2 核心升级）

### 4.1 CW-Margin DPO 损失函数（替代标准 DPO）

<aside>
🔴

**FIIR-v2 核心升级**：从标准 DPO 升级为 **Confidence-Weighted Margin DPO**。两个关键改进：① pair confidence $w_{ij}$ 由 calibration tier 决定（可靠的 pair 权重更高）；② adaptive margin $m_{ij}$ 由 failure gap 决定（near-miss 用小 margin，catastrophic 用大 margin）。借鉴 MADPO [35]、γ-PO [36]、CW-PO [37]。

</aside>

$$
\mathcal{L} = -\sum_i w_{ij} \log \sigma\left(\beta \left[\log \frac{\pi_\theta(x_w^i)}{\pi_{\text{ref}}(x_w^i)} - \log \frac{\pi_\theta(x_l^i)}{\pi_{\text{ref}}(x_l^i)}\right] - m_{ij}\right)
$$

```python
import torch
import torch.nn.functional as F

def cw_margin_dpo_loss(
    policy_chosen_logps: torch.Tensor,
    policy_rejected_logps: torch.Tensor,
    reference_chosen_logps: torch.Tensor,
    reference_rejected_logps: torch.Tensor,
    pair_weights: torch.Tensor,   # w_ij: pair confidence
    margins: torch.Tensor,         # m_ij: adaptive margin
    beta: float = 0.1
) -> torch.Tensor:
    """
    Confidence-Weighted Margin DPO (FIIR-v2)。
    借鉴 MADPO [35], γ-PO [36], CW-PO [37]。

    参数：
        pair_weights: 由 calibration tier 决定的 pair confidence
                      Tier1→1.0, Tier2→0.8, Tier3→0.5, Tier4→0.2
        margins:      由 failure gap 决定的 adaptive margin
                      near-miss→0.1, moderate→0.3, catastrophic→0.5
    """
    chosen_rewards = beta * (
        policy_chosen_logps - reference_chosen_logps
    )
    rejected_rewards = beta * (
        policy_rejected_logps - reference_rejected_logps
    )

    # CW-Margin DPO: weighted loss with adaptive margin
    logits = chosen_rewards - rejected_rewards - margins
    loss = -(pair_weights * F.logsigmoid(logits)).mean()
    return loss

def compute_pair_weight_and_margin(pair_info: dict) -> tuple:
    """
    从 pair 信息中计算 weight 和 margin。
    """
    # Weight: 由 label_confidence（calibration tier）决定
    w = pair_info["label_confidence"]  # 已在 pair 构造时计算

    # Margin: 由 main_axis_gap 决定
    gap = pair_info["main_axis_gap"]
    if gap < 0.15:       # near-miss pair
        m = 0.1
    elif gap < 0.4:      # moderate pair
        m = 0.3
    else:                # catastrophic pair
        m = 0.5

    return w, m
```

**对比标准 DPO（实验 #15 消融用）**：

```python
def standard_dpo_loss(
    policy_chosen_logps, policy_rejected_logps,
    reference_chosen_logps, reference_rejected_logps,
    beta: float = 0.1
) -> torch.Tensor:
    """标准 DPO (Rafailov et al., NeurIPS 2023) [14]，用于消融对比"""
    chosen_rewards = beta * (policy_chosen_logps - reference_chosen_logps)
    rejected_rewards = beta * (policy_rejected_logps - reference_rejected_logps)
    return -F.logsigmoid(chosen_rewards - rejected_rewards).mean()
```

### 4.2 训练循环（CW-Margin DPO + axis-aligned batch 采样）

```python
def train_structured_dpo_v2(
    model, ref_model, preference_data,
    epochs=3, batch_size=32, lr=1e-5, beta=0.1
):
    """FSAL-v2 结构化 CW-Margin DPO 训练"""
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)

    for epoch in range(epochs):
        batch = sample_balanced_batch(
            preference_data,
            batch_size=batch_size,
            ratios={"f1": 0.3, "f2": 0.3, "f3": 0.3, "mixed": 0.1}
        )

        for pair_batch in batch:
            winners = [p["winner"] for p in pair_batch]
            losers = [p["loser"] for p in pair_batch]

            # 计算 pair weights 和 margins
            weights, margins = [], []
            for p in pair_batch:
                w, m = compute_pair_weight_and_margin(p)
                weights.append(w)
                margins.append(m)
            pair_weights = torch.tensor(weights, device="cuda")
            pair_margins = torch.tensor(margins, device="cuda")

            with torch.no_grad():
                ref_w_logps = ref_model.log_prob(winners)
                ref_l_logps = ref_model.log_prob(losers)

            policy_w_logps = model.log_prob(winners)
            policy_l_logps = model.log_prob(losers)

            loss = cw_margin_dpo_loss(
                policy_w_logps, policy_l_logps,
                ref_w_logps, ref_l_logps,
                pair_weights=pair_weights,
                margins=pair_margins,
                beta=beta
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # === 模式坍缩监控 ===
        entropy = compute_composition_entropy(model, n_samples=1000)
        print(f"Epoch {epoch}: loss={loss:.4f}, entropy={entropy:.4f}")
        # 连续两轮熵下降 >10% 则降低学习率
```

### 4.3 CrystalFormer 序列级 DPO 适配（关键实现细节）

<aside>
🔑

CrystalFormer 的输出是自回归序列 $(G, \mathbf{L}, W_1, W_2, \ldots, W_n)$，其中 $G$ 为空间群 token、$\mathbf{L}$ 为晶格参数、$W_i$ 为 Wyckoff 位点。DPO 需要序列级 log probability，以下是具体适配方案。

</aside>

```python
def compute_crystal_log_prob(model, crystal_tokens, length_normalize=True):
    """
    计算 CrystalFormer 对一个晶体序列的 log probability。

    Args:
        model: CrystalFormer 模型
        crystal_tokens: tokenize 后的晶体序列
        length_normalize: 是否做长度归一化（推荐开启）
    Returns:
        序列级 log probability (标量)
    """
    log_probs = []
    for t in range(1, len(crystal_tokens)):
        logits = model(crystal_tokens[:t])
        log_p = F.log_softmax(logits[-1], dim=-1)
        log_probs.append(log_p[crystal_tokens[t]])

    total_log_prob = torch.stack(log_probs).sum()

    if length_normalize:
        # 长度归一化：避免模型偏好生成短序列（少原子晶体）
        total_log_prob = total_log_prob / len(log_probs)

    return total_log_prob

def dpo_step_crystal(model, ref_model, winner_struct, loser_struct, beta=0.1):
    """单步 Crystal DPO 更新"""
    w_tokens = tokenize_crystal(winner_struct)
    l_tokens = tokenize_crystal(loser_struct)

    # 变长序列：winner 和 loser 长度可不同，分别计算
    pi_w = compute_crystal_log_prob(model, w_tokens)
    pi_l = compute_crystal_log_prob(model, l_tokens)

    with torch.no_grad():
        ref_w = compute_crystal_log_prob(ref_model, w_tokens)
        ref_l = compute_crystal_log_prob(ref_model, l_tokens)

    return dpo_loss(pi_w, pi_l, ref_w, ref_l, beta)
```

**关键注意事项**：

1. **变长序列处理**：不同晶体原子数不同，DPO 偏好对 $(x_w, x_l)$ 不要求等长——分别计算各自的 log probability 即可
2. **长度归一化必须开启**：否则模型会退化为偏好生成小原子数晶体（短序列 log prob 绝对值更小）
3. **参考模型冻结**：$\pi_{\text{ref}}$ 使用 `model.eval()` + `torch.no_grad()`，整个训练过程不更新
4. **tokenization 一致性**：须与 CrystalFormer 原始代码保持一致（空间群编号 → token，晶格参数离散化，Wyckoff 位点编码），参考 `CrystalFormer/utils/tokenizer.py`

---

### 4.4 模式坍缩缓解策略

```python
def sample_balanced_batch(preference_data, batch_size, ratios):
    """
    模式坍缩缓解：
    1. 混入 50% 原始训练数据（SFT loss）
    2. 按维度平衡采样偏好对
    3. 组成熵监控
    """
    n_f1 = int(batch_size * ratios["f1"])
    n_f2 = int(batch_size * ratios["f2"])
    n_f3 = int(batch_size * ratios["f3"])
    n_mixed = batch_size - n_f1 - n_f2 - n_f3

    batch = []
    batch += sample_from(preference_data["f1_aligned"], n_f1, "f1")
    batch += sample_from(preference_data["f2_aligned"], n_f2, "f2")
    batch += sample_from(preference_data["f3_aligned"], n_f3, "f3")
    batch += sample_from(preference_data["mixed"], n_mixed, "mixed")

    return batch

# KL 正则化
def total_loss(dpo_loss, model, ref_model, kl_weight=0.01):
    """DPO + KL 正则化"""
    kl_div = compute_kl_divergence(model, ref_model)
    return dpo_loss + kl_weight * kl_div
```

---

## Step 5：Failure Predictor Reranking（推理时通道）

```python
def failure_predictor_reranking(
    model, failure_predictor,
    n_generate=100, n_select=10
):
    """
    双通道推理：
    1. 训练时已通过 Structured DPO 改进分布
    2. 推理时用 Failure Predictor 进一步过滤
    """
    # 生成 K 个候选
    candidates = model.generate(n_generate)

    # Failure Predictor 打分（毫秒级）
    scores = []
    for struct in candidates:
        pred = failure_predictor.predict(struct)
        # 综合失败分数 = F1 + F2 + F3
        total_score = pred["f1"] + pred["f2"] + pred["f3"]
        scores.append(total_score)

    # 选取失败分数最低的 Top-N
    top_indices = np.argsort(scores)[:n_select]
    return [candidates[i] for i in top_indices]
```

---

## Step 6：On-Policy 迭代闭环（FIIR-v2 核心升级）

<aside>
🔴

**FIIR-v2 核心升级**：每轮迭代 **on-policy 刷新**——重新生成样本 + 重新构造 matched pair + 重新计算 failure vector。防止 distribution shift（off-policy 的 pair 在新策略下可能已不再有效）。实验 #15 对比 on-policy vs off-policy。

</aside>

```python
def fiir_v2_iterative_loop(
    base_model, failure_predictor, mlip_calculators,
    n_rounds=5, n_generate_per_round=10000
):
    """FIIR-v2 完整迭代训练循环（On-Policy Refresh）"""
    model = base_model
    ref_model = base_model.copy()  # 冻结参考模型

    metrics_history = []

    for round_idx in range(n_rounds):
        print(f"\n=== Round {round_idx + 1}/{n_rounds} ===")

        # 1. On-Policy 生成：用当前模型生成新候选
        success, failure, pre_filtered = generate_and_label_v2(
            model, n_generate_per_round, mlip_calculators
        )
        print(f"  Pre-filtered: {len(pre_filtered)}")

        # 2. 分类失败样本
        near_miss, moderate, catastrophic = categorize_failures(failure)

        # 3. On-Policy 重新构造 Matched Axis-Aligned Pairs
        pref_data = {
            "f1_aligned": construct_matched_axis_aligned_pairs(
                success, failure, dim=0),
            "f2_aligned": construct_matched_axis_aligned_pairs(
                success, failure, dim=1),
            "f3_aligned": construct_matched_axis_aligned_pairs(
                success, failure, dim=2),
            "mixed": construct_mixed_pairs(success, failure)
        }

        # 4. CW-Margin DPO 训练
        model = train_structured_dpo_v2(
            model, ref_model, pref_data
        )

        # 5. 可选：更新 Failure Predictor
        # failure_predictor.finetune(new_labels)

        # 6. 记录指标
        metrics = evaluate_model(model, n_samples=5000)
        metrics_history.append(metrics)
        print(f"  Stable Rate: {metrics['stable_rate']:.3f}")
        print(f"  F1 Fail Rate: {metrics['f1_fail']:.3f}")
        print(f"  F2 Fail Rate: {metrics['f2_fail']:.3f}")
        print(f"  Composition Entropy: {metrics['entropy']:.3f}")
        print(f"  Pair Quality (mean): {np.mean([p['pair_quality'] for pairs in pref_data.values() for p in pairs]):.3f}")

        # 7. Early stopping：如果连续 2 轮 stable rate 提升 < 1% 则停止
        if len(metrics_history) >= 2:
            delta = metrics['stable_rate'] - metrics_history[-2]['stable_rate']
            if delta < 0.01:
                print(f"  ⚠️ Marginal improvement ({delta:.4f}), consider stopping.")

    return model, metrics_history
```

---

## Step 7：核心消融实验

| #       | 消融                                          | 具体做法                                            | 验证假设                                           |
| ------- | --------------------------------------------- | --------------------------------------------------- | -------------------------------------------------- |
| A1      | **维度消融**                                  | 分别删除 F1/F2/F3-aligned pairs                     | 各维度偏好对的独立贡献                             |
| A2      | **负样本消融**                                | near-miss only vs catastrophic only vs random       | Near-miss 的学习价值                               |
| A3      | **DPO vs PPO**                                | 同样多维信息，对比两种学习方式                      | Preference pair 天然支持多维对比                   |
| A4      | **Multi-dim PPO vs FSAL**                     | F1+F2+F3 多维 reward 做 PPO                         | 即使给 PPO 相同多维信息，axis-aligned DPO 仍更优   |
| A5      | **Axis-aligned vs Weighted-sum**              | 同样多维，对比偏好对构造方式                        | 解耦 > 压缩                                        |
| A6      | **迭代轮数**                                  | 画收敛曲线                                          | 多轮有持续收益                                     |
| A7      | **PLaID++ Head-to-Head**                      | 复现 PLaID++ [25] weighted-sum iterative DPO        | **核心 claim**：axis-aligned > weighted-sum        |
| A8      | **MapReduce LoRA variant**                    | F1/F2/F3 各训 LoRA adapter，迭代合并 [29]           | Pareto front 推进 vs batch-level mixing            |
| A9      | **推理时 Failure Guidance**                   | 冻结基座，推理时 Failure Predictor 引导             | 训练时对齐 > 推理时引导                            |
| A10     | **Repair（路线 B）**                          | near-miss only 局部修复                             | 修复 vs 偏好学习效率对比                           |
| A11     | **Soft Preference Learning**                  | DPO 中解耦 entropy/cross-entropy [31]               | stability ↑ 且 diversity 不坍缩                    |
| **A12** | **CW-Margin DPO vs 普通 DPO（FIIR-v2 新增）** | 去掉 pair_weight 和 margin，用标准 DPO              | **CW-Margin > 标准 DPO（核心消融）**               |
| **A13** | **Matched vs 无匹配 pairing（FIIR-v2 新增）** | 去掉化学体系硬匹配 + 结构软加权，仅用 score-aligned | **Matched pairing > 纯 score-aligned（核心消融）** |
| **A14** | **多基座验证（FIIR-v2 新增）**                | FSAL-v2 on DiffCSP++ 或 OMatG                       | **Base-model agnostic（vs PLaID++ 差异化）**       |
| **A15** | **On-Policy vs Off-Policy（FIIR-v2 新增）**   | 固定第 1 轮 pair 不刷新 vs 每轮 on-policy 刷新      | **On-policy refresh 防止 distribution shift**      |

---

## Step 8：必须正面回答的审稿问题

<aside>
⚠️

**Q1: 为什么 axis-aligned 比 weighted scalar 更好？**
→ 消融实验 #4 + 各维度独立改善可视化图

**Q2: 为什么 near-miss 比 catastrophic 更有学习价值？**
→ 消融实验 #2 + 梯度 norm 分析（near-miss 的梯度更大且方向更稳定）

**Q3: 为什么 DPO 比 PPO 更适合多维信号？**
→ 消融实验 #3。关键论证：preference pair 天然支持维度解耦的对比，PPO 必须将多维压成单一 reward

</aside>

---

## 论文写作要点

### 标题

> _"FSAL: Failure-Structured Alignment Learning for Crystal Generative Models"_

### 核心卖点（严格 3 个，其他降级到附录）

1. **Failure Attribution Space**：首次将晶体生成失败从 binary/scalar 扩展为 3 维连续空间
2. **Axis-Aligned Preference Construction**：维度解耦的偏好对比加权标量更精确
3. **Near-miss Mining + Dual-Channel**：近失优先 + 训练/推理双通道

### 与 PLaID++ [25] 的差异化

> PLaID++ (Xu et al., ICML 2026) [25] 是最直接的先行工作——也对晶体 LLM 做 iterative DPO。三个核心区别：
> **(1)** PLaID++ 将 stability + novelty + space group 混为 weighted-sum 标量 reward，我们用 axis-aligned 偏好对实现维度解耦——消融实验 #5 和 #PLaID++ Head-to-Head 直接验证
> **(2)** PLaID++ 的负样本是随机不稳定结构，我们的 near-miss mining（$E_{\text{hull}}$ 0.1–0.2 eV/atom）提供更高信息密度
> **(3)** PLaID++ 用 temperature scaling 对抗 mode collapse，我们用 Soft Preference Learning [31] 从理论上解耦 entropy 与 cross-entropy，提供更精细的多样性控制
> **(4)** 我们额外提供 Failure Predictor 推理时 reranking + Failure-Conditioned Repair（路线 B）两个互补通道

### 预期成果

- Stable Rate 相比 CrystalFormer-RL [1] 和 PLaID++ [25] 提升 ≥15%（相对），**且 diversity 指标不下降**
- **预期排序**：FSAL + Soft PL > FSAL > MapReduce LoRA variant > Multi-dim PPO > Weighted-sum DPO (≈PLaID++) > 推理时 Failure Guidance > Binary DPO > Energy-only PPO
- **Pareto front 目标**：在 stability-diversity 平面上，FSAL 的 Pareto front 严格支配 PLaID++ 和 CrystalFormer-RL
- 3–5 轮迭代有持续收益
- **数据泄漏防控**：所有生成结构须通过 `StructureMatcher` 与训练集去重，确保 novelty 指标可信

---

## 参考文献（本页引用）

- [1] Cao & Wang, "CrystalFormer-RL: Reinforcement Fine-Tuning for Materials Design", arXiv:2504.02367, 2025. https://arxiv.org/abs/2504.02367
- [2] Zeni et al., "MatterGen: A generative model for inorganic materials design", _Nature_, 2025. https://www.nature.com/articles/s41586-025-08628-5
- [3] "Continued challenges in high-throughput materials predictions: MatterGen predicts compounds from the training dataset", _Materials Horizons_, 2026. https://pubs.rsc.org/en/content/articlehtml/2026/mh/d6mh00268d
- [4] Höllmer et al., "Open Materials Generation with Stochastic Interpolants", ICML 2025. https://arxiv.org/abs/2502.02582
- [14] Rafailov et al., "Direct Preference Optimization: Your Language Model is Secretly a Reward Model", NeurIPS 2023. https://arxiv.org/abs/2305.18290
- [18] Betala et al., "LeMat-GenBench: A Unified Evaluation Framework for Crystal Generative Models", AI4Mat-NeurIPS 2025 Workshop. https://arxiv.org/abs/2512.04562
- [20] Jiao et al., "Space Group Constrained Crystal Generation (DiffCSP++)", ICLR 2024. https://arxiv.org/abs/2402.03992
- [25] Xu et al., "PLaID++: A Preference Aligned Language Model for Targeted Inorganic Materials Design", ICML 2026. https://arxiv.org/abs/2509.07150
- [29] Chen et al., "MapReduce LoRA: Advancing the Pareto Front in Multi-Preference Optimization", CVPR 2026 Highlight. https://arxiv.org/abs/2511.20629
- [31] Slocum et al., "Diverse Preference Learning for Capabilities and Alignment (Soft Preference Learning)", NeurIPS 2025. https://arxiv.org/abs/2511.08594
- [35] Rho, "Margin Adaptive DPO (MADPO)", TMLR. https://arxiv.org/abs/2510.05342
- [36] Sun et al., "γ-PO: Robust Preference Optimization via Dynamic Target Margins", ACL 2025. https://aclanthology.org/2025.findings-acl.282/
- [37] Afzali et al., "CW-PO: Confidence-Weighted Preference Optimization", ICLR 2026. https://arxiv.org/abs/2603.04968
- [38] Wu et al., "AlphaDPO: Adaptive Reward Margin", ICML 2025. https://arxiv.org/abs/2410.10148

---

## 给 Codex 的实现指导

Codex 根据本页面搭建代码时，不要直接实现完整训练。先建立以下最小接口：

- `PreferencePair`
- `PreferenceDataset`
- `AxisAlignedPairMiner`
- `MatchedPairConfig`
- `DPOLoss`
- `FSALTrainer`
- `GeneratorWrapper`

FSAL 的最小闭环是：

1. 输入带有 failure vector 的候选晶体集合；
2. 构造 F1/F2/F3 axis-aligned preference pairs；
3. 生成标准 preference dataset；
4. 调用 FSAL trainer 接口；
5. 输出训练日志和评估结果占位对象。

实现时必须保留以下实验扩展点：

- binary DPO baseline；
- weighted-sum DPO baseline；
- random negative baseline；
- near-miss mining；
- confidence-weighted margin DPO；
- per-axis adapter bank。
