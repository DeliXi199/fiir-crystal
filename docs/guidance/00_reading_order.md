## 目标

本页面用于指导 Codex 在 GitHub 仓库 `fiir-crystal` 中搭建 FIIR Crystal 项目框架。

## 必读文档

Codex 每次进行架构设计或重要代码修改前，应按顺序阅读：

1. `docs/guidance/01_fiir_project_manual.md`
2. `docs/guidance/02_paper1_crystalfail_bench.md`
3. `docs/guidance/03_paper2_fsal.md`
4. `docs/guidance/04_paper3_discovery_pipeline.md`

## GitHub 目录结构

```
fiir-crystal/
  README.md
  AGENTS.md

  docs/
    guidance/
      00_reading_order.md
      01_fiir_project_manual.md
      02_paper1_crystalfail_bench.md
      03_paper2_fsal.md
      04_paper3_discovery_pipeline.md

    specs/
      failure_taxonomy.md
      fsal_algorithm.md
      discovery_pipeline.md
      evaluation_metrics.md

    decisions/
      ADR-0001-project-scope.md
      ADR-0002-failure-label-design.md
      ADR-0003-axis-aligned-dpo.md

  fiir_crystal/
    failure/
    predictor/
    fsal/
    generation/
    evaluation/
    discovery/

  configs/
  scripts/
  experiments/
  tests/
  notebooks/
```

## Codex 第一阶段任务

第一阶段不要实现完整训练和 DFT，只搭建项目骨架：

1. 创建 Python package skeleton。
2. 创建核心 dataclasses。
3. 创建 module interfaces。
4. 创建配置文件结构。
5. 创建最小 tests。
6. 创建 `docs/specs/` 下的工程规格文档。

## Codex 不应做的事

1. 不要一开始下载大型数据集。
2. 不要直接调用真实 DFT。
3. 不要硬编码本地路径。
4. 不要把所有逻辑写进一个大脚本。
5. 不要跳过 `docs/specs/` 直接根据长篇指导文档写代码。

## 最小闭环

FIIR Crystal 的最小闭环是：

1. 输入候选晶体结构。
2. 计算 F1/F2/F3 failure vector。
3. 构造 matched axis-aligned preference pairs。
4. 调用 FSAL trainer 接口。
5. 评估 failure-rate / stability / novelty / diversity。
6. 将结果传入 discovery pipeline skeleton。
