## GitHub/Codex 导出信息

- Repository name: `fiir-crystal`
- Repository role: Paper 1 指导文档
- Export path: `docs/guidance/02_paper1_crystalfail_bench.md`
- Document type: implementation guidance
- Main code module: `fiir_crystal.failure`
- Related modules:
  - `fiir_crystal.predictor`
  - `fiir_crystal.evaluation`
- Main spec file to generate:
  - `docs/specs/failure_taxonomy.md`

---

## 工程实现边界

本页面用于指导 CrystalFail-Bench 和 failure labeling 模块实现。

代码实现时应拆成以下组件：

1. `fiir_crystal.failure.taxonomy`
   - 定义 F1/F2/F3 failure taxonomy。
   - 定义 failure score 的范围、含义、单位和置信度。
2. `fiir_crystal.failure.geometry`
   - 实现 F1 几何合法性检测。
   - 包括原子间距、晶格参数、角度异常、基础结构合法性检查。
3. `fiir_crystal.failure.chemistry`
   - 实现 F2 化学合法性检测。
   - 包括价态、电荷平衡、配位合理性、SMACT/BVS/CrystalNN 相关接口。
4. `fiir_crystal.failure.stability`
   - 实现 F3 热力学稳定性接口。
   - 支持 MLIP energy、`E_above_hull`、MLIP ensemble disagreement。
5. `fiir_crystal.predictor`
   - 实现 Learned Failure Predictor 的训练与推理接口。
   - 第一阶段只实现接口和数据结构，不强制实现完整 GNN 训练。
6. `fiir_crystal.evaluation`
   - 实现 failure distribution、failure profile、cross-model comparison 等评估工具。

---

## 实施目标

<aside>
🎯

构建 **CrystalFail-Bench**——第一个对晶体生成模型失败样本进行结构化、多维度、连续化归因的评测基准。同时训练 **Learned Failure Predictor** 供后续论文复用。

</aside>

**目标 Venue**：NeurIPS Datasets & Benchmarks / ICLR

**预估工期**：2–3 个月

**前置依赖**：无（本篇是整个系列的地基）

---

## Step 1：搭建失败标签生成 Pipeline

### 1.1 F1：几何合法性检测（连续 0–1）

实现以下三个子检查，加权合成 F1 分数：

```python
import numpy as np
from pymatgen.core import Structure
from pymatgen.analysis.local_env import CrystalNN
import spglib

def compute_f1_geometry(structure: Structure) -> float:
    """计算几何合法性分数 (0=完美, 1=严重违规)"""
    scores = []

    # (a) 原子间距异常检测
    min_dist = structure.distance_matrix[
        structure.distance_matrix > 0
    ].min()
    # 典型晶体最小原子间距 > 1.0 Å
    dist_score = max(0, 1.0 - min_dist / 1.0) if min_dist < 1.0 else 0.0
    scores.append(dist_score)

    # (b) 晶格参数合理性
    lattice = structure.lattice
    # 检查角度是否在合理范围 (30°–150°)
    angle_violations = sum(
        1 for a in [lattice.alpha, lattice.beta, lattice.gamma]
        if a < 30 or a > 150
    )
    scores.append(angle_violations / 3.0)

    # (c) spglib (Togo et al., 2024) 对称性偏移 [11]
    cell = (
        structure.lattice.matrix,
        structure.frac_coords,
        [s.Z for s in structure.species]
    )
    sym_data = spglib.get_symmetry_dataset(cell, symprec=0.1)
    # 如果在宽容差下无法识别对称性，说明结构严重畸变
    sym_score = 0.0 if sym_data is not None else 1.0
    scores.append(sym_score)

    return float(np.mean(scores))
```

### 1.2 F2：化学合法性检测（连续 0–1）

实现三个子检查，参考 BVS (Brown, _The Chemical Bond in Inorganic Chemistry_, 2002) [15]、CrystalNN (Pan et al., _Inorg. Chem._ 2021) [16]、SMACT (Davies et al., _JOSS_ 2019) [12]：

```python
from pymatgen.analysis.local_env import CrystalNN
from pymatgen.analysis.bond_valence import BVAnalyzer
from smact.screening import smact_filter

def compute_f2_chemistry(structure: Structure) -> float:
    """计算化学合法性分数 (0=完美, 1=严重违规)"""
    scores = []

    # (a) BVS 电荷平衡检查 [15]
    try:
        bva = BVAnalyzer()
        valences = bva.get_valences(structure)
        # GII (Global Instability Index)
        # GII < 0.1: 优秀; GII > 0.2: 可疑
        total_charge = sum(valences)
        bvs_score = min(abs(total_charge) / 2.0, 1.0)
    except Exception:
        bvs_score = 0.5  # 无法分析，给中间分
    scores.append(bvs_score)

    # (b) CrystalNN 配位数偏离检查 [16]
    try:
        nn = CrystalNN()
        coord_nums = []
        for i in range(len(structure)):
            cn = nn.get_cn(structure, i)
            coord_nums.append(cn)
        # 检查是否有异常配位数 (0 或 >12)
        abnormal = sum(1 for cn in coord_nums if cn == 0 or cn > 12)
        cn_score = abnormal / len(structure)
    except Exception:
        cn_score = 0.5
    scores.append(cn_score)

    # (c) SMACT 电荷中性检查 [12]
    composition = structure.composition
    elements = [str(el) for el in composition.elements]
    try:
        # 简化：检查是否存在至少一种电荷平衡方案
        from smact import Element as SmactElement
        smact_els = [SmactElement(e) for e in elements]
        oxidation_states = [el.oxidation_states for el in smact_els]
        # 如果能找到平衡的氧化态组合，则通过
        smact_score = 0.0  # 具体实现需遍历组合
    except Exception:
        smact_score = 0.5
    scores.append(smact_score)

    return float(np.mean(scores))
```

### 1.3 F3：热力学稳定性（连续 eV/atom）

使用三个独立 MLIP 交叉验证——MACE-MP-0 (Batatia et al., NeurIPS 2022) [8]、CHGNet (Deng et al., _Nat. Mach. Intell._ 2023) [9]、M3GNet (Chen & Ong, _Nat. Comp. Sci._ 2022) [10]：

```python
from ase import Atoms
from ase.optimize import BFGS

# === MACE-MP-0 弛豫 (Batatia et al., NeurIPS 2022) [8] ===
from mace.calculators import mace_mp
calc_mace = mace_mp(model="medium", device="cuda")

def relax_with_mace(structure: Structure, fmax=0.05, steps=200):
    """使用 MACE-MP-0 弛豫结构并返回能量"""
    from pymatgen.io.ase import AseAtomsAdaptor
    atoms = AseAtomsAdaptor.get_atoms(structure)
    atoms.calc = calc_mace
    opt = BFGS(atoms, logfile=None)
    opt.run(fmax=fmax, steps=steps)
    return atoms.get_potential_energy() / len(atoms)  # eV/atom

# === CHGNet 弛豫 (Deng et al., Nat. Mach. Intell. 2023) [9] ===
from chgnet.model import CHGNet
from chgnet.model.dynamics import CHGNetCalculator
model_chgnet = CHGNet.load()
calc_chgnet = CHGNetCalculator(model=model_chgnet)

# === M3GNet 弛豫 (Chen & Ong, Nat. Comp. Sci. 2022) [10] ===
import matgl
from matgl.ext.ase import M3GNetCalculator
pot = matgl.load_model("M3GNet-MP-2021.2.8-PES")
calc_m3gnet = M3GNetCalculator(potential=pot)

def compute_f3_stability(structure, ehull_calculator):
    """计算 E_hull (eV/atom)。需要凸包数据。"""
    energy_mace = relax_with_mace(structure)
    # 类似地对 CHGNet 和 M3GNet 弛豫
    # 三者一致判定：取中位数或要求 2/3 一致
    # E_hull < 0.1 eV/atom 视为稳定
    return energy_mace  # 简化示例
```

<aside>
⚠️

**关键**：$E_{\text{hull}}$ 的计算需要参考凸包（convex hull）数据。使用 `pymatgen.analysis.phase_diagram.PhaseDiagram` 从 Materials Project 或 Alexandria 获取参考相图。具体实现如下。

</aside>

#### E_hull 计算实现（`compute_ehull`）

```python
from pymatgen.analysis.phase_diagram import PhaseDiagram, PDEntry
from mp_api.client import MPRester

# 缓存参考相图，避免重复 API 调用
_phase_diagram_cache = {}

def compute_ehull(structure, energy_per_atom, api_key="YOUR_MP_API_KEY"):
    """
    计算结构相对于凸包的能量 E_above_hull (eV/atom)。
    E_hull < 0.1 eV/atom → 热力学稳定
    E_hull 0.1-0.2 → near-miss（Paper 2 核心训练样本）
    """
    composition = structure.composition
    chemsys = "-".join(sorted(str(el) for el in composition.elements))

    # 从缓存或 Materials Project 获取参考相图
    if chemsys not in _phase_diagram_cache:
        with MPRester(api_key) as mpr:
            entries = mpr.get_entries_in_chemsys(chemsys.split("-"))
        _phase_diagram_cache[chemsys] = entries
    else:
        entries = list(_phase_diagram_cache[chemsys])

    # 将候选结构加入相图
    candidate_entry = PDEntry(
        composition,
        energy_per_atom * composition.num_atoms
    )
    entries.append(candidate_entry)

    # 构建相图并计算 E_hull
    pd = PhaseDiagram(entries)
    return pd.get_e_above_hull(candidate_entry)  # eV/atom
```

<aside>
💡

**替代方案**：如不使用 Materials Project API，可从 Alexandria 数据集本地构建凸包——加载同化学体系的所有 DFT 条目，用 `PhaseDiagram` 本地计算，速度更快且无 API 限制。

</aside>

### 1.4 Pre-filtering：移除明显非法结构（FIIR-v2 新增）

<aside>
🔴

**FIIR-v2 新增**：在失败标注之前，先过滤掉明显非法结构——这些结构不应进入 DPO 训练（不值得让模型浪费容量学低级错误），但仍记入 benchmark 统计。

</aside>

```python
def pre_filter_trivially_invalid(structure: Structure) -> tuple:
    """
    Pre-filtering：移除明显非法结构。
    返回 (is_valid, rejection_reason)
    """
    # (a) 原子重叠检测：任意两原子间距 < 0.5 Å
    min_dist = structure.distance_matrix[
        structure.distance_matrix > 0
    ].min()
    if min_dist < 0.5:
        return False, f"atom_overlap (min_dist={min_dist:.2f}Å)"

    # (b) 晶格角异常：< 20° 或 > 160°
    lattice = structure.lattice
    for angle_name, angle_val in [
        ("alpha", lattice.alpha),
        ("beta", lattice.beta),
        ("gamma", lattice.gamma)
    ]:
        if angle_val < 20 or angle_val > 160:
            return False, f"extreme_angle ({angle_name}={angle_val:.1f}°)"

    # (c) 密度异常：< 0.5 g/cm³ 或 > 25 g/cm³
    density = structure.density
    if density < 0.5 or density > 25:
        return False, f"abnormal_density ({density:.2f} g/cm³)"

    # (d) 原子数为 0
    if len(structure) == 0:
        return False, "empty_structure"

    return True, None
```

### 1.5 整合：生成完整失败向量（FIIR-v2 升级版）

```python
def generate_failure_vector(structure: Structure,
                            mlip_calculators: dict = None) -> dict:
    """
    为单个晶体结构生成完整的 FIIR-v2 失败归因向量。
    升级：增加 uncertainty 和 calibration_tier 字段。
    """
    # Pre-filtering
    is_valid, reject_reason = pre_filter_trivially_invalid(structure)
    if not is_valid:
        return {
            "f1_geometry": 1.0, "f2_chemistry": 1.0, "f3_stability": 1.0,
            "uncertainty": 0.0,  # 确定性很高：一定是坏的
            "calibration_tier": 4,
            "pre_filtered": True,
            "reject_reason": reject_reason,
            "is_near_miss": False, "is_moderate": False, "is_catastrophic": True
        }

    f1 = compute_f1_geometry(structure)
    f2 = compute_f2_chemistry(structure)

    # F3: 多 MLIP ensemble 计算 + uncertainty
    f3_values = {}  # {mlip_name: e_hull}
    if mlip_calculators:
        for name, calc in mlip_calculators.items():
            f3_values[name] = compute_f3_with_calc(structure, calc)

    f3_median = float(np.median(list(f3_values.values()))) if f3_values else 0.0
    f3_std = float(np.std(list(f3_values.values()))) if len(f3_values) > 1 else 0.5

    # Calibration Tier 判定
    tier = assign_calibration_tier(f3_values, f3_std)

    return {
        "f1_geometry": f1,
        "f2_chemistry": f2,
        "f3_stability": f3_median,
        "f3_per_mlip": f3_values,
        "uncertainty": f3_std,
        "calibration_tier": tier,
        "pre_filtered": False,
        "is_near_miss": 0.1 <= f3_median <= 0.2,
        "is_moderate": 0.2 < f3_median <= 0.5,
        "is_catastrophic": f3_median > 0.5
    }

def assign_calibration_tier(f3_values: dict, f3_std: float) -> int:
    """
    Calibration Tier 分级（FIIR-v2 核心机制）：
    - Tier 1: DFT-validated（校准集，需后续补充）
    - Tier 2: 3 MLIP 一致（std < 0.05 eV/atom）
    - Tier 3: 单 MLIP + 规则一致（std 0.05-0.15）
    - Tier 4: 仅规则 or MLIP 分歧大（std > 0.15）
    """
    n_mlips = len(f3_values)
    if n_mlips >= 3 and f3_std < 0.05:
        return 2  # 多 MLIP 一致
    elif n_mlips >= 1 and f3_std < 0.15:
        return 3  # 单 MLIP + 规则
    else:
        return 4  # 仅规则或 MLIP 分歧大
    # Tier 1 需 DFT 校准集，在后续 Step 中补充
```

---

## Step 2：跨模型 Failure Profiling

### 2.1 选择评测模型（5 个代表性架构）

| 模型                                        | 类型                | 来源                                          | 生成量  |
| ------------------------------------------- | ------------------- | --------------------------------------------- | ------- |
| **CrystalFormer** (Cao & Wang, 2025) [1]    | 自回归 Transformer  | https://github.com/deepmodeling/CrystalFormer | 10,000+ |
| **OMatG** (Höllmer et al., ICML 2025) [4]   | Flow-based (SI)     | https://github.com/FERMat-ML/OMatG            | 10,000+ |
| **DiffCSP++** (Jiao et al., ICLR 2024) [20] | 扩散模型            | https://github.com/jiaor17/DiffCSP            | 10,000+ |
| **CDVAE** (Xie et al., ICLR 2022) [19]      | VAE + 扩散          | https://github.com/txie-93/cdvae              | 10,000+ |
| **PLaID++** (Xu et al., ICML 2026) [25]     | LLM + iterative DPO | https://arxiv.org/abs/2509.07150              | 10,000+ |
| **CrystalFormer-RL** (Cao & Wang, 2025) [1] | 自回归 + PPO RL     | https://github.com/deepmodeling/CrystalFormer | 10,000+ |

<aside>
💡

**选择理由**：6 个模型涵盖自回归、flow-based、扩散、VAE、LLM+DPO、RL 六种范式，确保 failure profile 的全面性。CrystalFormer-RL 的加入使我们可直接对比 RL 微调 vs 原始模型的失败模式变化——这是证明"失败分析可指导改进"的关键证据。

</aside>

### 2.2 批量生成与标注流程

```python
import json
from pathlib import Path

def run_failure_profiling(model_name, generated_structures):
    """对一个模型的所有生成结构进行失败标注"""
    results = []
    for i, struct in enumerate(generated_structures):
        fv = generate_failure_vector(struct)
        fv["model"] = model_name
        fv["sample_id"] = i
        results.append(fv)
        if i % 1000 == 0:
            print(f"  已标注 {i}/{len(generated_structures)}")

    # 保存结果
    out_path = Path(f"failure_labels/{model_name}.json")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    return results

# 对每个模型运行
for model_name in ["CrystalFormer", "OMatG", "DiffCSP++", "CDVAE", "LLM-based"]:
    structures = load_generated_structures(model_name)  # 自行实现
    run_failure_profiling(model_name, structures)
```

---

## Step 3：失败模式聚类与可视化

```python
import numpy as np
import hdbscan
import umap
import matplotlib.pyplot as plt

# 加载所有模型的失败向量
all_failures = []  # List[dict] with f1, f2, f3, model
X = np.array([[f["f1_geometry"], f["f2_chemistry"], f["f3_stability"]]
               for f in all_failures])

# HDBSCAN 聚类
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=50,
    min_samples=10,
    metric="euclidean"
)
labels = clusterer.fit_predict(X)

# UMAP 降维可视化
reducer = umap.UMAP(n_components=2, random_state=42)
embedding = reducer.fit_transform(X)

# 按模型着色绘图
model_names = [f["model"] for f in all_failures]
for model in set(model_names):
    mask = [m == model for m in model_names]
    plt.scatter(
        embedding[mask, 0], embedding[mask, 1],
        label=model, alpha=0.3, s=5
    )
plt.legend()
plt.title("Failure Mode Landscape (UMAP)")
plt.savefig("figures/failure_umap_by_model.pdf")
```

**预期发现**：

- **模式 A（F1 主导）**：原子重叠型——主要出现在某些扩散模型中
- **模式 B（F2 主导）**：化学不合理型——LLM-based 模型可能更多
- **模式 C（仅 F3 偏高）**：亚稳定型——**这类就是 near-miss，最有价值**

---

## Step 4：训练 Learned Failure Predictor

使用轻量 GNN（推荐 SchNet / PaiNN (Schütt et al., ICML 2021) [21]）：

```python
# 使用 SchNetPack 训练 Failure Predictor
# 输入：晶体结构（原子类型 + 坐标 + 晶格）
# 输出：3 维失败分数 (f1, f2, f3)

import schnetpack as spk
from schnetpack.data import ASEAtomsData

# 1. 准备数据集
# 将 (structure, failure_vector) 对转为 ASE Atoms 格式
atoms_list = []
property_list = []
for struct, fv in zip(structures, failure_vectors):
    from pymatgen.io.ase import AseAtomsAdaptor
    atoms = AseAtomsAdaptor.get_atoms(struct)
    atoms_list.append(atoms)
    property_list.append({
        "f1": np.array([fv["f1_geometry"]], dtype=np.float32),
        "f2": np.array([fv["f2_chemistry"]], dtype=np.float32),
        "f3": np.array([fv["f3_stability"]], dtype=np.float32),
    })

# 2. 创建 SchNetPack 数据集
dataset = ASEAtomsData.create(
    "failure_predictor_data.db",
    distance_unit="Ang",
    property_unit_dict={"f1": "1", "f2": "1", "f3": "eV/atom"}
)
dataset.add_systems(property_list, atoms_list)

# 3. 配置并训练模型
# 参见 SchNetPack 文档：https://schnetpack.readthedocs.io/
# 推荐：SchNet 或 PaiNN representation + 3-head output
```

<aside>
💡

**Failure Predictor 的核心价值**：

1. Paper 2 中用于推理时 reranking（毫秒级，替代分钟级的 MLIP 弛豫）
2. Paper 3 中用作第一层快速筛选
3. 验证跨模型泛化：用 CrystalFormer 数据训练，在 DiffCSP++ 数据上测试

</aside>

---

## Step 5：关键实验清单

- [ ] **实验 1**：各模型在 F1/F2/F3 三个维度上的失败率分布对比（核心图表）
- [ ] **实验 2**：失败模式 HDBSCAN 聚类结果 + 典型案例可视化
- [ ] **实验 3**：Near-miss vs Catastrophic 的维度分布差异
- [ ] **实验 4**：IID vs OOD 化学空间的失败率变化（少见元素组合）
- [ ] **实验 5**：不同 MLIP 的标签一致性（MACE vs CHGNet vs M3GNet）——**升级为 inter-rater reliability 分析**：报告 3 MLIP 的 Cohen's κ / Fleiss' κ + 系统偏差方向
- [ ] **实验 6**：Failure Predictor 精度（held-out 测试集）与跨模型泛化
- [ ] **实验 7**：与 LeMat-GenBench [18] 指标的互补性分析
- [ ] **实验 8**：在 LeMat-GenBench leaderboard 上提交所有 6 个模型的 failure profile
- [ ] **实验 9**：Failure Predictor 推理加速比分析（毫秒级 vs MLIP 秒级 vs DFT 小时级）
- [ ] **实验 10**：CrystalFormer vs CrystalFormer-RL failure profile 对比——RL 微调后哪些失败模式改善了、哪些恶化了
- [ ] **实验 11（FIIR-v2 新增）**：**Failure Taxonomy 数据驱动验证**——对所有模型的失败样本计算 F1/F2/F3 → PCA / factor analysis → 验证前 3 主成分是否与 geometry/chemistry/stability 高度对齐（目标：>85% 方差解释率）。若不对齐则调整维度定义。这是回应"为什么是 3 维而非 N 维"这一审稿核心质疑的关键实验
- [ ] **实验 12（FIIR-v2 新增）**：**Calibration Tier 分布统计**——报告各 Tier 占比 + DFT 校准集（~500 样本）上各 Tier 标签的准确率。Tier 1 应 >95%，Tier 2 应 >85%，Tier 3 应 >70%
- [ ] **实验 13（FIIR-v2 新增）**：**Pre-filtering 统计**——报告各模型被 pre-filter 移除的比例 + 典型被移除结构案例。预期：扩散模型被移除比例最高（原子重叠），自回归模型最低

---

## Step 6：开源产出清单

- [ ] CrystalFail-Bench 数据集（所有模型的 failure labels + calibration tier + uncertainty）
- [ ] 失败标注工具代码（含 pre-filtering 模块）
- [ ] 标准化的 failure attribution protocol（含 Calibration Tier 分级规范）
- [ ] DFT 校准集（~500 样本，用于 Tier 1 标定）
- [ ] 训练好的 Learned Failure Predictor 权重
- [ ] Failure Taxonomy 验证脚本（PCA/factor analysis）
- [ ] 可视化脚本与分析 notebook

---

## 论文写作要点

### 标题

> _"CrystalFail-Bench: A Structured Failure Attribution Benchmark for Crystal Generative Models"_

### Abstract 逻辑

1. 现有评测只关注"成功指标"（LeMat-GenBench [18]; matbench-genmetrics [22]），无人系统研究"怎么失败"——但失败样本占生成总量的 70–90%
2. 我们提出 3+1 维失败分类体系 + 连续化归因（几何/化学/稳定性 + 可合成性）
3. 对 6 个代表性模型（CrystalFormer、CrystalFormer-RL、OMatG、DiffCSP++、CDVAE、PLaID++）进行系统 failure profiling
4. **关键发现**：不同架构有系统性不同的失败模式（如扩散模型偏向几何失败，LLM 偏向化学失败），且这些 failure profiles 是 **actionable** 的——可直接指导 Paper 2 的对齐方向
5. 训练的 Failure Predictor（GNN-based）可跨模型泛化，推理速度比 MLIP 弛豫快 1000×
6. **数据驱动验证 3 维分类的合理性**：PCA/factor analysis 证明前 3 主成分与 geometry/chemistry/stability 高度对齐（>85% 方差解释率），为 Paper 2 的 axis-aligned 偏好构造提供理论基础
7. 引入 **Calibration Tier** 分级（Tier 1–4），为 Paper 2 的 Confidence-Weighted DPO 提供 pair weight
8. 与 LeMat-GenBench 互补：它们排"模型多好"→ 我们诊断"模型哪里差"→ 两者结合才能指导改进

### 与 LeMat-GenBench (Betala et al., AI4Mat-NeurIPS 2025 Workshop) [18] 的互补定位

- LeMat-GenBench 评估"模型多好"→ 我们诊断"模型哪里差"
- 它们输出排行榜 → 我们输出失败模式图谱

---

## 参考文献（本页引用）

- [1] Cao & Wang, "CrystalFormer-RL: Reinforcement Fine-Tuning for Materials Design", arXiv:2504.02367, 2025. https://arxiv.org/abs/2504.02367
- [4] Höllmer et al., "Open Materials Generation with Stochastic Interpolants", ICML 2025. https://arxiv.org/abs/2502.02582
- [8] Batatia et al., "MACE: Higher Order Equivariant Message Passing Neural Networks", NeurIPS 2022; MACE-MP-0: arXiv:2401.00096. https://github.com/ACEsuit/mace
- [9] Deng et al., "CHGNet: Pretrained universal neural network potential", _Nature Machine Intelligence_, 2023. https://doi.org/10.1038/s42256-023-00716-3
- [10] Chen & Ong, "A universal graph deep learning interatomic potential for the periodic table (M3GNet)", _Nature Computational Science_, 2022. https://doi.org/10.1038/s43588-022-00349-3
- [11] Togo et al., "Spglib: a software library for crystal symmetry search", 2024. https://spglib.readthedocs.io/
- [12] Davies et al., "SMACT: Semiconducting Materials by Analogy and Chemical Theory", _JOSS_, 2019. https://github.com/WMD-group/SMACT
- [15] Brown, "The Chemical Bond in Inorganic Chemistry: The Bond Valence Model", Oxford Univ. Press, 2002. https://www.iucr.org/resources/data/datasets/bond-valence-parameters
- [16] Pan et al., "Benchmarking Coordination Number Prediction Algorithms on DFT Structures (CrystalNN)", _Inorganic Chemistry_, 2021. https://docs.materialsproject.org/methodology/materials-methodology/related-materials
- [18] Betala et al., "LeMat-GenBench: A Unified Evaluation Framework for Crystal Generative Models", AI4Mat-NeurIPS 2025 Workshop. https://arxiv.org/abs/2512.04562
- [19] Xie et al., "Crystal Diffusion Variational Autoencoder for Periodic Material Generation (CDVAE)", ICLR 2022. https://arxiv.org/abs/2110.06197
- [20] Jiao et al., "Space Group Constrained Crystal Generation (DiffCSP++)", ICLR 2024. https://arxiv.org/abs/2402.03992
- [21] Schütt et al., "Equivariant Message Passing for the Prediction of Tensorial Properties and Molecular Spectra (PaiNN)", ICML 2021. https://github.com/atomistic-machine-learning/schnetpack
- [22] Baird et al., "matbench-genmetrics: A Python library for benchmarking crystal structure generation models", _JOSS_ 2024. https://github.com/sparks-baird/matbench-genmetrics
- [24] "Generative AI for crystal structures: a review", _npj Computational Materials_, 2025. https://www.nature.com/articles/s41524-025-01881-2
- [25] Xu et al., "PLaID++: A Preference Aligned Language Model for Targeted Inorganic Materials Design", ICML 2026. https://arxiv.org/abs/2509.07150
- [42] Flexible Uncertainty Calibration for Machine-Learned Interatomic Potentials, 2025. https://arxiv.org/abs/2510.00721

---

## 给 Codex 的实现指导

Codex 根据本页面实现代码时，应优先创建以下数据结构：

- `FailureVector`
- `FailureScore`
- `FailureLabel`
- `FailureLabeler`
- `FailurePredictor`
- `FailureProfile`

第一阶段不要实现重型 MLIP 调用和 Materials Project API 调用，只保留可替换接口和 mock/test 版本。

本页面的核心实现目标是：给任意晶体结构输出标准化的 FIIR failure vector：

- `f1_geometry`
- `f2_chemistry`
- `f3_stability`
- `confidence`
- `metadata`
