# 纸尿裤大类训练评估摘要

## 训练配置

- profile: `smoke`
- model: `yolo11n.pt`
- imgsz: `640`
- epochs: `5`
- batch: `16`
- device: `0`
- run_dir: `/home/ec2-user/yoloExample/models/train/diaper_category_CI_v2026-08-27_01`
- dataset_yaml: `config/generated/diaper_category_CI_v2026-08-27_01.yaml`
- dataset_root: `/home/ec2-user/yoloExample/datasets/diaper_category/CI/v2026-08-27_01`
- dataset_images: train=585, val=168, test=84, total=837`

## 最佳指标

- 未找到 `results.csv`，请确认训练是否完成或 run 目录是否正确。

## 已归档关键产物


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

首轮 PoC 建议先用 300~500 张有效标注图验证闭环，再扩大数据量。
