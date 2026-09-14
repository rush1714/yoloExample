# 公共变量、公共工具目标、Label Studio 基础目标、训练和推理目标。
# 业务流程专属参数放在各自 makefiles/*/Makefile.mk 中。

# 项目根目录：默认等于当前执行 make 的目录；通常不需要修改。
PROJECT_ROOT := $(shell pwd)
# Python 虚拟环境 bin 目录：所有 Python/Label Studio 命令都从这里执行。
VENV_BIN     := $(PROJECT_ROOT)/.venv/bin
# 项目内临时目录：替代 /tmp，避免命令在系统临时目录中产生不可追踪状态。
TMP_DIR      := $(PROJECT_ROOT)/.tmp
# Label Studio shell/start 的工作目录：用于避开当前目录导入安全问题，同时仍在项目内。
LS_WORK_DIR  := $(TMP_DIR)/label-studio
# Label Studio 应用数据目录：保存本地配置、上传文件等运行数据；数据库本体使用 PostgreSQL。
LS_DATA_DIR  := $(PROJECT_ROOT)/.label-studio-data
# 日志目录：Label Studio 后台启动日志、PID 文件等写入这里。
LOG_DIR      := $(PROJECT_ROOT)/logs
# 模型备份目录。
MODELS_BAK_DIR  := $(PROJECT_ROOT)/models/backup

# ── 通用 Excel 下载参数 ───────────────────────────────────────
EXCEL              ?= /Users/guobiao/DOC/森大2.0/18.陈列数据/CI_2026-08-26_最新1801个_02.xlsx
EXCEL_COLUMN       ?= 生动化照片链接
EXCEL_WORKERS      ?= 10
EXCEL_TIMEOUT      ?= 30

# ── 品牌与数据目录公共参数 ───────────────────────────────────
BRAND              ?= all
BRAND_LIBRARY      ?= $(PROJECT_ROOT)/config/brand_keywords.json
BRAND_PROFILE_SCRIPT := $(PROJECT_ROOT)/scripts/config/brand_profile.py
DATASET_NAME       := $(shell $(VENV_BIN)/python $(BRAND_PROFILE_SCRIPT) --brand-library $(BRAND_LIBRARY) --brand '$(BRAND)' --field dataset-name)
BRAND_DISPLAY_NAME := $(shell $(VENV_BIN)/python $(BRAND_PROFILE_SCRIPT) --brand-library $(BRAND_LIBRARY) --brand '$(BRAND)' --field display-name)
BRAND_FILTER       := $(shell $(VENV_BIN)/python $(BRAND_PROFILE_SCRIPT) --brand-library $(BRAND_LIBRARY) --brand '$(BRAND)' --field brand-filter)
BRAND_FILTER_ARG   := $(if $(BRAND_FILTER),--brand-filter '$(BRAND_FILTER)',)
COMPACT_CLASS_IDS_ARG := $(if $(BRAND_FILTER),--compact-class-ids,)
SHARED_DATASET_ROOT ?= $(PROJECT_ROOT)/datasets/multibrand
RAW_DIR            ?= $(SHARED_DATASET_ROOT)/raw/images
RAW_METADATA_DIR   ?= $(SHARED_DATASET_ROOT)/raw/metadata
DATASET_ROOT       ?= $(PROJECT_ROOT)/datasets/$(DATASET_NAME)
CONFIG_GENERATED_DIR ?= $(PROJECT_ROOT)/config/generated
TRAIN_DATA_YAML    ?= $(CONFIG_GENERATED_DIR)/$(DATASET_NAME).yaml
LS_LABEL_CONFIG_XML ?= $(DATASET_ROOT)/label_studio/label_config.xml

# ── Label Studio 公共参数 ────────────────────────────────────
POSTGRE_USER     ?= guobiao
POSTGRE_PASSWORD ?=
POSTGRE_NAME     ?= labelstudio
POSTGRE_HOST     ?= localhost
POSTGRE_PORT     ?= 5432
LS_PORT          ?= 9001
LS_IMPORT_JSON   ?= $(DATASET_ROOT)/label_studio/multibrand_label_studio_import.json
LS_LOCAL_FILES_PATH ?= $(RAW_DIR)
LS_LOG_FILE      ?= $(LOG_DIR)/label-studio.log
LS_PID_FILE      ?= $(LOG_DIR)/label-studio.pid
LS_PROJECT_TITLE ?= $(BRAND_DISPLAY_NAME) Package Review
LS_BRAND_FILTER ?= $(BRAND_FILTER)
LS_COMPACT_CLASS_IDS ?= $(if $(BRAND_FILTER),1,0)
LS_PROJECT_ID    ?=
LS_EXPORT_FORMAT ?= JSON
LS_EXPORT_DIR    ?= $(DATASET_ROOT)/label_studio/exports
LS_EXPORT_PATH   ?= $(LS_EXPORT_DIR)/label_studio_export.json
LS_TO_YOLO_REPORT ?= $(LS_EXPORT_DIR)/label_studio_to_yolo_report.json
LS_TO_YOLO_CLEAR ?= 0
LS_TO_YOLO_SKIP_EMPTY ?= 0
LS_TO_YOLO_CLEAR_ARG := $(if $(filter 1 true yes,$(LS_TO_YOLO_CLEAR)),--clear-output,)
LS_TO_YOLO_SKIP_EMPTY_ARG := $(if $(filter 1 true yes,$(LS_TO_YOLO_SKIP_EMPTY)),--skip-empty-annotations,)

# ── 训练/推理公共参数 ───────────────────────────────────────
TRAIN_BASE_MODEL ?= $(PROJECT_ROOT)/models/yolo26m.pt
TRAIN_EPOCHS     ?= 55
TRAIN_IMGSZ      ?= 960
TRAIN_BATCH      ?= -1
TRAIN_DEVICE     ?= mps
TRAIN_PROJECT    ?= $(PROJECT_ROOT)/models/train
TRAIN_NAME       ?= $(DATASET_NAME)
FINAL_MODEL      ?= $(PROJECT_ROOT)/models/$(DATASET_NAME)-best.pt
TRAIN_RESUME     ?= 0
TRAIN_DEVICE_ARG := $(if $(TRAIN_DEVICE),--device $(TRAIN_DEVICE),)
TRAIN_RESUME_ARG := $(if $(filter 1 true yes,$(TRAIN_RESUME)),--resume,)
PREDICT_SOURCE   ?= $(PROJECT_ROOT)/data/samples/multibrand-shelf.webp
PREDICT_MODEL    ?= $(FINAL_MODEL)
PREDICT_CONF     ?= 0.35
PREDICT_IMGSZ    ?= 960
PREDICT_OUTPUT_DIR ?= $(PROJECT_ROOT)/outputs/predict

# ── 本地目录图片导入 Label Studio 参数 ─────────────────────────
# 本地目录数据集名称；用于 datasets/local/<name> 隔离导入、导出和训练数据。
LOCAL_DATASET_NAME ?= local_dataset
# 已存在的本地图片目录；可传绝对路径，例如 /Users/guobiao/Downloads/images。
LOCAL_IMAGES_DIR ?= $(PROJECT_ROOT)/data/local_import/images
# 单类别标签名；Label Studio 和 YOLO 转换均使用该名称。
LOCAL_LABEL_NAME ?= diaper
LOCAL_IMAGES_ABS := $(shell LOCAL_IMAGES_DIR='$(LOCAL_IMAGES_DIR)' $(VENV_BIN)/python -c 'import os; from pathlib import Path; print(Path(os.environ["LOCAL_IMAGES_DIR"]).expanduser().resolve())')
# 本地目录导入/导出数据集根目录；如需自定义输出位置，请改这个变量，不要把路径写到 LOCAL_DATASET_NAME。
LOCAL_DATASET_ROOT ?= $(PROJECT_ROOT)/datasets/local/$(LOCAL_DATASET_NAME)
LOCAL_DATASET_ROOT_ABS := $(shell LOCAL_DATASET_ROOT='$(LOCAL_DATASET_ROOT)' $(VENV_BIN)/python -c 'import os; from pathlib import Path; print(Path(os.environ["LOCAL_DATASET_ROOT"]).expanduser().resolve())')
LOCAL_LS_IMPORT_JSON ?= $(LOCAL_DATASET_ROOT_ABS)/label_studio/local_dir_label_studio_import.json
LOCAL_LS_LABEL_CONFIG_XML ?= $(LOCAL_DATASET_ROOT_ABS)/label_studio/label_config.xml
LOCAL_LS_EXPORT_DIR ?= $(LOCAL_DATASET_ROOT_ABS)/label_studio/exports
LOCAL_LS_EXPORT_PATH ?= $(LOCAL_LS_EXPORT_DIR)/label_studio_export.json
LOCAL_LS_TO_YOLO_REPORT ?= $(LOCAL_LS_EXPORT_DIR)/label_studio_to_yolo_report.json
LOCAL_DATA_YAML ?= $(CONFIG_GENERATED_DIR)/local_$(LOCAL_DATASET_NAME).yaml
LOCAL_FINAL_MODEL ?= $(PROJECT_ROOT)/models/local/$(LOCAL_DATASET_NAME)/$(EC2_TRAIN_PROFILE)/best.pt
LOCAL_EC2_REMOTE_DATASET_ROOT ?= datasets/local/$(LOCAL_DATASET_NAME)
LOCAL_EC2_REMOTE_DATA_YAML ?= config/generated/local_$(LOCAL_DATASET_NAME).yaml
LOCAL_EC2_TRAIN_NAME ?= local_$(LOCAL_DATASET_NAME)
LOCAL_EC2_REMOTE_FINAL_MODEL ?= models/ec2/local/$(LOCAL_DATASET_NAME)/$(EC2_TRAIN_PROFILE)/best.pt
LOCAL_EC2_ARTIFACT_ROOT ?= artifacts/local/$(LOCAL_DATASET_NAME)/$(EC2_TRAIN_PROFILE)
LOCAL_EC2_LATEST_RUN_FILE ?= $(LOCAL_EC2_ARTIFACT_ROOT)/latest-run.txt
LOCAL_EC2_LOCAL_ARTIFACT_ROOT ?= outputs/ec2/local/$(LOCAL_DATASET_NAME)/$(EC2_TRAIN_PROFILE)
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

export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED := true
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT := /
export LABEL_STUDIO_BROWSER_OPEN := false
export NLTK_DISABLE_IMPORT_SECURITY := 1
export PROJECT_ROOT
export DJANGO_DB := postgresql
export POSTGRE_USER
export POSTGRE_PASSWORD
export POSTGRE_NAME
export POSTGRE_HOST
export POSTGRE_PORT
export LS_IMPORT_JSON
export LS_LOCAL_FILES_PATH
export LS_PROJECT_TITLE
export BRAND_LIBRARY
export LS_BRAND_FILTER
export LS_COMPACT_CLASS_IDS
export LS_LABEL_CONFIG_XML
export MODELS_BAK_DIR

.PHONY: help help-params web-console prepare-dirs brand-check brand-list \
	ls-setup ls-start ls-migrate ls-shell ls-stop ls-apply ls-export \
	local-dir-check local-dir-yaml local-dir-ls-import-json local-dir-ls-apply 1-local-dir-workflow-to-ls local-dir-ls-export local-dir-ls-to-yolo 2-local-dir-workflow-after-ls \
	local-dir-ec2-upload-data local-dir-ec2-train local-dir-ec2-train-smoke local-dir-ec2-train-baseline local-dir-ec2-train-improve local-dir-ec2-evaluate local-dir-ec2-download-artifacts local-dir-ec2-download-model \
	data-validate train predict datasets-clean-preview datasets-clean-ignored datasets-clean-untracked-except-raw-preview datasets-clean-untracked-except-raw ls-db-create ls-db-check bak-data

help: ## 显示命令帮助和常用参数说明
	@printf "\033[1m可用命令\033[0m\n"
	@grep -h -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-32s\033[0m %s\n", $$1, $$2}'
	@$(MAKE) --no-print-directory help-params

help-params: ## 显示 Make 参数默认值；各流程详见 makefiles/*/README.md
	@printf "\n\033[1m常用参数说明（各流程详见 makefiles/*/README.md）\033[0m\n"
	@printf "\n[公共]\n"
	@printf "  EXCEL=%s\n" "$(EXCEL)"
	@printf "  EXCEL_COLUMN=%s\n" "$(EXCEL_COLUMN)"
	@printf "  BRAND=%s\n" "$(BRAND)"
	@printf "  DATASET_ROOT=%s\n" "$(DATASET_ROOT)"
	@printf "  TRAIN_NAME=%s\n" "$(TRAIN_NAME)"
	@printf "  TRAIN_DEVICE=%s\n" "$(TRAIN_DEVICE)"
	@printf "\n[本地目录导入]\n"
	@printf "  LOCAL_DATASET_NAME=%s\n" "$(LOCAL_DATASET_NAME)"
	@printf "  LOCAL_IMAGES_DIR=%s\n" "$(LOCAL_IMAGES_DIR)"
	@printf "  LOCAL_DATASET_ROOT=%s\n" "$(LOCAL_DATASET_ROOT)"
	@printf "  LOCAL_LABEL_NAME=%s\n" "$(LOCAL_LABEL_NAME)"
	@printf "  LOCAL_RECURSIVE=%s\n" "$(LOCAL_RECURSIVE)"
	@printf "\n流程专属变量示例请看：\n"
	@printf "  makefiles/brand-ocr-yoloworld/README.md\n"
	@printf "  makefiles/brand-llm-ocr-yoloworld/README.md\n"
	@printf "  makefiles/brand-yoloe-visual/README.md\n"
	@printf "  makefiles/diaper-category-ec2/README.md\n"

web-console: ## 启动本地 Make 命令与数据可视化页面
	node web-console/server.js

prepare-dirs: ## 创建项目内临时目录和日志目录
	@mkdir -p $(TMP_DIR) $(LS_WORK_DIR) $(LOG_DIR) $(LS_EXPORT_DIR)

datasets-clean-preview: ## 预览 datasets/ 下会被 git clean 删除的 ignored 文件
	@git clean -ndX -- datasets/ \
	&& git clean -ndX -- models/train/

datasets-clean-ignored: ## 删除 datasets/ 下所有被 .gitignore 忽略的文件；先执行 datasets-clean-preview 确认
	@git clean -fdX -- datasets/ \
	&& git clean -fdX -- models/train/

datasets-clean-untracked-except-raw-preview: ## 预览删除 datasets/ 下除 raw 目录外的所有未跟踪内容
	@git clean -ndx -e 'raw/' -e '*/raw/' -- datasets/

datasets-clean-untracked-except-raw: ## 删除 datasets/ 下除 raw 目录外的所有未跟踪内容；先执行预览命令确认
	@git clean -fdx -e 'raw/' -e '*/raw/' -- datasets/

bak-data: ## 备份 models/ 下的 .pt 权重，并按日期时间和原文件名重命名
	@timestamp="$$(date '+%Y%m%d_%H%M%S')"; \
	export timestamp; \
	mkdir -p "$(MODELS_BAK_DIR)"; \
	find "$(PROJECT_ROOT)/models" -path "$(MODELS_BAK_DIR)" -prune -o -type f -name '*.pt' -exec sh -c 'for source do filename=$$(basename "$$source"); target="$(MODELS_BAK_DIR)/$${timestamp}_$${filename}"; cp "$$source" "$$target"; echo "已备份 $$source -> $$target"; done' sh {} +; \
	echo "权重备份完成：$(MODELS_BAK_DIR)"

brand-check: ## 验证 BRAND 是否存在于当前品牌库
	@$(VENV_BIN)/python $(BRAND_PROFILE_SCRIPT) --brand-library $(BRAND_LIBRARY) --brand '$(BRAND)' --field dataset-name >/dev/null

brand-list: ## 显示当前品牌库支持的 BRAND 参数
	@$(VENV_BIN)/python $(BRAND_PROFILE_SCRIPT) --brand-library $(BRAND_LIBRARY) --brand all --field available-brands

ls-setup: ls-db-create ls-migrate ## 首次初始化 PostgreSQL 数据库并执行迁移

ls-start: ls-db-check prepare-dirs ## 后台启动 Label Studio
	@if [ -n "$$(lsof -ti :$(LS_PORT) 2>/dev/null)" ]; then \
		echo "Label Studio 已在端口 $(LS_PORT) 运行，PID: $$(lsof -ti :$(LS_PORT) 2>/dev/null | tr '\n' ' ')"; \
		echo "日志文件：$(LS_LOG_FILE)"; \
	else \
		echo "===== $$(date '+%Y-%m-%d %H:%M:%S') start Label Studio port $(LS_PORT) =====" >> $(LS_LOG_FILE); \
		( cd $(LS_WORK_DIR) && exec env PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio start --data-dir $(LS_DATA_DIR) --port $(LS_PORT) --host 0.0.0.0 --no-browser ) >> $(LS_LOG_FILE) 2>&1 & \
		pid=$$!; echo $$pid > $(LS_PID_FILE); sleep 2; \
		if kill -0 $$pid 2>/dev/null; then echo "Label Studio 已后台启动，PID: $$pid"; echo "访问地址：http://localhost:$(LS_PORT)"; else echo "Label Studio 启动失败，请查看日志：$(LS_LOG_FILE)"; rm -f $(LS_PID_FILE); exit 1; fi; \
	fi

ls-migrate: ls-db-create prepare-dirs ## 执行 Django 数据库迁移
	cd $(LS_WORK_DIR) && printf 'from django.core.management import call_command\ncall_command("migrate", "--no-color")\nexit()\n' | \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

ls-shell: ls-db-check prepare-dirs ## 进入 Label Studio Django shell
	cd $(LS_WORK_DIR) && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

ls-stop: ## 停止 Label Studio
	@pids="$$(lsof -ti :$(LS_PORT) 2>/dev/null | sort -u | tr '\n' ' ')"; \
	if [ -n "$$pids" ]; then kill $$pids && rm -f $(LS_PID_FILE) && echo "已停止 PID $$pids"; else rm -f $(LS_PID_FILE); echo "端口 $(LS_PORT) 没有运行中的进程"; fi

ls-apply: ls-db-check prepare-dirs ## 通过 Django shell 导入任务到 Label Studio
	cd $(LS_WORK_DIR) && printf 'exec(open("$(PROJECT_ROOT)/scripts/label_studio/apply_import.py", encoding="utf-8").read())\nexit()\n' | \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

ls-export: ls-db-check prepare-dirs ## 从 Label Studio 导出 JSON；需传 LS_PROJECT_ID=<项目ID>
	@[ -n "$(LS_PROJECT_ID)" ] || (echo "错误：请传入 LS_PROJECT_ID，例如：make ls-export LS_PROJECT_ID=2" && exit 1)
	cd $(LS_WORK_DIR) && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio export \
		--data-dir $(LS_DATA_DIR) \
		--export-path $(LS_EXPORT_PATH) \
		$(LS_PROJECT_ID) $(LS_EXPORT_FORMAT)

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
	cd $(LS_WORK_DIR) && printf 'exec(open("$(PROJECT_ROOT)/scripts/label_studio/apply_import.py", encoding="utf-8").read())\nexit()\n' | \
		LS_IMPORT_JSON='$(LOCAL_LS_IMPORT_JSON)' \
		LS_LOCAL_FILES_PATH='$(LOCAL_IMAGES_ABS)' \
		LS_PROJECT_TITLE='Local Dir $(LOCAL_DATASET_NAME)' \
		LS_PROJECT_DESCRIPTION='本地目录图片单类别标注项目。' \
		LS_LOCAL_FILES_STORAGE_TITLE='Local Dir $(LOCAL_DATASET_NAME) images' \
		LS_LOCAL_FILES_STORAGE_DESCRIPTION='Local image directory imported from LOCAL_IMAGES_DIR.' \
		LS_LABEL_CONFIG_XML='$(LOCAL_LS_LABEL_CONFIG_XML)' \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

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
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py upload-data \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LOCAL_FINAL_MODEL)' \
		$(EC2_EXECUTE_ARG)

local-dir-ec2-train: local-dir-check ## 在 EC2 训练本地目录数据集（默认 dry-run；EC2_EXECUTE=1 才执行）
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py train \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' \
		--local-model '$(LOCAL_FINAL_MODEL)' --epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) \
		--batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) --profile '$(EC2_TRAIN_PROFILE)' \
		--artifact-root '$(LOCAL_EC2_ARTIFACT_ROOT)' --latest-run-file '$(LOCAL_EC2_LATEST_RUN_FILE)' \
		$(EC2_RESUME_ARG) $(EC2_EXECUTE_ARG)

local-dir-ec2-train-smoke: ## 使用 smoke 档位训练本地目录数据集
	$(MAKE) --no-print-directory local-dir-ec2-train EC2_TRAIN_PROFILE=smoke

local-dir-ec2-train-baseline: ## 使用 baseline 档位训练本地目录数据集
	$(MAKE) --no-print-directory local-dir-ec2-train EC2_TRAIN_PROFILE=baseline

local-dir-ec2-train-improve: ## 使用 improve 档位训练本地目录数据集
	$(MAKE) --no-print-directory local-dir-ec2-train EC2_TRAIN_PROFILE=improve

local-dir-ec2-evaluate: local-dir-check ## 归档 EC2 本地目录训练产物并生成评估摘要（默认 dry-run）
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py evaluate \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' \
		--local-model '$(LOCAL_FINAL_MODEL)' --epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) \
		--batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) --profile '$(EC2_TRAIN_PROFILE)' \
		--artifact-root '$(LOCAL_EC2_ARTIFACT_ROOT)' --latest-run-file '$(LOCAL_EC2_LATEST_RUN_FILE)' \
		--notes '$(EC2_EVAL_NOTES)' $(EC2_EXECUTE_ARG)

local-dir-ec2-download-artifacts: local-dir-check ## 下载 EC2 本地目录训练归档目录（默认 dry-run）
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py download-artifacts \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LOCAL_FINAL_MODEL)' \
		--profile '$(EC2_TRAIN_PROFILE)' --artifact-root '$(LOCAL_EC2_ARTIFACT_ROOT)' \
		--local-artifact-root '$(LOCAL_EC2_LOCAL_ARTIFACT_ROOT)' $(EC2_EXECUTE_ARG)

local-dir-ec2-download-model: local-dir-check ## 下载 EC2 本地目录训练 best.pt（默认 dry-run）
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py download-model \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country local --version '$(LOCAL_DATASET_NAME)' --label-name '$(LOCAL_LABEL_NAME)' \
		--dataset-root '$(LOCAL_DATASET_ROOT_ABS)' --data-yaml '$(LOCAL_DATA_YAML)' \
		--remote-dataset-root '$(LOCAL_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(LOCAL_EC2_REMOTE_DATA_YAML)' --train-name '$(LOCAL_EC2_TRAIN_NAME)' \
		--remote-final-model '$(LOCAL_EC2_REMOTE_FINAL_MODEL)' --local-model '$(LOCAL_FINAL_MODEL)' \
		--profile '$(EC2_TRAIN_PROFILE)' --artifact-root '$(LOCAL_EC2_ARTIFACT_ROOT)' \
		$(EC2_EXECUTE_ARG)

train: data-validate ## 训练 YOLO 模型
	$(VENV_BIN)/python scripts/training/train.py \
		--data $(TRAIN_DATA_YAML) \
		--base-model $(TRAIN_BASE_MODEL) \
		--epochs $(TRAIN_EPOCHS) \
		--imgsz $(TRAIN_IMGSZ) \
		--batch $(TRAIN_BATCH) \
		$(TRAIN_DEVICE_ARG) \
		--project $(TRAIN_PROJECT) \
		--name $(TRAIN_NAME) \
		--export-model $(FINAL_MODEL) \
		$(TRAIN_RESUME_ARG)

data-validate: brand-yaml ## 校验正式 YOLO 数据集结构、标签和类别
	$(VENV_BIN)/python scripts/training/validate_dataset.py --data $(TRAIN_DATA_YAML)

predict: ## 使用训练后的模型对 PREDICT_SOURCE 做推理验证
	$(VENV_BIN)/python scripts/inference/predict.py '$(PREDICT_SOURCE)' \
		--model $(PREDICT_MODEL) \
		--conf $(PREDICT_CONF) \
		--imgsz $(PREDICT_IMGSZ) \
		--output-dir $(PREDICT_OUTPUT_DIR)

ls-db-create: ## 如果 PostgreSQL 数据库不存在则创建
	@if PGPASSWORD="$(POSTGRE_PASSWORD)" psql -U $(POSTGRE_USER) -h $(POSTGRE_HOST) -p $(POSTGRE_PORT) -d $(POSTGRE_NAME) -c 'SELECT 1' >/dev/null 2>&1; then \
		echo "PostgreSQL 数据库 $(POSTGRE_NAME) 已存在"; \
	else \
		echo "创建 PostgreSQL 数据库 $(POSTGRE_NAME)"; \
		PGPASSWORD="$(POSTGRE_PASSWORD)" createdb -U $(POSTGRE_USER) -h $(POSTGRE_HOST) -p $(POSTGRE_PORT) $(POSTGRE_NAME); \
	fi

ls-db-check: ## 检查 PostgreSQL 数据库是否可用
	@PGPASSWORD="$(POSTGRE_PASSWORD)" psql -U $(POSTGRE_USER) -h $(POSTGRE_HOST) -p $(POSTGRE_PORT) -d $(POSTGRE_NAME) -c 'SELECT 1' >/dev/null 2>&1 \
		|| (echo "错误：数据库 $(POSTGRE_NAME) 不可用，请先执行: make ls-db-create" && exit 1)
	@echo "PostgreSQL 数据库 $(POSTGRE_NAME) 连接正常"
