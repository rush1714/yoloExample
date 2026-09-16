# scripts 脚本分类说明

本目录按数据来源、模型处理阶段和运行位置拆分脚本。Makefile 只负责组合参数和编排，具体逻辑应放在下面对应目录。

## 目录职责

| 目录 | 职责 | 典型入口 |
|---|---|---|
| `common/` | 跨流程复用工具，例如品牌库读取、Ultralytics 配置。 | 被其它脚本 import，不直接作为 CLI 使用。 |
| `config/` | 生成训练配置、品牌配置、单类别 YAML。 | `write_brand_yolo_yaml.py`、`write_single_class_yolo_yaml.py` |
| `data_import/` | 从 Excel、URL 或本地清单导入图片和参考图；不做训练。 | `import_images_from_excel.py`、`import_visual_prompts_from_excel.py` |
| `ocr/` | 图片文字识别和品牌候选筛选。 | `filter_brand_candidates.py`、`filter_brand_candidates_llm.py` |
| `pseudo_label/` | 自动/半自动预标注，包括 YOLO-World 与 YOLOE visual prompt。 | `generate_yolo_world.py`、`generate_yoloe_visual.py`、`ab_test_yolo_world.py` |
| `label_studio/` | Label Studio 导入、导出和标注转 YOLO。 | `apply_import.py`、`generate_*_import.py`、`export*_to_yolo.py` |
| `training/` | 本地训练和数据集校验。 | `train.py`、`validate_dataset.py` |
| `inference/` | 本地推理。 | `predict.py` |
| `s3/` | S3 配置、上传和本地图片代理。 | `upload_images_to_s3.py`、`s3_image_proxy.py` |
| `ec2/` | EC2 远端编排。 | `diaper_workflow.py`、`s3_workflow.py` |
| `cloud/` | 兼容旧路径的轻量入口，不再放主要实现。 | `ec2_diaper_workflow.py`、`ec2_s3_workflow.py` |

## 迁移规则

- 新增 EC2 编排能力放到 `scripts/ec2/`，公共 SSH / rsync / dry-run 工具放到 `scripts/ec2/common.py`。
- `scripts/cloud/` 仅保留兼容入口，避免旧命令或外部调用立即失效。
- 新增图片来源脚本放 `data_import/`；新增 S3 上传/代理放 `s3/`；新增标注转换放 `label_studio/`。
- 新增训练和数据校验逻辑放 `training/`；新增推理逻辑放 `inference/`。

## 常用脚本示例

```bash
# 品牌库生成多类别或单品牌 YOLO YAML
uv run python scripts/config/write_brand_yolo_yaml.py \
  --brand-library config/brand_keywords.json \
  --data-yaml config/generated/multibrand.yaml \
  --pseudo-yaml config/generated/multibrand_pseudo.yaml \
  --dataset-root ../../datasets/multibrand

# 生成单类别 YOLO YAML
uv run python scripts/config/write_single_class_yolo_yaml.py \
  --output config/generated/local_demo.yaml \
  --dataset-root datasets/local/demo \
  --class-name diaper

# 从 Excel 下载图片
uv run python scripts/data_import/import_images_from_excel.py \
  --excel /path/images.xlsx \
  --column 整改后图片URL \
  --output-dir datasets/multibrand/raw/images \
  --metadata-dir datasets/multibrand/raw/metadata

# 常规 OCR 筛选品牌候选
uv run python scripts/ocr/filter_brand_candidates.py \
  --raw-dir datasets/multibrand/raw/images \
  --output-dir datasets/multibrand/ocr \
  --brand-library config/brand_keywords.json \
  --engine rapidocr \
  --workers 4

# Ollama 视觉 OCR 筛选品牌候选
uv run python scripts/ocr/filter_brand_candidates_llm.py \
  --raw-dir datasets/multibrand/raw/images \
  --output-dir datasets/multibrand/ocr \
  --brand-library config/brand_keywords.json \
  --model gemma3:12b \
  --workers 1

# YOLO-World 预标注
uv run python scripts/pseudo_label/generate_yolo_world.py \
  --raw-dir datasets/multibrand/raw/images \
  --output-root datasets/multibrand/pseudo \
  --brand-library config/brand_keywords.json \
  --model models/yolov8s-world.pt \
  --conf 0.03 \
  --imgsz 960

# YOLOE visual prompt 预标注
uv run python scripts/pseudo_label/generate_yoloe_visual.py \
  --raw-dir datasets/multibrand/raw/images \
  --output-root datasets/multibrand/pseudo \
  --reference-root datasets/multibrand/visual_prompts \
  --brand-library config/brand_keywords.json \
  --model models/yoloe-26m-seg.pt \
  --device mps

# Label Studio 导入和导出转换
uv run python scripts/label_studio/generate_import.py \
  --raw-report datasets/multibrand/raw/metadata/download_report.csv \
  --pseudo-root datasets/multibrand/pseudo \
  --output datasets/multibrand/label_studio/multibrand_label_studio_import.json \
  --brand-library config/brand_keywords.json
uv run python scripts/label_studio/export_to_yolo.py \
  --input datasets/multibrand/label_studio/exports/label_studio_export.json \
  --output-root datasets/multibrand \
  --pseudo-root datasets/multibrand/pseudo \
  --brand-library config/brand_keywords.json

# 本地训练与推理
uv run python scripts/training/validate_dataset.py --data config/generated/multibrand.yaml
uv run python scripts/training/train.py \
  --data config/generated/multibrand.yaml \
  --base-model models/yolo26m.pt \
  --epochs 50 \
  --imgsz 960 \
  --batch -1 \
  --device mps
uv run python scripts/inference/predict.py data/samples/multibrand-shelf.webp \
  --model models/multibrand-best.pt \
  --output-dir outputs/predict

# S3 图片管理
uv run python scripts/s3/upload_images_to_s3.py \
  --config config/brand_s3_ec2.local.yaml \
  --dataset-name demo \
  --label-name diaper \
  --input-dir /path/to/images \
  --bucket <bucket> \
  --prefix yolo-training/demo
uv run python scripts/s3/s3_image_proxy.py \
  --config config/brand_s3_ec2.local.yaml \
  --bucket <bucket> \
  --region ap-southeast-1

# EC2 编排（默认 dry-run；加 --execute 才真实执行）
uv run python scripts/ec2/diaper_workflow.py train \
  --host <host> \
  --user ec2-user \
  --key /path/key.pem \
  --country CI \
  --version v2026-08-28 \
  --base-model yolo26m.pt \
  --epochs 100 \
  --imgsz 960 \
  --run-name yolo26m_img960_e100
uv run python scripts/ec2/s3_workflow.py train \
  --host <host> \
  --user ec2-user \
  --key /path/key.pem \
  --dataset-name demo \
  --base-model yolo26m.pt \
  --epochs 100 \
  --imgsz 960 \
  --run-name yolo26m_img960_e100
```
