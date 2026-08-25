# 常规 OCR + YOLO-World 预标注 + Label Studio + 训练验证流程

# ── 品牌 YOLO 数据配置参数 ───────────────────────────────────
# 正式训练 YAML 输出路径；默认跟随 BRAND 生成 config/generated/<brand>.yaml。
BRAND_DATA_YAML    ?= $(TRAIN_DATA_YAML)
# 伪标注 YAML 输出路径；用于检查 pseudo/images 和 pseudo/labels。
BRAND_PSEUDO_YAML  ?= $(CONFIG_GENERATED_DIR)/$(DATASET_NAME)_pseudo.yaml

# ── 常规 OCR 参数 ─────────────────────────────────────────────
# OCR 引擎：rapidocr（默认，CPU 快）或 easyocr（备选）。
OCR_ENGINE          ?= rapidocr
# 常规 OCR 并发线程数；调大更快但更占内存。
OCR_WORKERS         ?= 10
# 额外 OCR 关键词参数；会与品牌库关键词合并。
OCR_KEYWORD_ARGS    ?=
# EasyOCR 语言列表；rapidocr 下主要保留为兼容参数。
OCR_LANGUAGES       ?= en
# OCR 文本最低置信度，范围 0-1。
OCR_MIN_CONFIDENCE  ?= 0.2
# 品牌关键词模糊匹配阈值，范围 0-100。
OCR_FUZZY_THRESHOLD ?= 60
# OCR 处理图片数量上限；空表示全量。
OCR_LIMIT           ?=
# 是否复制命中图片到 ocr/candidates；默认只写候选清单。
OCR_COPY_CANDIDATES ?= 0
# 是否从已有 OCR JSON 报告恢复，跳过已完成图片。
OCR_RESUME          ?= 0
OCR_LIMIT_ARG       := $(if $(OCR_LIMIT),--limit $(OCR_LIMIT),)
OCR_COPY_ARG        := $(if $(filter 1 true yes,$(OCR_COPY_CANDIDATES)),--copy-candidates,)
OCR_RESUME_ARG      := $(if $(filter 1 true yes,$(OCR_RESUME)),--resume,)

# ── YOLO-World 预标注参数 ───────────────────────────────────
# YOLO-World 权重路径；可换 s/m/x world 系列模型。
PSEUDO_MODEL      ?= $(PROJECT_ROOT)/models/yolov8s-world.pt
# 额外提示词模板；多品牌模式建议使用 {brand} 占位符。
PSEUDO_PROMPT_ARGS ?=
# 临时额外品牌过滤参数；常规使用 BRAND 即可。
PSEUDO_BRAND_FILTER_ARGS ?=
# 是否为每个品牌补充 "<brand> package" 和 "<brand> diaper package" 提示词。
PSEUDO_INCLUDE_BRAND_PACKAGE_PROMPTS ?= 1
# 同类别重复框 NMS IoU 阈值。
PSEUDO_NMS_IOU     ?= 0.45
# 大框覆盖小框过滤阈值。
PSEUDO_CONTAINMENT ?= 0.85
# 单个框最大面积占整图比例；用于删除整图大框。
PSEUDO_MAX_AREA_RATIO ?= 0.45
# 是否跨品牌去重。
PSEUDO_CROSS_BRAND_DEDUP ?= 1
# 跨品牌重复框 IoU 阈值。
PSEUDO_CROSS_BRAND_IOU ?= 0.35
# 跨品牌覆盖过滤阈值。
PSEUDO_CROSS_BRAND_CONTAINMENT ?= 0.80
# 检测置信度，调低增加召回但误检更多。
PSEUDO_CONF       ?= 0.03
# 推理图片尺寸。
PSEUDO_IMGSZ      ?= 960
# 预标注处理数量上限；空表示全量。
PSEUDO_LIMIT      ?=
# 是否只处理 OCR 候选清单；0 表示全量 raw/images。
PSEUDO_USE_OCR_CANDIDATES ?= 1
PSEUDO_LIMIT_ARG  := $(if $(PSEUDO_LIMIT),--limit $(PSEUDO_LIMIT),)
PSEUDO_CANDIDATES_ARG := $(if $(filter 1 true yes,$(PSEUDO_USE_OCR_CANDIDATES)),--candidates-file $(OCR_CANDIDATES_FILE),)
PSEUDO_BRAND_PACKAGE_ARG := $(if $(filter 1 true yes,$(PSEUDO_INCLUDE_BRAND_PACKAGE_PROMPTS)),--include-brand-package-prompts,)
PSEUDO_CROSS_BRAND_DEDUP_ARG := $(if $(filter 1 true yes,$(PSEUDO_CROSS_BRAND_DEDUP)),--cross-brand-dedup,)

# ── YOLO-World A/B 测试参数 ─────────────────────────────────
AB_MODELS ?= models/yolov8s-world.pt,yolov8m-world.pt,yolov8m-worldv2.pt,yolov8x-worldv2.pt
AB_OUTPUT_ROOT ?= $(DATASET_ROOT)/ab_tests/yolo_world
AB_RUN_NAME ?=
AB_LIMIT ?= 50
AB_PREVIEW_LIMIT ?= 30
AB_USE_OCR_CANDIDATES ?= $(PSEUDO_USE_OCR_CANDIDATES)
AB_RUN_NAME_ARG := $(if $(AB_RUN_NAME),--run-name $(AB_RUN_NAME),)
AB_LIMIT_ARG := $(if $(AB_LIMIT),--limit $(AB_LIMIT),)
AB_CANDIDATES_ARG := $(if $(filter 1 true yes,$(AB_USE_OCR_CANDIDATES)),--candidates-file $(OCR_CANDIDATES_FILE),)
AB_BRAND_PACKAGE_ARG := $(if $(filter 1 true yes,$(PSEUDO_INCLUDE_BRAND_PACKAGE_PROMPTS)),--include-brand-package-prompts,--no-include-brand-package-prompts)
AB_CROSS_BRAND_DEDUP_ARG := $(if $(filter 1 true yes,$(PSEUDO_CROSS_BRAND_DEDUP)),--cross-brand-dedup,--no-cross-brand-dedup)

.PHONY: step-1-import-excel step-2-ocr step-3-pseudo-label step-4-import-ls step-5-export-ls-to-train step-6-train step-7-validate \
	workflow-to-ls workflow-after-ls excel-import ocr pseudo-label brand-yaml ls-import-json ls-to-yolo yolo-world-ab-test

step-1-import-excel: excel-import ## 1. 从 Excel 导入/下载原始图片

step-2-ocr: ocr ## 2. 并行 OCR 识别品牌库关键词并生成候选图片清单

step-3-pseudo-label: brand-yaml pseudo-label ## 3. 使用 YOLO-World 和品牌库提示词生成多品牌预标注

step-4-import-ls: ls-import-json ls-apply ## 4. 生成任务 JSON 并导入 Label Studio

step-5-export-ls-to-train: ls-export ls-to-yolo ## 5. 导出 Label Studio 结果并转换为正式训练集

step-6-train: train ## 6. 训练多品牌 YOLO 模型

step-7-validate: data-validate predict ## 7. 校验正式数据集并用训练模型推理验证

workflow-to-ls: step-1-import-excel step-2-ocr step-3-pseudo-label step-4-import-ls ## 常规 OCR + YOLO-World 到 Label Studio

workflow-after-ls: step-5-export-ls-to-train step-6-train step-7-validate ## Label Studio 人工复核完成后导出、训练并验证

brand-yaml: brand-check ## 根据当前 BRAND 从品牌库生成 YOLO 数据集 YAML
	$(VENV_BIN)/python scripts/config/write_brand_yolo_yaml.py \
		--brand-library $(BRAND_LIBRARY) \
		--data-yaml $(BRAND_DATA_YAML) \
		--pseudo-yaml $(BRAND_PSEUDO_YAML) \
		--dataset-root ../../datasets/$(DATASET_NAME) \
		$(BRAND_FILTER_ARG) \
		$(COMPACT_CLASS_IDS_ARG)

excel-import: ## 从 Excel 指定列下载原始图片到 RAW_DIR
	$(VENV_BIN)/python scripts/data_import/import_images_from_excel.py \
		--excel '$(EXCEL)' \
		--column '$(EXCEL_COLUMN)' \
		--output-dir $(RAW_DIR) \
		--metadata-dir $(RAW_METADATA_DIR) \
		--workers $(EXCEL_WORKERS) \
		--timeout $(EXCEL_TIMEOUT)

ocr: ## 并行 OCR 识别品牌标识库候选图片，输出 OCR_CANDIDATES_FILE
	$(VENV_BIN)/python scripts/ocr/filter_brand_candidates.py \
		--raw-dir $(RAW_DIR) \
		--output-dir $(OCR_OUTPUT_DIR) \
		--engine $(OCR_ENGINE) \
		--brand-library $(BRAND_LIBRARY) \
		$(BRAND_FILTER_ARG) \
		$(OCR_KEYWORD_ARGS) \
		--languages $(OCR_LANGUAGES) \
		--min-confidence $(OCR_MIN_CONFIDENCE) \
		--fuzzy-threshold $(OCR_FUZZY_THRESHOLD) \
		--workers $(OCR_WORKERS) \
		$(OCR_LIMIT_ARG) \
		$(OCR_COPY_ARG) \
		$(OCR_RESUME_ARG)

pseudo-label: ## 生成 YOLO-World 预标注，默认使用 OCR 候选清单和品牌库提示词
	$(VENV_BIN)/python scripts/pseudo_label/generate_yolo_world.py \
		--raw-dir $(RAW_DIR) \
		--output-root $(PSEUDO_ROOT) \
		--model $(PSEUDO_MODEL) \
		--brand-library $(BRAND_LIBRARY) \
		$(BRAND_FILTER_ARG) \
		$(COMPACT_CLASS_IDS_ARG) \
		$(PSEUDO_BRAND_FILTER_ARGS) \
		$(PSEUDO_BRAND_PACKAGE_ARG) \
		$(PSEUDO_PROMPT_ARGS) \
		--nms-iou $(PSEUDO_NMS_IOU) \
		--containment-threshold $(PSEUDO_CONTAINMENT) \
		--max-area-ratio $(PSEUDO_MAX_AREA_RATIO) \
		$(PSEUDO_CROSS_BRAND_DEDUP_ARG) \
		--cross-brand-iou $(PSEUDO_CROSS_BRAND_IOU) \
		--cross-brand-containment $(PSEUDO_CROSS_BRAND_CONTAINMENT) \
		--conf $(PSEUDO_CONF) \
		--imgsz $(PSEUDO_IMGSZ) \
		$(PSEUDO_LIMIT_ARG) \
		$(PSEUDO_CANDIDATES_ARG)

ls-import-json: ## 生成 Label Studio 导入 JSON（含预标注 predictions）
	$(VENV_BIN)/python scripts/label_studio/generate_import.py \
		--raw-report $(RAW_METADATA_DIR)/download_report.csv \
		--pseudo-root $(PSEUDO_ROOT) \
		--output $(LS_IMPORT_JSON) \
		--brand-library $(BRAND_LIBRARY) \
		$(BRAND_FILTER_ARG) \
		$(COMPACT_CLASS_IDS_ARG) \
		--label-config-output $(LS_LABEL_CONFIG_XML)

ls-to-yolo: ## 将 Label Studio JSON 导出转换为 YOLO 训练集
	$(VENV_BIN)/python scripts/label_studio/export_to_yolo.py \
		--input $(LS_EXPORT_PATH) \
		--output-root $(DATASET_ROOT) \
		--pseudo-root $(PSEUDO_ROOT) \
		--brand-library $(BRAND_LIBRARY) \
		$(BRAND_FILTER_ARG) \
		$(COMPACT_CLASS_IDS_ARG) \
		--report $(LS_TO_YOLO_REPORT) \
		$(LS_TO_YOLO_CLEAR_ARG) \
		$(LS_TO_YOLO_SKIP_EMPTY_ARG)

yolo-world-ab-test: brand-yaml ## 用同一批图片对比 YOLO-World 模型并生成报告
	$(VENV_BIN)/python scripts/pseudo_label/ab_test_yolo_world.py \
		--raw-dir $(RAW_DIR) \
		--output-root $(AB_OUTPUT_ROOT) \
		$(AB_RUN_NAME_ARG) \
		--model '$(AB_MODELS)' \
		--brand-library $(BRAND_LIBRARY) \
		$(BRAND_FILTER_ARG) \
		$(COMPACT_CLASS_IDS_ARG) \
		$(AB_BRAND_PACKAGE_ARG) \
		$(PSEUDO_PROMPT_ARGS) \
		--nms-iou $(PSEUDO_NMS_IOU) \
		--containment-threshold $(PSEUDO_CONTAINMENT) \
		--max-area-ratio $(PSEUDO_MAX_AREA_RATIO) \
		$(AB_CROSS_BRAND_DEDUP_ARG) \
		--cross-brand-iou $(PSEUDO_CROSS_BRAND_IOU) \
		--cross-brand-containment $(PSEUDO_CROSS_BRAND_CONTAINMENT) \
		--conf $(PSEUDO_CONF) \
		--imgsz $(PSEUDO_IMGSZ) \
		--preview-limit $(AB_PREVIEW_LIMIT) \
		$(AB_LIMIT_ARG) \
		$(AB_CANDIDATES_ARG)
