# CI 纸尿裤 Baseline 训练分析计划

## 输入

已下载 EC2 baseline 训练归档：

```text
outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/
```

训练配置：

- profile：`baseline`
- 模型：`yolo11s.pt`
- epochs：`100`
- imgsz：`960`
- batch：`-1`（Ultralytics 自动选择）
- device：EC2 A10G CUDA:0
- 实际 run：`runs/detect/models/train/diaper_category_CI_v2026-08-27_01-4`
- 数据集：train=585，val=168，test=84，总计=837

Baseline 最佳指标：

- best epoch：64
- precision：0.76262
- recall：0.73398
- mAP50：0.74910
- mAP50-95：0.37312

Smoke 对照配置：`yolo11n.pt`、640、5 epoch，最佳指标：precision=0.72844、recall=0.63563、mAP50=0.67553、mAP50-95=0.32708。

## 计划

1. 读取 baseline 的 `results.csv`，分析最佳 epoch、训练/验证损失与后半程指标趋势。
2. 将 baseline 与 smoke 进行同数据集条件下的指标对比，计算绝对提升和相对提升。
3. 说明比较边界：baseline 同时改变了模型容量（n→s）、训练尺寸（640→960）和训练轮数（5→100），因此不能将提升完全归因于单一因素。
4. 分析 best epoch=64 对后续训练策略的含义，以及是否应直接进入 improve（yolo11m）或先做人工错误复核/数据清洗。
5. 生成正式报告：

```text
docs/plans/2026-08-27_11_plan_CI纸尿裤Baseline训练分析报告.md
```

报告包含训练配置、指标趋势、smoke 对比、结论、可视化人工复核建议、improve 的进入条件和推荐命令。

## 不做

- 不修改模型、数据集或训练参数。
- 不连接 EC2。
- 不自动启动 improve 训练。
