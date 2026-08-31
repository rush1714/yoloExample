# 纸尿裤大类训练评估摘要

## 训练配置

- profile: `improve`
- model: `yolo26m.pt`
- imgsz: `960`
- epochs: `100`
- batch: `-1`
- device: `0`
- run_dir: `/home/ec2-user/yoloExample/runs/detect/models/train/diaper_category_CI_v2026-08-28-3`
- dataset_yaml: `config/generated/diaper_category_CI_v2026-08-28.yaml`
- dataset_root: `/home/ec2-user/yoloExample/datasets/diaper_category/CI/v2026-08-28`
- dataset_images: train=585, val=168, test=84, total=837`

## 最佳指标

- best_epoch: `82`
- precision(B): `0.7517`
- recall(B): `0.71311`
- mAP50(B): `0.73992`
- mAP50-95(B): `0.37125`
- train/box_loss: `1.70159`
- train/cls_loss: `1.06309`
- train/dfl_loss: ``

## 已归档关键产物

- `weights/best.pt`
- `weights/last.pt`
- `metrics/results.csv`
- `metrics/args.yaml`
- `plots/labels.jpg`
- `plots/train_batch0.jpg`
- `plots/train_batch1.jpg`
- `plots/train_batch2.jpg`
- `plots/train_batch17550.jpg`
- `plots/train_batch17551.jpg`
- `plots/train_batch17552.jpg`
- `plots/val_batch0_pred.jpg`
- `plots/val_batch0_labels.jpg`
- `plots/val_batch1_labels.jpg`
- `plots/val_batch1_pred.jpg`
- `plots/val_batch2_pred.jpg`
- `plots/val_batch2_labels.jpg`
- `plots/BoxPR_curve.png`
- `plots/BoxF1_curve.png`
- `plots/BoxP_curve.png`
- `plots/BoxR_curve.png`
- `plots/confusion_matrix_normalized.png`
- `plots/confusion_matrix.png`
- `plots/results.png`
- `weights/exported-best.pt`

## 人工复核问题分类

请把预测可视化或人工复核样例复制到以下目录，按问题类型沉淀：

- `review/false_positive/`：误检
- `review/false_negative/`：漏检
- `review/wrong_class/`：类别错误（当前单类通常较少）
- `review/duplicate_box/`：重复框
- `review/bad_image/`：图片质量问题
- `review/annotation_issue/`：标注规范或标注错误
- `review/ok/`：效果可接受样例

## 备注

training start
