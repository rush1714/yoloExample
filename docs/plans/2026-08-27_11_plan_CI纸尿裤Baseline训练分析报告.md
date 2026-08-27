# CI 纸尿裤 Baseline 训练分析报告

日期：2026-08-27  
训练档位：baseline  
状态：100 epoch 训练、验证、EC2 关键产物归档与本地下载均已完成。

## 1. 训练概览

| 项目 | 结果 |
|---|---|
| 任务 | 单类别目标检测：纸尿裤/diaper（class_id=0） |
| 数据集 | `CI/v2026-08-27_01` |
| 训练模型 | `yolo11s.pt` |
| 训练轮数 | 100 |
| 图片尺寸 | 960 |
| batch | `-1`（Ultralytics 自动 batch） |
| 设备 | EC2 A10G，CUDA:0 |
| 实际 Ultralytics run | `runs/detect/models/train/diaper_category_CI_v2026-08-27_01-4` |
| 数据集划分 | train=585，val=168，test=84，总计=837 |

Baseline 实际运行目录：

```text
/home/ec2-user/yoloExample/runs/detect/models/train/diaper_category_CI_v2026-08-27_01-4
```

本地归档目录：

```text
outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/
```

## 2. Baseline 最佳指标

最佳指标出现在 epoch 64：

| 指标 | 最佳结果 |
|---|---:|
| Precision | 0.76262 |
| Recall | 0.73398 |
| mAP50 | 0.74910 |
| mAP50-95 | 0.37312 |
| train box loss | 1.54988 |
| train cls loss | 0.89301 |
| train dfl loss | 1.26608 |
| val box loss | 1.81775 |
| val cls loss | 1.09854 |
| val dfl loss | 1.53733 |

## 3. 与 Smoke 结果对比

| 指标 | Smoke：yolo11n / 640 / 5 epoch | Baseline：yolo11s / 960 / 100 epoch | 绝对提升 | 相对提升 |
|---|---:|---:|---:|---:|
| Precision | 0.72844 | 0.76262 | +0.03418 | +4.7% |
| Recall | 0.63563 | 0.73398 | +0.09835 | +15.5% |
| mAP50 | 0.67553 | 0.74910 | +0.07357 | +10.9% |
| mAP50-95 | 0.32708 | 0.37312 | +0.04604 | +14.1% |

### 对比结论

- Baseline 对漏检改善最明显：Recall 增加 9.84 个百分点，说明更大的模型、960 尺寸和充分训练提高了纸尿裤目标的召回。
- mAP50 和 mAP50-95 均提升，说明不仅在宽松 IoU 下更容易检测到目标，框定位质量也有改善。
- Precision 只提高 3.42 个百分点，意味着后续主要瓶颈更可能是数据和标注质量，而不仅是继续增大模型。
- 该对比同时改变了模型容量、输入尺寸和训练轮数，不能把提升单独归因于 `yolo11s`、960 或 100 epoch 中任一因素。

## 4. 训练指标图

### 4.1 训练/验证指标总览

`results.png` 汇总展示了训练损失、验证损失、Precision、Recall、mAP50 和 mAP50-95 随 epoch 的变化。

![baseline results](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/results.png)

观察：

- 训练损失整体下降，说明模型持续拟合训练集。
- 验证指标在中后段进入平台期，最佳 mAP50-95 出现在 epoch 64。
- epoch 64 后 train loss 仍下降，但验证 mAP 没有稳定继续提高，说明单纯增加训练轮数收益有限。

### 4.2 PR 曲线

![baseline PR curve](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/BoxPR_curve.png)

PR 曲线用于观察不同置信度阈值下 Precision 与 Recall 的权衡。当前曲线表明模型已具备可用召回，但仍需要通过阈值选择和错误样例分析控制误检。

### 4.3 F1 曲线

![baseline F1 curve](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/BoxF1_curve.png)

F1 曲线可用于选择较均衡的置信度阈值。后续做推理验证时，不建议只使用默认阈值，应结合业务对漏检/误检的容忍度选择阈值。

### 4.4 Precision / Recall 曲线

![baseline Precision curve](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/BoxP_curve.png)

![baseline Recall curve](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/BoxR_curve.png)

建议后续在业务验证集中分别观察：

- 提高阈值后误检是否明显下降；
- 降低阈值后漏检是否明显改善；
- 是否存在一批固定场景始终漏检，例如远景小包装、强反光、边缘遮挡、多包装粘连。

### 4.5 混淆矩阵

![baseline confusion matrix](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/confusion_matrix.png)

![baseline normalized confusion matrix](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/confusion_matrix_normalized.png)

当前是单类别任务，混淆矩阵主要用于观察目标和背景之间的误检/漏检关系。重点关注背景被预测成纸尿裤的比例，以及真实纸尿裤未被预测出的比例。

### 4.6 标签分布图

![baseline labels](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/labels.jpg)

标签分布图用于检查框的位置、尺寸和类别分布是否异常。如果出现大量极小框、极大框、集中在图像某一角落的框，需要回看标注规范和原图质量。

## 5. 验证集人工复核图

下面是验证集标签与预测结果对照图，建议优先人工复核这些图。

### val batch 0

标注图：

![baseline val batch0 labels](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/val_batch0_labels.jpg)

预测图：

![baseline val batch0 pred](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/val_batch0_pred.jpg)

### val batch 1

标注图：

![baseline val batch1 labels](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/val_batch1_labels.jpg)

预测图：

![baseline val batch1 pred](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/val_batch1_pred.jpg)

### val batch 2

标注图：

![baseline val batch2 labels](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/val_batch2_labels.jpg)

预测图：

![baseline val batch2 pred](../../outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/plots/val_batch2_pred.jpg)

复核方式：

- 对比 labels 与 pred，逐张标出漏检、误检、重复框、框偏移和标注问题。
- 若发现 pred 框明显正确但 labels 漏标，应归为 `annotation_issue`，不要误判为模型错误。
- 若 labels 本身框过大/过小，会直接限制 mAP50-95 上限，应优先修正标注。

## 6. 训练趋势与最佳 Epoch 分析

### 6.1 收敛过程

- 前 1~10 epoch 指标波动较大，属于 warmup、自动学习率搜索和小样本验证波动的正常表现。
- 约 epoch 45~55 时，mAP50 已稳定在约 0.74 附近。
- epoch 64 达到最佳 mAP50-95=0.37312，同时 Precision=0.76262、Recall=0.73398，保存为 `best.pt`。
- epoch 65~100 的 train loss 仍持续下降，例如 train box loss 最终降至约 1.36，但验证 mAP50-95 大多在 0.36~0.37 区间波动，没有持续超过 epoch 64。

这说明：训练集拟合仍在增强，但验证集泛化已接近平台期。Ultralytics 正确选择 epoch 64 的 `best.pt`，不应使用 epoch 100 的 `last.pt` 替代。

### 6.2 时间与吞吐

`results.csv` 显示 100 epoch 累计约 1269 秒，约 21 分钟；按完整 epoch 计算约 12~13 秒/epoch。这与 A10G、585 张训练图、168 张验证图、imgsz=960、yolo11s 的配置相符。

A10G 训练期间 GPU 利用率约 85%、显存占用约 5.2GB、温度约 51°C，属于健康状态。`batch=-1` 表示 Ultralytics 自动选择 batch，不表示单图训练。

## 7. 当前效果边界

Baseline 已经证明模型具有较稳定的纸尿裤检测能力，但还不能直接作为上线模型：

- Recall 0.734：仍可能漏掉约四分之一的目标，需优先检查小目标、遮挡、反光、远景、边缘截断包装。
- mAP50-95 0.373：严格框定位仍有改进空间，需关注框过大、框过小、多个相邻包装粘连和标注框不一致。
- 单类别任务中 Precision/Recall 的提升可能受数据划分相似度影响，必须结合 test 集与现场新图片验证，而不能只看 val 指标。

## 8. 人工复核与问题归类

本地 baseline 归档：

```text
outputs/ec2/diaper_category/CI/v2026-08-27_01/baseline/
```

发现问题后按类型复制样例到：

```text
review/false_positive/    # 非纸尿裤被框出
review/false_negative/    # 真实纸尿裤漏检
review/wrong_class/       # 单类阶段通常较少，保留给未来多类扩展
review/duplicate_box/     # 同一商品多个重叠框
review/bad_image/         # 模糊、反光、遮挡、远景、曝光异常
review/annotation_issue/  # 漏标、框偏移、框过大/过小、规范不一致
review/ok/                # 正确检测代表样例
```

## 9. Baseline 后的质量门槛

在进入 improve 前，建议完成：

- [ ] 抽查 val/test 至少 50~100 张，确认真实纸尿裤没有系统性漏标。
- [ ] 至少归档一批漏检、误检、重复框和标注问题样例。
- [ ] 对小目标、遮挡商品、半截包装、多个相邻包装制定一致标注规则。
- [ ] 用 20~50 张尚未参与训练的真实门店图片完成现场推理检查。
- [ ] 判断错误主要来自模型容量不足，还是数据/标注/图片质量问题。

## 10. 下一步建议

### 推荐优先级：先分析，再决定 Improve

当前 baseline 相比 smoke 已有明显提升，但最佳指标在 epoch 64 后未继续提升。因此不建议仅因“模型更大”立刻进入 improve；先复核错误样例和标注质量通常更有价值。

### 确认需要 improve 时

```bash
make 05-1-diaper-ec2-train-improve \
  DIAPER_COUNTRY=CI \
  DIAPER_VERSION=v2026-08-27_01 \
  DIAPER_LABEL_NAME=diaper \
  EC2_TRAIN_BATCH=-1 \
  EC2_TRAIN_DEVICE=0 \
  EC2_EXECUTE=1

make 05-2-diaper-ec2-evaluate-improve \
  DIAPER_COUNTRY=CI \
  DIAPER_VERSION=v2026-08-27_01 \
  EC2_TRAIN_PROFILE=improve \
  EC2_EXECUTE=1

make 05-3-diaper-ec2-download-artifacts-improve \
  DIAPER_COUNTRY=CI \
  DIAPER_VERSION=v2026-08-27_01 \
  EC2_TRAIN_PROFILE=improve \
  EC2_EXECUTE=1
```

Improve 配置：`yolo11m.pt`、`imgsz=960`、`epochs=150`。必须与 baseline 使用同一数据划分，以保证对比有效。

## 11. 结论

Baseline 训练成功建立了当前 CI 纸尿裤大类检测基线：`mAP50=0.74910`、`mAP50-95=0.37312`、`Precision=0.76262`、`Recall=0.73398`。

与 smoke 相比，Recall 是最明显的收益项，说明现有模型/训练配置显著减少了漏检。后续优化应以人工错误归类为驱动；优先修订数据和标注问题，再用 improve 训练确认更大模型是否带来可复现的收益。
