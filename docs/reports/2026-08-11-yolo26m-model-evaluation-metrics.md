# YOLO26m 训练模型评估口径

日期：2026-08-11

## 目标

为纸尿裤、洗衣粉、香皂、湿巾纸等门店陈列识别模型建立统一评估口径，避免只看单一“准确率”而忽略漏检、误检、计数误差和困难场景表现。

## 核心结论

陈列识别模型不能只看 accuracy。YOLO 检测模型应重点看：

1. mAP50-95：综合检测质量，作为模型总体能力主指标。
2. mAP50：宽松定位下能否识别出目标，适合观察业务可用性。
3. Recall：是否漏检；陈列计数场景优先关注。
4. Precision：是否误检；用于控制误报。
5. per-class 指标：各品牌/品类是否均衡，尤其关注小包装和易混品牌。
6. 计数误差：预测数量与人工数量的差异，这是业务最终指标。
7. 困难集表现：模糊、非正面、遮挡、远距离、小目标图片的专项指标。

## 推荐验收门槛

第一阶段 PoC 可用门槛：

- mAP50 >= 0.70
- mAP50-95 >= 0.45
- Recall >= 0.75
- 主要类别 per-class Recall >= 0.70
- 图片级数量误差中位数 <= 1 件

生产试点建议门槛：

- mAP50 >= 0.80
- mAP50-95 >= 0.55
- Recall >= 0.85
- Precision >= 0.80
- 主要类别 per-class Recall >= 0.80
- 图片级数量误差中位数 <= 1 件，P90 <= 3 件

这些门槛需要根据真实业务容忍度和人工复核成本调整。

## 评估命令

训练后使用 Ultralytics val 评估：

```bash
uv run yolo detect val \
  model=models/multibrand-best.pt \
  data=data/multibrand.yaml \
  imgsz=960 \
  device=mps \
  plots=True
```

在 AWS NVIDIA GPU 上：

```bash
uv run yolo detect val \
  model=models/multibrand-best.pt \
  data=data/multibrand.yaml \
  imgsz=960 \
  device=0 \
  plots=True
```

## 需要查看的输出

训练输出目录通常位于：

```text
models/train/multibrand/
```

重点文件：

- results.csv：每个 epoch 的训练/验证指标曲线数据。
- results.png：训练过程曲线图。
- weights/best.pt：验证指标最好的模型。
- weights/last.pt：最后一个 epoch 的模型。
- confusion_matrix.png：混淆矩阵，观察类别混淆。
- PR_curve.png：Precision-Recall 曲线。
- F1_curve.png：不同置信度下 F1 表现。
- val_batch*_pred.jpg：验证集预测可视化。
- val_batch*_labels.jpg：验证集人工标注可视化。

## 业务专项评估

建议额外建立 `datasets/multibrand/eval_hard/` 或在 metadata 中标记困难样本：

- blur：模糊图片。
- side_view：非正面/斜拍图片。
- small_object：远距离小目标。
- occlusion：遮挡。
- reflection：反光。
- dense_shelf：密集陈列。

每次训练后分别统计这些困难集的 Recall、Precision、mAP50 和计数误差。

## 业务口径

最终模型好坏应按以下优先级判断：

1. 是否漏掉目标商品：Recall。
2. 数量是否接近人工结果：count error。
3. 品牌/品类是否判断正确：per-class mAP 和混淆矩阵。
4. 框的位置是否足够准：mAP50-95。
5. 推理是否够快：单图耗时、批量吞吐。

对于当前陈列识别项目，召回率和计数误差优先级高于单纯 precision。
