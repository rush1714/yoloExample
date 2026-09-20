# 本地目录图片导入、Label Studio 标注、YOLO 转换，以及本地目录数据集衔接 EC2。

# ── 本地目录图片导入 Label Studio 参数 ─────────────────────────
# 本地目录数据集名称；用于 datasets/local/<name> 隔离导入、导出和训练数据。
LOCAL_DATASET_NAME ?= local_dataset
# 已存在的本地图片目录；可传绝对路径，例如 /Users/guobiao/Downloads/images。
LOCAL_IMAGES_DIR ?= $(PROJECT_ROOT)/data/local_import/images
# 单类别标签名；Label Studio 和 YOLO 转换均使用该名称。
LOCAL_LABEL_NAME ?= diaper
LOCAL_IMAGES_ABS := $(shell $(VENV_BIN)/python $(LABEL_RESOLVE_PATH_SCRIPT) '$(LOCAL_IMAGES_DIR)')
# 本地目录导入/导出数据集根目录；如需自定义输出位置，请改这个变量，不要把路径写到 LOCAL_DATASET_NAME。
LOCAL_DATASET_ROOT ?= $(PROJECT_ROOT)/datasets/local/$(LOCAL_DATASET_NAME)
LOCAL_DATASET_ROOT_ABS := $(shell $(VENV_BIN)/python $(LABEL_RESOLVE_PATH_SCRIPT) '$(LOCAL_DATASET_ROOT)')
LOCAL_LS_IMPORT_JSON ?= $(LOCAL_DATASET_ROOT_ABS)/label_studio/local_dir_label_studio_import.json
LOCAL_LS_LABEL_CONFIG_XML ?= $(LOCAL_DATASET_ROOT_ABS)/label_studio/label_config.xml
LOCAL_LS_EXPORT_DIR ?= $(LOCAL_DATASET_ROOT_ABS)/label_studio/exports
LOCAL_LS_EXPORT_PATH ?= $(LOCAL_LS_EXPORT_DIR)/label_studio_export.json
LOCAL_LS_TO_YOLO_REPORT ?= $(LOCAL_LS_EXPORT_DIR)/label_studio_to_yolo_report.json
LOCAL_DATA_YAML ?= $(CONFIG_GENERATED_DIR)/local_$(LOCAL_DATASET_NAME).yaml
LOCAL_FINAL_MODEL ?= $(PROJECT_ROOT)/models/local/$(LOCAL_DATASET_NAME)/$(EC2_RUN_NAME)/best.pt
LOCAL_EC2_REMOTE_DATASET_ROOT ?= datasets/local/$(LOCAL_DATASET_NAME)
LOCAL_EC2_REMOTE_DATA_YAML ?= config/generated/local_$(LOCAL_DATASET_NAME).yaml
LOCAL_EC2_TRAIN_NAME ?= local_$(LOCAL_DATASET_NAME)
LOCAL_EC2_REMOTE_FINAL_MODEL ?= models/ec2/local/$(LOCAL_DATASET_NAME)/$(EC2_RUN_NAME)/best.pt
LOCAL_EC2_ARTIFACT_ROOT ?= artifacts/local/$(LOCAL_DATASET_NAME)/$(EC2_RUN_NAME)
LOCAL_EC2_LATEST_RUN_FILE ?= $(LOCAL_EC2_ARTIFACT_ROOT)/latest-run.txt
LOCAL_EC2_LOCAL_ARTIFACT_ROOT ?= outputs/ec2/local/$(LOCAL_DATASET_NAME)/$(EC2_RUN_NAME)
# 是否递归扫描本地图片目录。
LOCAL_RECURSIVE ?= 1
# 最多导入多少张图片；空表示全量。
LOCAL_LIMIT ?=
LOCAL_LIMIT_ARG := $(if $(LOCAL_LIMIT),--limit $(LOCAL_LIMIT),)
LOCAL_RECURSIVE_ARG := $(if $(filter 0 false no,$(LOCAL_RECURSIVE)),--no-recursive,--recursive)
LOCAL_LS_TO_YOLO_CLEAR ?= 0
LOCAL_LS_TO_YOLO_SKIP_EMPTY ?= 0
LOCAL_LS_TO_YOLO_CLEAR_ARG := $(if $(filter 1 true yes,$(LOCAL_LS_TO_YOLO_CLEAR)),--clear-output,)
LOCAL_LS_TO_YOLO_SKIP_EMPTY_ARG := $(if $(filter 1 true yes,$(LOCAL_LS_TO_YOLO_SKIP_EMPTY)),--skip-empty-annotations,)

.PHONY: local-dir-check local-dir-yaml local-dir-ls-import-json local-dir-ls-apply 1-local-dir-workflow-to-ls \
	local-dir-ls-export local-dir-ls-to-yolo 2-local-dir-workflow-after-ls \
	local-dir-ec2-upload-data local-dir-ec2-train local-dir-ec2-evaluate local-dir-ec2-download-artifacts local-dir-ec2-download-model

local-dir-check: ## 检查本地目录导入参数，避免把路径误填到 LOCAL_DATASET_NAME
	@case '$(LOCAL_DATASET_NAME)' in \
		*/*|/*) echo "错误：LOCAL_DATASET_NAME 只能是短名称，不能填写路径；如需指定导出目录，请使用 LOCAL_DATASET_ROOT=/目标目录"; exit 1;; \
	esac

local-dir-yaml: local-dir-check ## 生成本地目录单类别 YOLO YAML
	$(VENV_BIN)/python scripts/config/write_single_class_yolo_yaml.py \
		--output '$(LOCAL_DATA_YAML)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' \
		--class-name '$(LOCAL_LABEL_NAME)'

local-dir-ls-import-json: local-dir-check ## 扫描本地图片目录并生成单类别 Label Studio 导入 JSON
	$(VENV_BIN)/python scripts/label_studio/generate_local_dir_import.py \
		--input-dir '$(LOCAL_IMAGES_ABS)' \
		--output '$(LOCAL_LS_IMPORT_JSON)' \
		--label-name '$(LOCAL_LABEL_NAME)' \
		--label-config-output '$(LOCAL_LS_LABEL_CONFIG_XML)' \
		--dataset-name '$(LOCAL_DATASET_NAME)' \
		$(LOCAL_RECURSIVE_ARG) $(LOCAL_LIMIT_ARG)

local-dir-ls-apply: local-dir-check ls-db-check prepare-dirs ## 将本地目录图片任务导入 Label Studio（每执行一次创建新项目）
	cd $(LS_WORK_DIR) && \
		LS_IMPORT_JSON='$(LOCAL_LS_IMPORT_JSON)' \
		LS_LOCAL_FILES_PATH='$(LOCAL_IMAGES_ABS)' \
		LS_PROJECT_TITLE='Local Dir $(LOCAL_DATASET_NAME)' \
		LS_PROJECT_DESCRIPTION='本地目录图片单类别标注项目。' \
		LS_LOCAL_FILES_STORAGE_TITLE='Local Dir $(LOCAL_DATASET_NAME) images' \
		LS_LOCAL_FILES_STORAGE_DESCRIPTION='Local image directory imported from LOCAL_IMAGES_DIR.' \
		LS_LABEL_CONFIG_XML='$(LOCAL_LS_LABEL_CONFIG_XML)' \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR) < $(PROJECT_ROOT)/scripts/label_studio/apply_import.py

1-local-dir-workflow-to-ls: local-dir-ls-import-json local-dir-ls-apply ## 扫描本地目录并导入 Label Studio

local-dir-ls-export: local-dir-check ls-db-check prepare-dirs ## 从 Label Studio 导出本地目录标注 JSON；需传 LS_PROJECT_ID=<项目ID>
	@[ -n "$(LS_PROJECT_ID)" ] || (echo "错误：请传入 LS_PROJECT_ID，例如：make local-dir-ls-export LS_PROJECT_ID=2" && exit 1)
	mkdir -p '$(LOCAL_LS_EXPORT_DIR)'
	cd $(LS_WORK_DIR) && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio export \
		--data-dir $(LS_DATA_DIR) \
		--export-path '$(LOCAL_LS_EXPORT_PATH)' \
		$(LS_PROJECT_ID) $(LS_EXPORT_FORMAT)

local-dir-ls-to-yolo: local-dir-yaml ## 将本地目录 Label Studio 导出转换为 YOLO 训练集
	$(VENV_BIN)/python scripts/label_studio/export_single_class_to_yolo.py \
		--input '$(LOCAL_LS_EXPORT_PATH)' \
		--output-root '$(LOCAL_DATASET_ROOT_ABS)' \
		--label-name '$(LOCAL_LABEL_NAME)' \
		$(LOCAL_LS_TO_YOLO_CLEAR_ARG) $(LOCAL_LS_TO_YOLO_SKIP_EMPTY_ARG) \
		--report '$(LOCAL_LS_TO_YOLO_REPORT)'

2-local-dir-workflow-after-ls: local-dir-ls-export local-dir-ls-to-yolo ## 导出本地目录标注并转换 YOLO 训练集

local-dir-ec2-upload-data: local-dir-yaml ## 上传本地目录 YOLO 数据集到 EC2（默认 dry-run；EC2_EXECUTE=1 才执行）
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py upload-data \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LOCAL_FINAL_MODEL)' \
		$(EC2_EXECUTE_ARG)

local-dir-ec2-train: local-dir-check ## 在 EC2 训练本地目录数据集（默认 dry-run；训练规模由 EC2_* 参数控制）
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py train \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' \
		--local-model '$(LOCAL_FINAL_MODEL)' --epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) \
		--batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) --run-name '$(EC2_RUN_NAME)' \
		--artifact-root '$(LOCAL_EC2_ARTIFACT_ROOT)' --latest-run-file '$(LOCAL_EC2_LATEST_RUN_FILE)' \
		$(EC2_RESUME_ARG) $(EC2_EXECUTE_ARG)

local-dir-ec2-evaluate: local-dir-check ## 归档 EC2 本地目录训练产物并生成评估摘要（默认 dry-run）
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py evaluate \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' \
		--local-model '$(LOCAL_FINAL_MODEL)' --epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) \
		--batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) --run-name '$(EC2_RUN_NAME)' \
		--artifact-root '$(LOCAL_EC2_ARTIFACT_ROOT)' --latest-run-file '$(LOCAL_EC2_LATEST_RUN_FILE)' \
		--notes '$(EC2_EVAL_NOTES)' $(EC2_EXECUTE_ARG)

local-dir-ec2-download-artifacts: local-dir-check ## 下载 EC2 本地目录训练归档目录（默认 dry-run）
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py download-artifacts \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LOCAL_FINAL_MODEL)' \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(LOCAL_EC2_ARTIFACT_ROOT)' \
		--local-artifact-root '$(LOCAL_EC2_LOCAL_ARTIFACT_ROOT)' $(EC2_EXECUTE_ARG)

local-dir-ec2-download-model: local-dir-check ## 下载 EC2 本地目录训练 best.pt（默认 dry-run）
	$(VENV_BIN)/python scripts/ec2/diaper_workflow.py download-model \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LOCAL_FINAL_MODEL)' \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(LOCAL_EC2_ARTIFACT_ROOT)' \
		$(EC2_EXECUTE_ARG)
