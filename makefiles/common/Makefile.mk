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

.PHONY: help help-params prepare-dirs brand-check brand-list \
	ls-setup ls-start ls-migrate ls-shell ls-stop ls-apply ls-export \
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
	@printf "\n流程专属变量示例请看：\n"
	@printf "  makefiles/brand-ocr-yoloworld/README.md\n"
	@printf "  makefiles/brand-llm-ocr-yoloworld/README.md\n"
	@printf "  makefiles/brand-yoloe-visual/README.md\n"
	@printf "  makefiles/diaper-category-ec2/README.md\n"

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
