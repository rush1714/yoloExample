# 通用标签类别工作流：类别来源、图片来源、Label Studio、YOLO 转换和 EC2 均通过参数组合。
# 旧 brand/diaper/local/s3 命令保留兼容；新流程优先使用本文件里的 label-* 目标。

# ── 通用类别参数 ───────────────────────────────────────────────
# 可提交 Git 的通用类别配置文件；控制台“类别管理”会读写此文件。
LABEL_CATALOG ?= $(PROJECT_ROOT)/config/label_categories.json
# 国家/市场参数；默认 default，业务执行建议显式传入，例如 COUNTRY=GH。
COUNTRY ?= default
# 数据版本；默认当天日期，业务执行建议显式传入，例如 DATA_VERSION=v2026-09-18。
DATA_VERSION ?= v$(shell date +%Y-%m-%d)
# 类别列表名称，默认使用 config/label_categories.json 中的通用自定义类别集合。
LABEL_SET ?= general
export LABEL_SET
# 类别多选，英文逗号分隔；留空表示当前类别列表全部启用类别，all 仅作历史兼容。
LABELS ?=
# 选择部分类别时默认把 class_id 压缩成从 0 开始的连续值；全量类别默认保持配置中的稳定 class_id。
LABEL_COMPACT_CLASS_IDS ?= $(if $(filter-out all,$(strip $(LABELS))),1,0)
LABEL_COMPACT_CLASS_IDS_ARG = $(if $(filter 1 true yes,$(LABEL_COMPACT_CLASS_IDS)),--compact-class-ids,)
LABEL_PROFILE_SCRIPT := $(PROJECT_ROOT)/scripts/config/label_profile.py
LABEL_RESOLVE_PATH_SCRIPT := $(PROJECT_ROOT)/scripts/config/resolve_path.py
# 默认数据集短名称由 LABEL_SET + LABELS 计算；也可显式覆盖 LABEL_DATASET_NAME。
LABEL_DATASET_NAME ?= $(shell $(VENV_BIN)/python $(LABEL_PROFILE_SCRIPT) --catalog '$(LABEL_CATALOG)' --label-set '$(LABEL_SET)' --labels '$(LABELS)' $(LABEL_COMPACT_CLASS_IDS_ARG) --field dataset-name)
LABEL_DISPLAY_NAME ?= $(shell $(VENV_BIN)/python $(LABEL_PROFILE_SCRIPT) --catalog '$(LABEL_CATALOG)' --label-set '$(LABEL_SET)' --labels '$(LABELS)' $(LABEL_COMPACT_CLASS_IDS_ARG) --field display-name)
# 数据域仅保留为历史兼容参数；新标准目录不再按 excel/local/s3 来源拆分。
LABEL_DATA_DOMAIN ?= $(if $(filter label-excel-import label-ls-import-json-from-raw label-ls-import-json-from-pseudo label-ocr label-pseudo-label 1-label-excel-workflow-to-ls 1-label-excel-ocr-yoloworld-workflow-to-ls,$(MAKECMDGOALS)),excel,local)
# 同一国家、版本、类别组合只使用一套数据集根目录，图片来源只影响导入方式。
LABEL_DATASET_ROOT ?= $(PROJECT_ROOT)/datasets/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)
LABEL_DATASET_ROOT_ABS := $(shell $(VENV_BIN)/python $(LABEL_RESOLVE_PATH_SCRIPT) '$(LABEL_DATASET_ROOT)')
LABEL_RAW_DIR ?= $(LABEL_DATASET_ROOT_ABS)/raw/images
LABEL_RAW_METADATA_DIR ?= $(LABEL_DATASET_ROOT_ABS)/raw/metadata
LABEL_LOCAL_IMAGES_DIR ?= $(PROJECT_ROOT)/data/local_import/images
LABEL_LOCAL_IMAGES_ABS := $(shell $(VENV_BIN)/python $(LABEL_RESOLVE_PATH_SCRIPT) '$(LABEL_LOCAL_IMAGES_DIR)')
LABEL_LOCAL_STAGE_REPORT ?= $(LABEL_RAW_METADATA_DIR)/local_import_manifest.json
LABEL_LS_IMPORT_JSON ?= $(LABEL_DATASET_ROOT_ABS)/label_studio/label_studio_import.json
LABEL_LS_LABEL_CONFIG_XML ?= $(LABEL_DATASET_ROOT_ABS)/label_studio/label_config.xml
LABEL_LS_LOCAL_FILES_PATH ?= $(LABEL_RAW_DIR)
LABEL_LS_EXPORT_DIR ?= $(LABEL_DATASET_ROOT_ABS)/label_studio/exports
LABEL_LS_EXPORT_PATH ?= $(LABEL_LS_EXPORT_DIR)/label_studio_export.json
LABEL_LS_TO_YOLO_REPORT ?= $(LABEL_LS_EXPORT_DIR)/label_studio_to_yolo_report.json
LABEL_DATA_YAML ?= $(CONFIG_GENERATED_DIR)/$(COUNTRY)_$(DATA_VERSION)_$(LABEL_DATASET_NAME).yaml
LABEL_PSEUDO_ROOT ?= $(LABEL_DATASET_ROOT_ABS)/pseudo
LABEL_PSEUDO_YAML ?= $(CONFIG_GENERATED_DIR)/$(COUNTRY)_$(DATA_VERSION)_$(LABEL_DATASET_NAME)_pseudo.yaml
LABEL_OCR_OUTPUT_DIR ?= $(LABEL_DATASET_ROOT_ABS)/ocr
LABEL_OCR_CANDIDATES_FILE ?= $(LABEL_OCR_OUTPUT_DIR)/metadata/ocr_candidates.txt
LABEL_FILTER_ARG = $(if $(filter-out all,$(strip $(LABELS))),--brand-filter '$(LABELS)',)
LABEL_IMPORT_LIMIT ?=
LABEL_IMPORT_LIMIT_ARG := $(if $(LABEL_IMPORT_LIMIT),--limit $(LABEL_IMPORT_LIMIT),)
LABEL_RECURSIVE ?= 1
LABEL_RECURSIVE_ARG := $(if $(filter 0 false no,$(LABEL_RECURSIVE)),--no-recursive,--recursive)
LABEL_LS_TO_YOLO_CLEAR ?= 0
LABEL_LS_TO_YOLO_SKIP_EMPTY ?= 0
LABEL_LS_TO_YOLO_CLEAR_ARG := $(if $(filter 1 true yes,$(LABEL_LS_TO_YOLO_CLEAR)),--clear-output,)
LABEL_LS_TO_YOLO_SKIP_EMPTY_ARG := $(if $(filter 1 true yes,$(LABEL_LS_TO_YOLO_SKIP_EMPTY)),--skip-empty-annotations,)
LABEL_YOLO_S3_TO_EC2_SKIP_EMPTY_ARG := $(if $(filter 1 true yes,$(LABEL_LS_TO_YOLO_SKIP_EMPTY)),--skip-empty-labels,)
# 多项目合并可传 LS_PROJECT_IDS=21,20，也兼容控制台常用的 LS_PROJECT_ID=21,20。
LABEL_LS_PROJECT_IDS ?= $(LS_PROJECT_IDS)
LABEL_LS_PROJECT_EXPORT_DIR ?= $(LABEL_LS_EXPORT_DIR)/projects
LABEL_MERGED_LS_EXPORT_PATH ?= $(LABEL_LS_EXPORT_DIR)/merged_label_studio_export.json
LABEL_MERGE_REPORT ?= $(LABEL_LS_EXPORT_DIR)/merged_label_studio_export_report.json

# ── 通用云端清单/EC2 路径参数 ─────────────────────────────────
# S3 只作为同一数据集下的辅助清单目录，不再作为 datasets/s3 一级来源目录。
LABEL_S3_DATASET_ROOT ?= $(LABEL_DATASET_ROOT_ABS)
LABEL_S3_DATASET_ROOT_ABS := $(shell $(VENV_BIN)/python $(LABEL_RESOLVE_PATH_SCRIPT) '$(LABEL_S3_DATASET_ROOT)')
LABEL_S3_MANIFEST_JSON ?= $(LABEL_S3_DATASET_ROOT_ABS)/s3/metadata/s3_images.json
LABEL_S3_LS_IMPORT_JSON ?= $(LABEL_DATASET_ROOT_ABS)/label_studio/s3_label_studio_import.json
LABEL_S3_LS_LABEL_CONFIG_XML ?= $(LABEL_DATASET_ROOT_ABS)/label_studio/label_config.xml
LABEL_S3_LS_EXPORT_DIR ?= $(LABEL_DATASET_ROOT_ABS)/label_studio/exports
LABEL_S3_LS_EXPORT_PATH ?= $(LABEL_S3_LS_EXPORT_DIR)/label_studio_export.json
LABEL_S3_LS_TO_YOLO_REPORT ?= $(LABEL_S3_DATASET_ROOT_ABS)/s3/metadata/label_studio_to_yolo_report.json
LABEL_YOLO_S3_TO_EC2_REPORT ?= $(LABEL_S3_DATASET_ROOT_ABS)/s3/metadata/yolo_dataset_to_ec2_manifest_report.json
LABEL_S3_EC2_IMAGE_MANIFEST_JSON ?= $(LABEL_S3_DATASET_ROOT_ABS)/s3/metadata/ec2_image_manifest.json
LABEL_S3_EC2_IMAGE_MANIFEST_CSV ?= $(LABEL_S3_DATASET_ROOT_ABS)/s3/metadata/ec2_image_manifest.csv
LABEL_S3_DATA_YAML ?= $(LABEL_DATA_YAML)
LABEL_S3_PREFIX ?= $(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)
LABEL_S3_EC2_REMOTE_DATASET_ROOT ?= datasets/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)
LABEL_S3_EC2_REMOTE_DATA_YAML ?= config/generated/$(COUNTRY)_$(DATA_VERSION)_$(LABEL_DATASET_NAME).yaml
LABEL_S3_EC2_REMOTE_MANIFEST_JSON ?= datasets/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/s3/metadata/ec2_image_manifest.json
LABEL_S3_EC2_REMOTE_MANIFEST_CSV ?= datasets/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/s3/metadata/ec2_image_manifest.csv
LABEL_S3_EC2_TRAIN_NAME ?= $(COUNTRY)_$(DATA_VERSION)_$(LABEL_DATASET_NAME)
LABEL_S3_EC2_REMOTE_FINAL_MODEL ?= models/ec2/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME)/best.pt
LABEL_S3_FINAL_MODEL ?= $(PROJECT_ROOT)/models/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME)/best.pt
LABEL_S3_EC2_ARTIFACT_ROOT ?= artifacts/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME)
LABEL_S3_EC2_LATEST_RUN_FILE ?= $(LABEL_S3_EC2_ARTIFACT_ROOT)/latest-run.txt
LABEL_S3_EC2_LOCAL_ARTIFACT_ROOT ?= outputs/ec2/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME)
LABEL_S3_EC2_PREDICT_WORK_DIR ?= $(if $(EC2_PREDICT_WORK_DIR),$(EC2_PREDICT_WORK_DIR),outputs/ec2_predict/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME))
LABEL_S3_EC2_PREDICT_MODEL ?= $(if $(EC2_PREDICT_MODEL),$(EC2_PREDICT_MODEL),$(LABEL_S3_EC2_REMOTE_FINAL_MODEL))
LABEL_S3_EC2_PREDICT_URI_LIST ?= $(LABEL_S3_DATASET_ROOT_ABS)/s3/metadata/ec2_predict_$(EC2_RUN_NAME)_uploaded_s3_uris.txt
LABEL_S3_EC2_PREDICT_REPORT_JSON ?= $(LABEL_S3_DATASET_ROOT_ABS)/s3/metadata/ec2_predict_$(EC2_RUN_NAME)_download_report.json
LABEL_S3_EC2_PREDICT_REPORT_CSV ?= $(LABEL_S3_DATASET_ROOT_ABS)/s3/metadata/ec2_predict_$(EC2_RUN_NAME)_download_report.csv
LABEL_S3_EC2_LOCAL_PREDICT_RESULT_ROOT ?= $(if $(EC2_PREDICT_LOCAL_RESULT_ROOT),$(EC2_PREDICT_LOCAL_RESULT_ROOT),$(PROJECT_ROOT)/outputs/ec2_predict/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME))
LABEL_S3_EC2_LOCAL_PREDICT_SOURCE_IMAGE_ROOT ?= $(if $(EC2_PREDICT_LOCAL_SOURCE_IMAGE_ROOT),$(EC2_PREDICT_LOCAL_SOURCE_IMAGE_ROOT),$(LABEL_DATASET_ROOT_ABS)/predict/images/$(EC2_RUN_NAME))

LABEL_EC2_REMOTE_DATASET_ROOT ?= datasets/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)
LABEL_EC2_REMOTE_DATA_YAML ?= config/generated/$(COUNTRY)_$(DATA_VERSION)_$(LABEL_DATASET_NAME).yaml
LABEL_EC2_TRAIN_NAME ?= $(COUNTRY)_$(DATA_VERSION)_$(LABEL_DATASET_NAME)
LABEL_EC2_REMOTE_FINAL_MODEL ?= models/ec2/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME)/best.pt
LABEL_FINAL_MODEL ?= $(PROJECT_ROOT)/models/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME)/best.pt
LABEL_EC2_ARTIFACT_ROOT ?= artifacts/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME)
LABEL_EC2_LATEST_RUN_FILE ?= $(LABEL_EC2_ARTIFACT_ROOT)/latest-run.txt
LABEL_EC2_LOCAL_ARTIFACT_ROOT ?= outputs/ec2/$(COUNTRY)/$(DATA_VERSION)/$(LABEL_DATASET_NAME)/$(EC2_RUN_NAME)

.PHONY: label-list label-yaml label-excel-import label-ocr label-pseudo-label label-ls-import-json-from-raw label-ls-import-json-from-pseudo label-stage-local-images label-local-ls-import-json label-local-ls-apply label-s3-upload-images label-s3-ls-import-json label-s3-ls-apply label-s3-ls-export \
	label-ls-apply label-ls-export label-to-yolo label-s3-to-yolo label-local-s3-to-yolo label-yolo-s3-to-ec2-manifest label-merge-ls-projects label-merge-ls-projects-to-yolo \
	1-label-excel-workflow-to-ls 1-label-excel-ocr-yoloworld-workflow-to-ls 1-label-local-workflow-to-ls 1-label-s3-workflow-to-ls 2-label-workflow-after-ls 2-label-s3-workflow-after-ls 2-label-local-s3-workflow-after-ls \
	label-ec2-upload-data label-ec2-train label-ec2-evaluate label-ec2-download-artifacts label-ec2-download-model \
	label-s3-ec2-upload-manifest label-s3-ec2-download-images label-s3-ec2-train label-s3-ec2-evaluate label-s3-ec2-download-artifacts label-s3-ec2-download-model label-s3-ec2-predict-manifest label-s3-ec2-upload-existing-predict-results label-s3-ec2-download-predict-results 3-label-s3-workflow-ec2-train

label-list: ## 显示通用类别列表和当前 LABEL_SET 下可选类别
	@printf "类别配置=%s\n" "$(LABEL_CATALOG)"
	@printf "默认目录规则=datasets/<COUNTRY>/<DATA_VERSION>/<LABEL_DATASET_NAME>\n"
	@printf "当前 COUNTRY=%s DATA_VERSION=%s LABEL_DATASET_NAME=%s\n" "$(COUNTRY)" "$(DATA_VERSION)" "$(LABEL_DATASET_NAME)"
	@printf "可选类别列表：\n"
	@$(VENV_BIN)/python $(LABEL_PROFILE_SCRIPT) --catalog '$(LABEL_CATALOG)' --label-set '$(LABEL_SET)' --labels '$(LABELS)' --field available-sets
	@printf "\n当前类别列表 $(LABEL_SET) 可选类别：\n"
	@$(VENV_BIN)/python $(LABEL_PROFILE_SCRIPT) --catalog '$(LABEL_CATALOG)' --label-set '$(LABEL_SET)' --labels '$(LABELS)' --field available-labels

label-yaml: ## 根据 LABEL_SET/LABELS 生成通用 YOLO YAML
	$(VENV_BIN)/python scripts/config/write_label_yolo_yaml.py \
		--catalog '$(LABEL_CATALOG)' \
		--label-set '$(LABEL_SET)' \
		--labels '$(LABELS)' \
		--output '$(LABEL_DATA_YAML)' \
		--pseudo-output '$(LABEL_PSEUDO_YAML)' \
		--dataset-root '$(LABEL_DATASET_ROOT_ABS)' \
		$(LABEL_COMPACT_CLASS_IDS_ARG)

label-excel-import: ## 按 COUNTRY/DATA_VERSION/LABELS 下载 Excel 图片到通用 raw 目录
	$(VENV_BIN)/python scripts/data_import/import_images_from_excel.py \
		--excel '$(EXCEL)' \
		--column '$(EXCEL_COLUMN)' \
		--output-dir '$(LABEL_RAW_DIR)' \
		--metadata-dir '$(LABEL_RAW_METADATA_DIR)' \
		--workers $(EXCEL_WORKERS) \
		--timeout $(EXCEL_TIMEOUT)

label-ocr: ## 使用 LABELS 在品牌类别列表内做 OCR 候选筛选
	$(VENV_BIN)/python scripts/ocr/filter_brand_candidates.py \
		--raw-dir '$(LABEL_RAW_DIR)' \
		--output-dir '$(LABEL_OCR_OUTPUT_DIR)' \
		--engine $(OCR_ENGINE) \
		--brand-library '$(LABEL_CATALOG)' \
		$(LABEL_FILTER_ARG) \
		$(OCR_KEYWORD_ARGS) \
		--languages $(OCR_LANGUAGES) \
		--min-confidence $(OCR_MIN_CONFIDENCE) \
		--fuzzy-threshold $(OCR_FUZZY_THRESHOLD) \
		--workers $(OCR_WORKERS) \
		$(OCR_LIMIT_ARG) $(OCR_COPY_ARG) $(OCR_RESUME_ARG)

label-pseudo-label: label-yaml ## 使用 LABELS 在品牌类别列表内生成 YOLO-World 预标注
	$(VENV_BIN)/python scripts/pseudo_label/generate_yolo_world.py \
		--raw-dir '$(LABEL_RAW_DIR)' \
		--output-root '$(LABEL_PSEUDO_ROOT)' \
		--model $(PSEUDO_MODEL) \
		--brand-library '$(LABEL_CATALOG)' \
		$(LABEL_FILTER_ARG) \
		$(LABEL_COMPACT_CLASS_IDS_ARG) \
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
		$(if $(filter 1 true yes,$(PSEUDO_USE_OCR_CANDIDATES)),--candidates-file '$(LABEL_OCR_CANDIDATES_FILE)',)

label-ls-import-json-from-raw: label-yaml ## 根据 Excel 下载报告生成通用类别 LS 导入 JSON
	$(VENV_BIN)/python scripts/label_studio/generate_label_import.py \
		--source raw-report \
		--catalog '$(LABEL_CATALOG)' \
		--label-set '$(LABEL_SET)' \
		--labels '$(LABELS)' \
		--dataset-name '$(LABEL_DATASET_NAME)' \
		--raw-report '$(LABEL_RAW_METADATA_DIR)/download_report.csv' \
		--output '$(LABEL_LS_IMPORT_JSON)' \
		--label-config-output '$(LABEL_LS_LABEL_CONFIG_XML)' \
		$(LABEL_IMPORT_LIMIT_ARG) $(LABEL_COMPACT_CLASS_IDS_ARG)

label-ls-import-json-from-pseudo: label-yaml ## 根据 Excel 下载报告和预标注结果生成通用类别 LS 导入 JSON
	$(VENV_BIN)/python scripts/label_studio/generate_label_import.py \
		--source raw-report \
		--catalog '$(LABEL_CATALOG)' \
		--label-set '$(LABEL_SET)' \
		--labels '$(LABELS)' \
		--dataset-name '$(LABEL_DATASET_NAME)' \
		--raw-report '$(LABEL_RAW_METADATA_DIR)/download_report.csv' \
		--pseudo-root '$(LABEL_PSEUDO_ROOT)' \
		--output '$(LABEL_LS_IMPORT_JSON)' \
		--label-config-output '$(LABEL_LS_LABEL_CONFIG_XML)' \
		$(LABEL_IMPORT_LIMIT_ARG) $(LABEL_COMPACT_CLASS_IDS_ARG)

label-stage-local-images: ## 把本地图片目录沉淀到标准 raw/images 目录
	$(VENV_BIN)/python scripts/data_import/stage_local_images.py \
		--input-dir '$(LABEL_LOCAL_IMAGES_ABS)' \
		--output-dir '$(LABEL_RAW_DIR)' \
		--report '$(LABEL_LOCAL_STAGE_REPORT)' \
		$(LABEL_RECURSIVE_ARG) $(LABEL_IMPORT_LIMIT_ARG)

label-local-ls-import-json: label-yaml label-stage-local-images ## 扫描本地图片目录并生成通用类别 LS 导入 JSON
	$(VENV_BIN)/python scripts/label_studio/generate_label_import.py \
		--source local-dir \
		--catalog '$(LABEL_CATALOG)' \
		--label-set '$(LABEL_SET)' \
		--labels '$(LABELS)' \
		--dataset-name '$(LABEL_DATASET_NAME)' \
		--input-dir '$(LABEL_RAW_DIR)' \
		--output '$(LABEL_LS_IMPORT_JSON)' \
		--label-config-output '$(LABEL_LS_LABEL_CONFIG_XML)' \
		$(LABEL_RECURSIVE_ARG) $(LABEL_IMPORT_LIMIT_ARG) $(LABEL_COMPACT_CLASS_IDS_ARG)

label-local-ls-apply: ls-db-check prepare-dirs ## 将本地目录通用类别导入 JSON 创建为 Label Studio 项目
	$(MAKE) --no-print-directory label-ls-apply \
		LABEL_DATA_DOMAIN='local' \
		LABEL_LS_LOCAL_FILES_PATH='$(LABEL_RAW_DIR)'

label-ls-apply: ls-db-check prepare-dirs ## 将通用类别导入 JSON 创建为 Label Studio 项目
	cd $(LS_WORK_DIR) && \
		LS_IMPORT_JSON='$(LABEL_LS_IMPORT_JSON)' \
		LS_LOCAL_FILES_PATH='$(LABEL_LS_LOCAL_FILES_PATH)' \
		LS_PROJECT_TITLE='$(LABEL_DISPLAY_NAME) $(COUNTRY) $(DATA_VERSION)' \
		LS_PROJECT_DESCRIPTION='通用标签类别标注项目：LABEL_SET=$(LABEL_SET), LABELS=$(LABELS)。' \
		LS_LOCAL_FILES_STORAGE_TITLE='$(LABEL_DATASET_NAME) images' \
		LS_LOCAL_FILES_STORAGE_DESCRIPTION='通用标签类别流程导入的本地图片。' \
		LS_LABEL_CONFIG_XML='$(LABEL_LS_LABEL_CONFIG_XML)' \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR) < $(PROJECT_ROOT)/scripts/label_studio/apply_import.py

1-label-excel-workflow-to-ls: label-excel-import label-ls-import-json-from-raw label-ls-apply ## Excel 图片下载并按通用类别导入 Label Studio

1-label-excel-ocr-yoloworld-workflow-to-ls: label-excel-import label-ocr label-pseudo-label label-ls-import-json-from-pseudo label-ls-apply ## Excel 图片下载、OCR、YOLO-World 预标注并按通用类别导入 LS

1-label-local-workflow-to-ls: label-local-ls-import-json label-local-ls-apply ## 本地图片目录按通用类别导入 Label Studio

label-ls-export: ls-db-check prepare-dirs ## 从 Label Studio 导出通用类别 JSON；需传 LS_PROJECT_ID=<项目ID>
	@[ -n "$(LS_PROJECT_ID)" ] || (echo "错误：请传入 LS_PROJECT_ID，例如：make label-ls-export LS_PROJECT_ID=2" && exit 1)
	mkdir -p '$(LABEL_LS_EXPORT_DIR)'
	cd $(LS_WORK_DIR) && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio export \
		--data-dir $(LS_DATA_DIR) \
		--export-path '$(LABEL_LS_EXPORT_PATH)' \
		$(LS_PROJECT_ID) $(LS_EXPORT_FORMAT)

label-to-yolo: ## 将通用类别本地 LS 导出转换为 YOLO images/labels
	$(VENV_BIN)/python scripts/label_studio/export_labels_to_yolo.py \
		--mode local \
		--input '$(LABEL_LS_EXPORT_PATH)' \
		--output-root '$(LABEL_DATASET_ROOT_ABS)' \
		--catalog '$(LABEL_CATALOG)' \
		--label-set '$(LABEL_SET)' \
		--labels '$(LABELS)' \
		--report '$(LABEL_LS_TO_YOLO_REPORT)' \
		--data-yaml '$(LABEL_DATA_YAML)' \
		--dataset-root-for-yaml '$(LABEL_DATASET_ROOT_ABS)' \
		$(LABEL_LS_TO_YOLO_CLEAR_ARG) $(LABEL_LS_TO_YOLO_SKIP_EMPTY_ARG) $(LABEL_COMPACT_CLASS_IDS_ARG)

2-label-workflow-after-ls: label-ls-export label-to-yolo ## 导出通用类别 LS 标注并转换为 YOLO 训练集

label-merge-ls-projects: ls-db-check prepare-dirs ## 导出并合并多个 LS 项目；需传 LABEL_LS_PROJECT_IDS=21,20
	@[ -n "$(LABEL_LS_PROJECT_IDS)" ] || (echo "错误：请传入 LABEL_LS_PROJECT_IDS=21,20 或 LS_PROJECT_ID=21,20" && exit 1)
	@label_filter="$$( $(VENV_BIN)/python $(LABEL_PROFILE_SCRIPT) --catalog '$(LABEL_CATALOG)' --label-set '$(LABEL_SET)' --labels '$(LABELS)' $(LABEL_COMPACT_CLASS_IDS_ARG) --field label-filter )"; \
	$(VENV_BIN)/python scripts/label_studio/export_and_merge_projects.py \
		--project-ids '$(LABEL_LS_PROJECT_IDS)' \
		--output '$(LABEL_MERGED_LS_EXPORT_PATH)' \
		--report '$(LABEL_MERGE_REPORT)' \
		--project-export-dir '$(LABEL_LS_PROJECT_EXPORT_DIR)' \
		--label-name "$$label_filter" \
		--annotation-index '$(LS_CLONE_ANNOTATION_INDEX)' \
		--export-format '$(LS_EXPORT_FORMAT)' \
		--venv-bin '$(VENV_BIN)' \
		--ls-work-dir '$(LS_WORK_DIR)' \
		--ls-data-dir '$(LS_DATA_DIR)'

label-merge-ls-projects-to-yolo: label-merge-ls-projects ## 合并多个 LS 项目后转换为通用 YOLO 训练集
	$(MAKE) --no-print-directory label-to-yolo \
		LABEL_LS_EXPORT_PATH='$(LABEL_MERGED_LS_EXPORT_PATH)' \
		LABEL_LS_TO_YOLO_CLEAR='$(LABEL_LS_TO_YOLO_CLEAR)' \
		LABEL_LS_TO_YOLO_SKIP_EMPTY='$(LABEL_LS_TO_YOLO_SKIP_EMPTY)'

label-s3-upload-images: ## 上传 LABEL_LOCAL_IMAGES_DIR 指向的图片目录到 S3，并在标准数据集内生成清单；S3_DRY_RUN=1 只生成计划
	$(VENV_BIN)/python scripts/s3/upload_images_to_s3.py \
		--config '$(BRAND_S3_CONFIG)' \
		--dataset-name '$(LABEL_DATASET_NAME)' \
		--label-name '$(LABEL_DISPLAY_NAME)' \
		--input-dir '$(LABEL_LOCAL_IMAGES_ABS)' \
		--dataset-root '$(LABEL_S3_DATASET_ROOT_ABS)' \
		--bucket '$(S3_BUCKET)' \
		--prefix '$(LABEL_S3_PREFIX)' \
		--region '$(S3_REGION)' \
		--profile '$(S3_PROFILE)' \
		--endpoint-url '$(S3_ENDPOINT_URL)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' \
		--proxy-base-url '$(S3_PROXY_BASE_URL)' \
		--workers $(S3_UPLOAD_WORKERS) \
		$(S3_RECURSIVE_ARG) $(S3_LIMIT_ARG) $(S3_DRY_RUN_ARG)

label-s3-ls-import-json: ## 根据 S3 上传清单生成通用类别 LS 导入 JSON
	$(VENV_BIN)/python scripts/label_studio/generate_label_import.py \
		--source s3-manifest \
		--catalog '$(LABEL_CATALOG)' \
		--label-set '$(LABEL_SET)' \
		--labels '$(LABELS)' \
		--dataset-name '$(LABEL_DATASET_NAME)' \
		--s3-manifest '$(LABEL_S3_MANIFEST_JSON)' \
		--image-url-mode '$(S3_IMAGE_URL_MODE)' \
		--proxy-base-url '$(S3_PROXY_BASE_URL)' \
		--output '$(LABEL_S3_LS_IMPORT_JSON)' \
		--label-config-output '$(LABEL_S3_LS_LABEL_CONFIG_XML)' \
		$(LABEL_IMPORT_LIMIT_ARG) $(LABEL_COMPACT_CLASS_IDS_ARG)

label-s3-ls-apply: ls-db-check prepare-dirs ## 将通用类别 S3 图片任务导入 Label Studio
	cd $(LS_WORK_DIR) && \
		LS_IMPORT_JSON='$(LABEL_S3_LS_IMPORT_JSON)' \
		LS_LOCAL_FILES_PATH='$(PROJECT_ROOT)' \
		LS_PROJECT_TITLE='S3 $(LABEL_DISPLAY_NAME) $(COUNTRY) $(DATA_VERSION)' \
		LS_PROJECT_DESCRIPTION='通用标签类别 S3 图片标注项目：LABEL_SET=$(LABEL_SET), LABELS=$(LABELS)。' \
		LS_LOCAL_FILES_STORAGE_TITLE='S3 $(LABEL_DATASET_NAME)' \
		LS_LOCAL_FILES_STORAGE_DESCRIPTION='S3 图片任务不依赖本地图片存储，本 storage 只用于满足 Label Studio 权限。' \
		LS_LABEL_CONFIG_XML='$(LABEL_S3_LS_LABEL_CONFIG_XML)' \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR) < $(PROJECT_ROOT)/scripts/label_studio/apply_import.py

1-label-s3-workflow-to-ls: label-s3-upload-images label-s3-ls-import-json label-s3-ls-apply ## 本地图片上传 S3 并按通用类别导入 Label Studio

label-s3-ls-export: ls-db-check prepare-dirs ## 从 Label Studio 导出通用 S3 图片标注 JSON；需传 LS_PROJECT_ID=<项目ID>
	@[ -n "$(LS_PROJECT_ID)" ] || (echo "错误：请传入 LS_PROJECT_ID，例如：make label-s3-ls-export LS_PROJECT_ID=2" && exit 1)
	mkdir -p '$(LABEL_S3_LS_EXPORT_DIR)'
	cd $(LS_WORK_DIR) && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio export \
		--data-dir $(LS_DATA_DIR) \
		--export-path '$(LABEL_S3_LS_EXPORT_PATH)' \
		$(LS_PROJECT_ID) $(LS_EXPORT_FORMAT)

label-s3-to-yolo: ## 将 S3 图片 LS 导出转换为 YOLO labels 和 EC2 manifest
	$(VENV_BIN)/python scripts/label_studio/export_labels_to_yolo.py \
		--mode s3 \
		--input '$(LABEL_S3_LS_EXPORT_PATH)' \
		--output-root '$(LABEL_S3_DATASET_ROOT_ABS)' \
		--catalog '$(LABEL_CATALOG)' \
		--label-set '$(LABEL_SET)' \
		--labels '$(LABELS)' \
		--report '$(LABEL_S3_LS_TO_YOLO_REPORT)' \
		--data-yaml '$(LABEL_S3_DATA_YAML)' \
		--dataset-root-for-yaml '$(LABEL_S3_DATASET_ROOT_ABS)' \
		--ec2-manifest-json '$(LABEL_S3_EC2_IMAGE_MANIFEST_JSON)' \
		--ec2-manifest-csv '$(LABEL_S3_EC2_IMAGE_MANIFEST_CSV)' \
		$(LABEL_LS_TO_YOLO_CLEAR_ARG) $(LABEL_LS_TO_YOLO_SKIP_EMPTY_ARG) $(LABEL_COMPACT_CLASS_IDS_ARG)

2-label-s3-workflow-after-ls: label-s3-ls-export label-s3-to-yolo ## 导出通用 S3 标注并生成 YOLO labels/EC2 manifest

label-local-s3-to-yolo: ## 将本地地址 LS 导出结合 S3 上传清单生成 YOLO labels/EC2 manifest
	$(VENV_BIN)/python scripts/label_studio/export_labels_to_yolo.py \
		--mode local-s3 \
		--input '$(LABEL_LS_EXPORT_PATH)' \
		--s3-manifest '$(LABEL_S3_MANIFEST_JSON)' \
		--local-images-dir '$(LABEL_LOCAL_IMAGES_ABS)' \
		--output-root '$(LABEL_S3_DATASET_ROOT_ABS)' \
		--catalog '$(LABEL_CATALOG)' \
		--label-set '$(LABEL_SET)' \
		--labels '$(LABELS)' \
		--report '$(LABEL_S3_LS_TO_YOLO_REPORT)' \
		--data-yaml '$(LABEL_S3_DATA_YAML)' \
		--dataset-root-for-yaml '$(LABEL_S3_DATASET_ROOT_ABS)' \
		--ec2-manifest-json '$(LABEL_S3_EC2_IMAGE_MANIFEST_JSON)' \
		--ec2-manifest-csv '$(LABEL_S3_EC2_IMAGE_MANIFEST_CSV)' \
		$(LABEL_LS_TO_YOLO_CLEAR_ARG) $(LABEL_LS_TO_YOLO_SKIP_EMPTY_ARG) $(LABEL_COMPACT_CLASS_IDS_ARG)

2-label-local-s3-workflow-after-ls: label-ls-export label-local-s3-to-yolo ## 导出本地地址 LS 标注，并结合 S3 清单生成 EC2 manifest

label-yolo-s3-to-ec2-manifest: label-yaml ## 已生成 YOLO images/labels 后，结合 S3 上传清单生成 EC2 manifest
	$(VENV_BIN)/python scripts/s3/yolo_dataset_to_ec2_manifest.py \
		--dataset-root '$(LABEL_DATASET_ROOT_ABS)' \
		--s3-manifest '$(LABEL_S3_MANIFEST_JSON)' \
		--data-yaml '$(LABEL_DATA_YAML)' \
		--ec2-manifest-json '$(LABEL_S3_EC2_IMAGE_MANIFEST_JSON)' \
		--ec2-manifest-csv '$(LABEL_S3_EC2_IMAGE_MANIFEST_CSV)' \
		--report '$(LABEL_YOLO_S3_TO_EC2_REPORT)' \
		$(LABEL_YOLO_S3_TO_EC2_SKIP_EMPTY_ARG)

label-ec2-upload-data: label-yaml ## 上传通用本地 YOLO 数据集到 EC2，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py upload-data \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country '$(COUNTRY)' --version '$(DATA_VERSION)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_DATA_YAML)' \
		--remote-dataset-root '$(LABEL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LABEL_EC2_REMOTE_DATA_YAML)' --train-name '$(LABEL_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LABEL_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LABEL_FINAL_MODEL)' \
		$(EC2_EXECUTE_ARG)

label-ec2-train: ## 在 EC2 训练通用本地数据集，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py train \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--country '$(COUNTRY)' --version '$(DATA_VERSION)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_DATA_YAML)' \
		--remote-dataset-root '$(LABEL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LABEL_EC2_REMOTE_DATA_YAML)' --train-name '$(LABEL_EC2_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(LABEL_EC2_REMOTE_FINAL_MODEL)' \
		--local-model '$(LABEL_FINAL_MODEL)' --epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) \
		--batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) --run-name '$(EC2_RUN_NAME)' \
		--artifact-root '$(LABEL_EC2_ARTIFACT_ROOT)' --latest-run-file '$(LABEL_EC2_LATEST_RUN_FILE)' \
		--skip-generate-yaml $(EC2_RESUME_ARG) $(EC2_EXECUTE_ARG)

label-ec2-evaluate: ## 归档通用本地数据集 EC2 训练产物，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py evaluate \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--country '$(COUNTRY)' --version '$(DATA_VERSION)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_DATA_YAML)' \
		--remote-dataset-root '$(LABEL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LABEL_EC2_REMOTE_DATA_YAML)' --train-name '$(LABEL_EC2_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(LABEL_EC2_REMOTE_FINAL_MODEL)' \
		--local-model '$(LABEL_FINAL_MODEL)' --epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) \
		--batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) --run-name '$(EC2_RUN_NAME)' \
		--artifact-root '$(LABEL_EC2_ARTIFACT_ROOT)' --latest-run-file '$(LABEL_EC2_LATEST_RUN_FILE)' \
		--notes '$(EC2_EVAL_NOTES)' $(EC2_EXECUTE_ARG)

label-ec2-download-artifacts: ## 下载通用本地数据集 EC2 训练归档，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py download-artifacts \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country '$(COUNTRY)' --version '$(DATA_VERSION)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_DATA_YAML)' \
		--remote-dataset-root '$(LABEL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LABEL_EC2_REMOTE_DATA_YAML)' --train-name '$(LABEL_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LABEL_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LABEL_FINAL_MODEL)' \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(LABEL_EC2_ARTIFACT_ROOT)' \
		--local-artifact-root '$(LABEL_EC2_LOCAL_ARTIFACT_ROOT)' $(EC2_EXECUTE_ARG)

label-ec2-download-model: ## 下载通用本地数据集 EC2 best.pt，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py download-model \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country '$(COUNTRY)' --version '$(DATA_VERSION)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_DATA_YAML)' \
		--remote-dataset-root '$(LABEL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LABEL_EC2_REMOTE_DATA_YAML)' --train-name '$(LABEL_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LABEL_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LABEL_FINAL_MODEL)' \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(LABEL_EC2_ARTIFACT_ROOT)' $(EC2_EXECUTE_ARG)

label-s3-ec2-upload-manifest: ## 上传通用 S3 labels、manifest 和 YAML 到 EC2，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py upload-manifest \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--dataset-name '$(LABEL_DATASET_NAME)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_S3_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_S3_DATA_YAML)' \
		--ec2-manifest-json '$(LABEL_S3_EC2_IMAGE_MANIFEST_JSON)' --ec2-manifest-csv '$(LABEL_S3_EC2_IMAGE_MANIFEST_CSV)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' --download-mode '$(S3_EC2_DOWNLOAD_MODE)' \
		--remote-dataset-root '$(LABEL_S3_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LABEL_S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(LABEL_S3_EC2_REMOTE_MANIFEST_JSON)' \
		--remote-manifest-csv '$(LABEL_S3_EC2_REMOTE_MANIFEST_CSV)' \
		--train-name '$(LABEL_S3_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LABEL_S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LABEL_S3_FINAL_MODEL)' \
		$(EC2_EXECUTE_ARG)

label-s3-ec2-download-images: ## 在 EC2 按通用 S3 manifest 下载训练图片，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py download-images \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--dataset-name '$(LABEL_DATASET_NAME)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_S3_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_S3_DATA_YAML)' \
		--ec2-manifest-json '$(LABEL_S3_EC2_IMAGE_MANIFEST_JSON)' --ec2-manifest-csv '$(LABEL_S3_EC2_IMAGE_MANIFEST_CSV)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' --download-mode '$(S3_EC2_DOWNLOAD_MODE)' \
		--remote-dataset-root '$(LABEL_S3_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LABEL_S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(LABEL_S3_EC2_REMOTE_MANIFEST_JSON)' \
		--remote-manifest-csv '$(LABEL_S3_EC2_REMOTE_MANIFEST_CSV)' $(EC2_EXECUTE_ARG)

label-s3-ec2-train: ## 在 EC2 训练通用 S3 数据集，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py train \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--dataset-name '$(LABEL_DATASET_NAME)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_S3_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_S3_DATA_YAML)' \
		--ec2-manifest-json '$(LABEL_S3_EC2_IMAGE_MANIFEST_JSON)' --ec2-manifest-csv '$(LABEL_S3_EC2_IMAGE_MANIFEST_CSV)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' --download-mode '$(S3_EC2_DOWNLOAD_MODE)' \
		--remote-dataset-root '$(LABEL_S3_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LABEL_S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(LABEL_S3_EC2_REMOTE_MANIFEST_JSON)' \
		--remote-manifest-csv '$(LABEL_S3_EC2_REMOTE_MANIFEST_CSV)' \
		--train-name '$(LABEL_S3_EC2_TRAIN_NAME)' --base-model '$(EC2_BASE_MODEL)' \
		--remote-final-model '$(LABEL_S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LABEL_S3_FINAL_MODEL)' \
		--epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) --batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(LABEL_S3_EC2_ARTIFACT_ROOT)' --latest-run-file '$(LABEL_S3_EC2_LATEST_RUN_FILE)' \
		--skip-generate-yaml $(EC2_RESUME_ARG) $(EC2_EXECUTE_ARG)

3-label-s3-workflow-ec2-train: label-s3-ec2-upload-manifest label-s3-ec2-download-images label-s3-ec2-train ## 上传通用 S3 训练清单到 EC2、下载图片并训练

label-s3-ec2-evaluate: ## 归档通用 S3 数据集 EC2 训练产物，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py evaluate \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--dataset-name '$(LABEL_DATASET_NAME)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_S3_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_S3_DATA_YAML)' \
		--ec2-manifest-json '$(LABEL_S3_EC2_IMAGE_MANIFEST_JSON)' \
		--remote-dataset-root '$(LABEL_S3_EC2_REMOTE_DATASET_ROOT)' --remote-data-yaml '$(LABEL_S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(LABEL_S3_EC2_REMOTE_MANIFEST_JSON)' --train-name '$(LABEL_S3_EC2_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(LABEL_S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LABEL_S3_FINAL_MODEL)' \
		--epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) --batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(LABEL_S3_EC2_ARTIFACT_ROOT)' --latest-run-file '$(LABEL_S3_EC2_LATEST_RUN_FILE)' \
		--notes '$(EC2_EVAL_NOTES)' $(EC2_EXECUTE_ARG)

label-s3-ec2-download-artifacts: ## 下载通用 S3 数据集 EC2 训练归档，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py download-artifacts \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--dataset-name '$(LABEL_DATASET_NAME)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_S3_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_S3_DATA_YAML)' \
		--ec2-manifest-json '$(LABEL_S3_EC2_IMAGE_MANIFEST_JSON)' \
		--remote-dataset-root '$(LABEL_S3_EC2_REMOTE_DATASET_ROOT)' --remote-data-yaml '$(LABEL_S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(LABEL_S3_EC2_REMOTE_MANIFEST_JSON)' --train-name '$(LABEL_S3_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LABEL_S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LABEL_S3_FINAL_MODEL)' \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(LABEL_S3_EC2_ARTIFACT_ROOT)' \
		--local-artifact-root '$(LABEL_S3_EC2_LOCAL_ARTIFACT_ROOT)' $(EC2_EXECUTE_ARG)

label-s3-ec2-download-model: ## 下载通用 S3 数据集 EC2 best.pt，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py download-model \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--dataset-name '$(LABEL_DATASET_NAME)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--dataset-root '$(LABEL_S3_DATASET_ROOT_ABS)' --data-yaml '$(LABEL_S3_DATA_YAML)' \
		--ec2-manifest-json '$(LABEL_S3_EC2_IMAGE_MANIFEST_JSON)' \
		--remote-dataset-root '$(LABEL_S3_EC2_REMOTE_DATASET_ROOT)' --remote-data-yaml '$(LABEL_S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(LABEL_S3_EC2_REMOTE_MANIFEST_JSON)' --train-name '$(LABEL_S3_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LABEL_S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LABEL_S3_FINAL_MODEL)' \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(LABEL_S3_EC2_ARTIFACT_ROOT)' $(EC2_EXECUTE_ARG)

label-s3-ec2-predict-manifest: ## 在 EC2 读取 S3/Excel/JSON/TXT 图片清单，批量推理并上传结果到 S3，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py predict-s3-manifest \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--dataset-name '$(LABEL_DATASET_NAME)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--remote-final-model '$(LABEL_S3_EC2_REMOTE_FINAL_MODEL)' --run-name '$(EC2_RUN_NAME)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' --download-mode '$(S3_EC2_DOWNLOAD_MODE)' \
		--predict-manifest-source '$(EC2_PREDICT_MANIFEST_SOURCE)' \
		--predict-local-manifest '$(EC2_PREDICT_LOCAL_MANIFEST)' \
		--predict-remote-manifest '$(EC2_PREDICT_REMOTE_MANIFEST)' \
		--predict-output-s3-uri '$(EC2_PREDICT_OUTPUT_S3_URI)' \
		--predict-model '$(LABEL_S3_EC2_PREDICT_MODEL)' \
		--predict-work-dir '$(LABEL_S3_EC2_PREDICT_WORK_DIR)' \
		--predict-input-column '$(EC2_PREDICT_INPUT_COLUMN)' \
		--predict-conf $(EC2_PREDICT_CONF) --predict-imgsz $(EC2_PREDICT_IMGSZ) \
		--predict-limit $(EC2_PREDICT_LIMIT) --device $(EC2_TRAIN_DEVICE) $(EC2_EXECUTE_ARG)

label-s3-ec2-upload-existing-predict-results: ## 补传 EC2 work-dir 已有批量推理结果到 S3，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py upload-existing-predict-results \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--dataset-name '$(LABEL_DATASET_NAME)' --label-name '$(LABEL_DISPLAY_NAME)' \
		--remote-final-model '$(LABEL_S3_EC2_REMOTE_FINAL_MODEL)' --run-name '$(EC2_RUN_NAME)' \
		--predict-output-s3-uri '$(EC2_PREDICT_OUTPUT_S3_URI)' \
		--predict-work-dir '$(LABEL_S3_EC2_PREDICT_WORK_DIR)' $(EC2_EXECUTE_ARG)

label-s3-ec2-download-predict-results: ## 下载 EC2 批量推理 S3 结果记录、结果文件和原始图片到本地标准目录
	$(VENV_BIN)/python scripts/s3/download_predict_results.py \
		--output-s3-uri '$(EC2_PREDICT_OUTPUT_S3_URI)' \
		--uri-list-output '$(LABEL_S3_EC2_PREDICT_URI_LIST)' \
		--result-root '$(LABEL_S3_EC2_LOCAL_PREDICT_RESULT_ROOT)' \
		--source-image-root '$(LABEL_S3_EC2_LOCAL_PREDICT_SOURCE_IMAGE_ROOT)' \
		--report-json '$(LABEL_S3_EC2_PREDICT_REPORT_JSON)' \
		--report-csv '$(LABEL_S3_EC2_PREDICT_REPORT_CSV)' \
		--profile '$(S3_PROFILE)' --region '$(S3_REGION)' --endpoint-url '$(S3_ENDPOINT_URL)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' \
		--source-download-timeout $(EC2_PREDICT_SOURCE_DOWNLOAD_TIMEOUT) \
		--workers $(EC2_PREDICT_DOWNLOAD_WORKERS) \
		$(EC2_PREDICT_DOWNLOAD_SOURCE_IMAGES_ARG)
