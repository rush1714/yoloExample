# CI 纸尿裤 Smoke 训练分析计划

## 输入

已下载 EC2 训练归档：

```text
outputs/ec2/diaper_category/CI/v2026-08-27_01/smoke/
```

训练配置：

- profile：`smoke`
- 模型：`yolo11n.pt`
- epochs：`5`
- imgsz：`640`
- batch：`16`
- 设备：EC2 A10G CUDA:0
- 数据集：train=585，val=168，test=84，total=837

训练结束真实目录：

```text
/home/ec2-user/yoloExample/runs/detect/models/train/diaper_category_CI_v2026-08-27_01-3
```

## 已读取的关键指标

第 5 epoch：

- precision：0.72844
- recall：0.63563
- mAP50：0.67553
- mAP50-95：0.32708
- train box loss：1.80719
- train cls loss：1.47768
- train dfl loss：1.26017

## 分析与报告计划

1. 基于 `metrics/results.csv` 分析 5 个 epoch 的收敛趋势、指标波动和 smoke 阶段结果。
2. 说明 smoke 的目的主要是验证数据集、训练链路和模型可学习性，不能作为正式精度结论。
3. 对照首轮 PoC 建议，指出当前总图片 837 张已超过建议的 300~500 张，但可用于 smoke；baseline 前应优先人工复核数据与样例质量。
4. 根据归档产物清单和现有 `evaluation-summary.md`，给出人工复核路径：
   - `plots/val_batch*_labels.jpg` 与 `plots/val_batch*_pred.jpg` 对照。
   - 将问题样例归档到 review 的 false_positive、false_negative、duplicate_box、bad_image、annotation_issue 等目录。
5. 输出正式分析报告：

```text
docs/plans/2026-08-27_7_plan_CI纸尿裤Smoke训练分析报告.md
```

报告包含：训练配置、指标表、趋势、结论、风险、人工复核建议、baseline 执行门槛与下一步命令。

## 不做

- 不修改模型或数据集。
- 不连接 EC2。
- 不擅自启动 baseline 或 improve 训练。
