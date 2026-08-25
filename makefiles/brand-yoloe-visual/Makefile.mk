# YOLOE visual prompt + 品牌参考图预标注完整流程

# ── 品牌参考图导入参数 ───────────────────────────────────────
# YOLOE 仍复用 YOLO-World 的阈值、候选清单、类别过滤等公共预标注参数；若只用本模块，以下默认值可独立工作。
PSEUDO_NMS_IOU     ?= 0.45
PSEUDO_CONTAINMENT ?= 0.85
PSEUDO_MAX_AREA_RATIO ?= 0.45
PSEUDO_CROSS_BRAND_DEDUP ?= 1
PSEUDO_CROSS_BRAND_IOU ?= 0.35
PSEUDO_CROSS_BRAND_CONTAINMENT ?= 0.80
PSEUDO_CONF       ?= 0.03
PSEUDO_IMGSZ      ?= 960
PSEUDO_LIMIT      ?=
PSEUDO_USE_OCR_CANDIDATES ?= 1
PSEUDO_LIMIT_ARG  := $(if $(PSEUDO_LIMIT),--limit $(PSEUDO_LIMIT),)
PSEUDO_CANDIDATES_ARG := $(if $(filter 1 true yes,$(PSEUDO_USE_OCR_CANDIDATES)),--candidates-file $(OCR_CANDIDATES_FILE),)
# 品牌参考图 Excel；应包含品牌列和图片 URL 列。
VISUAL_PROMPTS_EXCEL ?= /Users/guobiao/Downloads/品牌图片2_1786525402668.xlsx
# 品牌列名；脚本会按该列创建 visual_prompts/<品牌>/ 目录。
VISUAL_PROMPTS_BRAND_COLUMN ?= brand
# 图片 URL 列名；支持一格多个 URL。
VISUAL_PROMPTS_ATTACH_COLUMN ?= attach_file
# 品牌参考图保存根目录。
VISUAL_PROMPTS_OUTPUT_ROOT ?= $(SHARED_DATASET_ROOT)/visual_prompts
# 品牌参考图下载报告目录。
VISUAL_PROMPTS_METADATA_DIR ?= $(VISUAL_PROMPTS_OUTPUT_ROOT)/metadata
# 品牌参考图下载并发数。
VISUAL_PROMPTS_WORKERS ?= 8
# 单张品牌参考图下载超时时间。
VISUAL_PROMPTS_TIMEOUT ?= 30
# 最多导入多少个去重后的 URL；空表示全量。
VISUAL_PROMPTS_LIMIT ?=
VISUAL_PROMPTS_LIMIT_ARG := $(if $(VISUAL_PROMPTS_LIMIT),--limit $(VISUAL_PROMPTS_LIMIT),)

# ── YOLOE Visual Prompt 参数 ────────────────────────────────
# YOLOE visual prompt 权重路径。
PSEUDO_VISUAL_MODEL ?= $(PROJECT_ROOT)/models/yoloe-26m-seg.pt
# 参考图根目录；结构为 visual_prompts/<品牌名>/*.jpg|png。
PSEUDO_VISUAL_REFERENCE_ROOT ?= $(SHARED_DATASET_ROOT)/visual_prompts
# 每个品牌最多使用多少张参考图；空表示全部。
PSEUDO_VISUAL_REFERENCE_LIMIT ?=
# 推理设备；M 系 Mac 默认 mps，CUDA 可设 0，CPU 可设 cpu。
PSEUDO_VISUAL_DEVICE ?= mps
PSEUDO_VISUAL_REFERENCE_LIMIT_ARG := $(if $(PSEUDO_VISUAL_REFERENCE_LIMIT),--reference-limit $(PSEUDO_VISUAL_REFERENCE_LIMIT),)
PSEUDO_VISUAL_DEVICE_ARG := $(if $(PSEUDO_VISUAL_DEVICE),--device $(PSEUDO_VISUAL_DEVICE),)
PSEUDO_VISUAL_CROSS_BRAND_DEDUP_ARG := $(if $(filter 1 true yes,$(PSEUDO_CROSS_BRAND_DEDUP)),--cross-brand-dedup,--no-cross-brand-dedup)

.PHONY: visual-prompts-import step-3-pseudo-label-visual workflow-to-ls-visual pseudo-label-visual

visual-prompts-import: ## 从品牌图片 Excel 下载 YOLOE visual prompt 参考图
	$(VENV_BIN)/python scripts/data_import/import_visual_prompts_from_excel.py \
		--excel '$(VISUAL_PROMPTS_EXCEL)' \
		--brand-column '$(VISUAL_PROMPTS_BRAND_COLUMN)' \
		--url-column '$(VISUAL_PROMPTS_ATTACH_COLUMN)' \
		--output-root $(VISUAL_PROMPTS_OUTPUT_ROOT) \
		--metadata-dir $(VISUAL_PROMPTS_METADATA_DIR) \
		--workers $(VISUAL_PROMPTS_WORKERS) \
		--timeout $(VISUAL_PROMPTS_TIMEOUT) \
		$(VISUAL_PROMPTS_LIMIT_ARG)

step-3-pseudo-label-visual: brand-yaml pseudo-label-visual ## 3. 使用 YOLOE visual prompt 和品牌参考图生成预标注

workflow-to-ls-visual: step-1-import-excel step-2-ocr step-3-pseudo-label-visual step-4-import-ls ## YOLOE visual prompt 到 Label Studio

pseudo-label-visual: ## 使用 YOLOE visual prompt 和品牌参考图生成预标注
	$(VENV_BIN)/python scripts/pseudo_label/generate_yoloe_visual.py \
		--raw-dir $(RAW_DIR) \
		--output-root $(PSEUDO_ROOT) \
		--reference-root $(PSEUDO_VISUAL_REFERENCE_ROOT) \
		--model $(PSEUDO_VISUAL_MODEL) \
		--brand-library $(BRAND_LIBRARY) \
		$(BRAND_FILTER_ARG) \
		$(COMPACT_CLASS_IDS_ARG) \
		--nms-iou $(PSEUDO_NMS_IOU) \
		--containment-threshold $(PSEUDO_CONTAINMENT) \
		--max-area-ratio $(PSEUDO_MAX_AREA_RATIO) \
		$(PSEUDO_VISUAL_CROSS_BRAND_DEDUP_ARG) \
		--cross-brand-iou $(PSEUDO_CROSS_BRAND_IOU) \
		--cross-brand-containment $(PSEUDO_CROSS_BRAND_CONTAINMENT) \
		--conf $(PSEUDO_CONF) \
		--imgsz $(PSEUDO_IMGSZ) \
		$(PSEUDO_VISUAL_DEVICE_ARG) \
		$(PSEUDO_LIMIT_ARG) \
		$(PSEUDO_CANDIDATES_ARG) \
		$(PSEUDO_VISUAL_REFERENCE_LIMIT_ARG)
