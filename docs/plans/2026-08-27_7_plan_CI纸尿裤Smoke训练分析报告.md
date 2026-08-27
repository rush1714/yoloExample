# CI 纸尿裤 Smoke 训练分析报告

日期：2026-08-27  
训练档位：smoke  
状态：训练、验证、EC2 关键产物下载均已完成。

## 1. 训练概览

| 项目 | 结果 |
|---|---|
| 任务 | 单类别目标检测：纸尿裤（class_id=0） |
| 数据集 | `CI/v2026-08-27_01` |
| 训练模型 | `yolo11n.pt` |
| 训练轮数 | 5 |
| 图片尺寸 | 640 |
| batch | 16 |
| 设备 | EC2 A10G，CUDA:0 |
| 实际 Ultralytics run | `runs/detect/models/train/diaper_category_CI_v2026-08-27_01-3` |
| 数据集划分 | train=585，val=168，test=84，总计=837 |
| 训练增强 | mosaic=1.0、fliplr=0.5、scale=0.5、auto_augment=randaugment |

本次 smoke 训练成功完成，说明以下基础链路已打通：EC2 PyTorch 环境、A10 GPU、Ultralytics、绝对路径 YAML、数据集结构、YOLO 标签、训练产物归档和下载。

## 2. 指标趋势

| Epoch | Precision | Recall | mAP50 | mAP50-95 | train box loss | train cls loss | val box loss |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.0139 | 0.5201 | 0.0624 | 0.0231 | 2.1167 | 2.8737 | 1.8943 |
| 2 | 0.6542 | 0.2869 | 0.4311 | 0.1819 | 1.9806 | 1.8548 | 1.9224 |
| 3 | 0.6117 | 0.5708 | 0.5679 | 0.2534 | 1.9140 | 1.7252 | 1.8636 |
| 4 | 0.6723 | 0.6118 | 0.6171 | 0.2828 | 1.8663 | 1.5745 | 1.8580 |
| 5 | **0.7284** | **0.6356** | **0.6755** | **0.3271** | **1.8072** | **1.4777** | **1.7951** |

## 3. 结果解读

### 3.1 Smoke 目标达成

Smoke 阶段的目标不是取得最终精度，而是验证数据与训练闭环是否正确。本次 5 epoch 后：

- `mAP50` 从 0.0624 提升到 0.6755。
- `mAP50-95` 从 0.0231 提升到 0.3271。
- 训练 box / cls / dfl loss 都持续下降。
- 验证 box loss 从 1.8943 降至 1.7951。

结论：模型已经从数据中学到纸尿裤目标的可泛化视觉特征，数据集不是空标注、类别错位或标签坐标完全异常；训练链路具备进入 baseline 阶段的条件。

### 3.2 当前指标仍不能作为最终效果结论

第 5 epoch 的结果：

```text
Precision: 0.7284
Recall:    0.6356
mAP50:     0.6755
mAP50-95:  0.3271
```

解释：

- Precision 0.73：当前预测出的纸尿裤框中，大约七成具有较好匹配；仍可能存在货架、包装图案或相邻商品误检。
- Recall 0.64：约三分之一真实纸尿裤目标尚未被召回，可能来自小目标、遮挡、反光、远距离货架、标注遗漏或 5 epoch 未充分收敛。
- mAP50 0.68：在 IoU=0.5 的宽松定位标准下已有可用学习信号。
- mAP50-95 0.33：严格定位精度仍偏低，说明框的位置、大小和边界质量仍有较大优化空间。

5 epoch 训练的 warmup 已占 3 epoch，因此真正稳定学习阶段只有约 2 epoch；不能据此直接比较模型上限或选择最终模型。

## 4. 数据规模与 PoC 建议

当前总图片 837 张，已高于“首轮有效验证 300~500 张”的建议范围。

这不影响本次 smoke 链路验证，但在直接启动 baseline 前，建议先完成数据质量抽检，而不是盲目继续增加标注量：

1. 抽查 val/test 中至少 50~100 张图片。
2. 确认所有纸尿裤包装都已标注，且没有把整排货架、价签、宣传海报当成纸尿裤框。
3. 统一遮挡商品、边缘截断商品、远景小包装、多包装重叠场景的标注规则。
4. 关注 train/val/test 是否来自同一批相似货架/门店；避免随机划分造成过于乐观的验证集结果。
5. 如果抽检发现标注噪声或图片质量问题，应先修订标签再训练 baseline。

## 5. 人工复核建议

本地已下载的归档目录：

```text
outputs/ec2/diaper_category/CI/v2026-08-27_01/smoke/
```

优先对照以下图片：

```text
plots/val_batch0_labels.jpg  <-> plots/val_batch0_pred.jpg
plots/val_batch1_labels.jpg  <-> plots/val_batch1_pred.jpg
plots/val_batch2_labels.jpg  <-> plots/val_batch2_pred.jpg
```

将发现的样例按问题复制到：

```text
review/false_positive/    # 误检：非纸尿裤被框出
review/false_negative/    # 漏检：真实纸尿裤未被框出
review/wrong_class/       # 类别错误：当前单类阶段通常较少
review/duplicate_box/     # 同一商品重复框
review/bad_image/         # 模糊、反光、遮挡、过暗、远景等图片质量问题
review/annotation_issue/  # 漏标、框偏移、框过大/过小、标注规范不一致
review/ok/                # 检测与标注均合理的代表样例
```

本次归档已包含：`best.pt`、`last.pt`、`exported-best.pt`、`results.csv`、`args.yaml`、PR/F1/P/R 曲线、混淆矩阵、训练批次和验证批次可视化图。

## 6. 下一步建议

### 6.1 先完成基线前质量门槛

在启动 baseline 前，至少完成：

- [ ] 复核 50~100 张 val/test 图片的标注完整性和框质量。
- [ ] 从验证图中按问题类型至少归档一批典型错误样例。
- [ ] 确认没有系统性把货架、价格标签或背景海报标成纸尿裤。
- [ ] 记录需要更新的标注规范，并在后续补标时统一执行。

### 6.2 质量门槛通过后建立 baseline

```bash
make 06-diaper-ec2-train-baseline \
  DIAPER_COUNTRY=CI \
  DIAPER_VERSION=v2026-08-27_01 \
  EC2_TRAIN_BATCH=16 \
  EC2_TRAIN_DEVICE=0 \
  EC2_EXECUTE=1

make 04-diaper-ec2-evaluate \
  DIAPER_COUNTRY=CI \
  DIAPER_VERSION=v2026-08-27_01 \
  EC2_TRAIN_PROFILE=baseline \
  EC2_EXECUTE=1

make 05-diaper-ec2-download-artifacts \
  DIAPER_COUNTRY=CI \
  DIAPER_VERSION=v2026-08-27_01 \
  EC2_TRAIN_PROFILE=baseline \
  EC2_EXECUTE=1
```

Baseline 配置：`yolo11s.pt`、`imgsz=960`、`epochs=100`。

### 6.3 Improve 阶段触发条件

只有在 baseline 的错误样例已被归类、数据/标注问题已有处理方案后，再执行：

```bash
make 07-diaper-ec2-train-improve \
  DIAPER_COUNTRY=CI \
  DIAPER_VERSION=v2026-08-27_01 \
  EC2_TRAIN_BATCH=16 \
  EC2_TRAIN_DEVICE=0 \
  EC2_EXECUTE=1
```

Improve 配置：`yolo11m.pt`、`imgsz=960`、`epochs=150`。若显存、训练耗时或效果分析显示没有收益，再调整 batch、epoch 或模型规模。

## 7. 结论

本次 smoke 训练是成功的基础验证：模型在 5 epoch 内出现明确收敛，mAP50 达到 0.6755，证明当前 CI 纸尿裤大类数据具有可训练性。

下一步不建议立即把结论定为“模型已经可上线”，而应先利用已下载可视化图完成错误类型归档和标注质量检查。质量门槛通过后，再用 `yolo11s.pt / 960 / 100 epoch` 建立正式 baseline，并与 improve 阶段进行受控对比。
