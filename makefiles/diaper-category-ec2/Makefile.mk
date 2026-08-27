# 纸尿裤大类正式标注 + EC2 A10 训练/推理完整流程

# ── 纸尿裤大类正式标注数据参数 ───────────────────────────────
# 国家/市场代码；用于 datasets/diaper_category/<country>/<version> 分目录。
DIAPER_COUNTRY ?= CI
# 数据版本；默认按当天日期，建议实际项目显式传 vYYYYMMDD 或业务批次号。
DIAPER_VERSION ?= v$(shell date +%Y-%m-%d)_01
DIAPER_DATASET_NAME := diaper_category_$(DIAPER_COUNTRY)_$(DIAPER_VERSION)
# 正式图片 Excel；默认复用公共 EXCEL，也可按国家单独传。
DIAPER_EXCEL ?= $(EXCEL)
# 图片 URL 列名；默认复用公共 EXCEL_COLUMN。
DIAPER_EXCEL_COLUMN ?= $(EXCEL_COLUMN)
# 单类别标签名；Label Studio 与 YOLO YAML 均使用该名称。
DIAPER_LABEL_NAME ?= diaper
DIAPER_DATASET_ROOT ?= $(PROJECT_ROOT)/datasets/diaper_category/$(DIAPER_COUNTRY)/$(DIAPER_VERSION)
DIAPER_RAW_DIR ?= $(DIAPER_DATASET_ROOT)/raw/images
DIAPER_RAW_METADATA_DIR ?= $(DIAPER_DATASET_ROOT)/raw/metadata
DIAPER_LS_IMPORT_JSON ?= $(DIAPER_DATASET_ROOT)/label_studio/diaper_category_label_studio_import.json
DIAPER_LS_LABEL_CONFIG_XML ?= $(DIAPER_DATASET_ROOT)/label_studio/label_config.xml
DIAPER_LS_EXPORT_DIR ?= $(DIAPER_DATASET_ROOT)/label_studio/exports
DIAPER_LS_EXPORT_PATH ?= $(DIAPER_LS_EXPORT_DIR)/label_studio_export.json
DIAPER_LS_TO_YOLO_REPORT ?= $(DIAPER_LS_EXPORT_DIR)/label_studio_to_yolo_report.json
DIAPER_DATA_YAML ?= $(CONFIG_GENERATED_DIR)/$(DIAPER_DATASET_NAME).yaml
DIAPER_TRAIN_NAME ?= $(DIAPER_DATASET_NAME)
DIAPER_FINAL_MODEL ?= $(PROJECT_ROOT)/models/diaper_category/$(DIAPER_COUNTRY)/$(DIAPER_VERSION)/best.pt

# ── AWS EC2 A10 参数 ────────────────────────────────────────
# EC2 地址或 SSH Host 别名；默认空，dry-run 时也会保留占位。
EC2_HOST ?= 100.52.169.93
# EC2 SSH 用户；Ubuntu AMI 默认 ubuntu。
EC2_USER ?= ec2-user
# SSH 私钥路径；未设置时不传 -i。
EC2_KEY ?= ~/.ssh/smdp-yolo-gpu-key.pem
# SSH 端口。
EC2_PORT ?= 22
# EC2 上项目根目录。
EC2_PROJECT_ROOT ?= /home/$(EC2_USER)/yoloExample
# EC2 上执行训练/推理前激活 PyTorch 环境；用户当前环境已使用该路径。
EC2_ACTIVATE_CMD ?= source /opt/pytorch/bin/activate
# EC2 上 Python 执行命令；激活 PyTorch 环境后默认使用 python3。
EC2_PYTHON_CMD ?= python3
# 训练档位：smoke=yolo11n/640/5，baseline=yolo11s/960/100，improve=yolo11m/960/150，custom=使用显式参数。
EC2_TRAIN_PROFILE ?= smoke
# A10 GPU 设备号。
EC2_TRAIN_DEVICE ?= 0
# EC2 训练 batch。
EC2_TRAIN_BATCH ?= 16
# EC2 训练轮数；默认由 EC2_TRAIN_PROFILE 派生，也可手动覆盖。
EC2_TRAIN_EPOCHS ?= $(if $(filter smoke,$(EC2_TRAIN_PROFILE)),5,$(if $(filter baseline,$(EC2_TRAIN_PROFILE)),100,$(if $(filter improve,$(EC2_TRAIN_PROFILE)),150,100)))
# EC2 训练/推理尺寸；默认由 EC2_TRAIN_PROFILE 派生，也可手动覆盖。
EC2_TRAIN_IMGSZ ?= $(if $(filter smoke,$(EC2_TRAIN_PROFILE)),640,960)
# EC2 基座模型；默认由 EC2_TRAIN_PROFILE 派生，也可手动覆盖。
EC2_BASE_MODEL ?= $(if $(filter smoke,$(EC2_TRAIN_PROFILE)),yolo11n.pt,$(if $(filter baseline,$(EC2_TRAIN_PROFILE)),yolo11s.pt,$(if $(filter improve,$(EC2_TRAIN_PROFILE)),yolo11m.pt,models/yolo26m.pt)))
EC2_REMOTE_DATA_YAML ?= config/generated/$(DIAPER_DATASET_NAME).yaml
EC2_REMOTE_FINAL_MODEL ?= models/ec2/diaper_category/$(DIAPER_COUNTRY)/$(DIAPER_VERSION)/$(EC2_TRAIN_PROFILE)/best.pt
EC2_ARTIFACT_ROOT ?= artifacts/diaper_category/$(DIAPER_COUNTRY)/$(DIAPER_VERSION)/$(EC2_TRAIN_PROFILE)
EC2_LOCAL_ARTIFACT_ROOT ?= outputs/ec2/diaper_category/$(DIAPER_COUNTRY)/$(DIAPER_VERSION)/$(EC2_TRAIN_PROFILE)
EC2_PREDICT_SOURCE ?= data/samples/multibrand-shelf.webp
EC2_EVAL_NOTES ?= 首轮 PoC 建议先用 300~500 张有效标注图验证闭环，再扩大数据量。
EC2_EXECUTE ?= 0
EC2_EXECUTE_ARG := $(if $(filter 1 true yes,$(EC2_EXECUTE)),--execute,)
EC2_KEY_ARG := $(if $(EC2_KEY),--key $(EC2_KEY),)
EC2_RESUME_ARG := $(if $(filter 1 true yes,$(TRAIN_RESUME)),--resume,)

.PHONY: diaper-yaml diaper-import-excel diaper-ls-import-json diaper-ls-apply diaper-ls-export diaper-ls-to-yolo \
	diaper-workflow-to-ls diaper-workflow-after-ls diaper-prepare-dirs \
	01-diaper-ec2-upload-project 02-diaper-ec2-upload-data \
	03-diaper-ec2-train-smoke 04-diaper-ec2-evaluate 05-diaper-ec2-download-artifacts \
	06-diaper-ec2-train-baseline 07-diaper-ec2-train-improve 08-diaper-ec2-predict 09-diaper-ec2-download-model \
	diaper-ec2-upload-project diaper-ec2-upload-data diaper-ec2-train diaper-ec2-train-smoke diaper-ec2-train-baseline diaper-ec2-train-improve \
	diaper-ec2-evaluate diaper-ec2-predict diaper-ec2-download-model diaper-ec2-download-artifacts

diaper-yaml: ## 生成纸尿裤大类单类别 YOLO YAML
	$(VENV_BIN)/python scripts/config/write_single_class_yolo_yaml.py \
		--output $(DIAPER_DATA_YAML) \
		--dataset-root ../../datasets/diaper_category/$(DIAPER_COUNTRY)/$(DIAPER_VERSION) \
		--class-name '$(DIAPER_LABEL_NAME)'

diaper-import-excel: ## 下载纸尿裤大类正式图片到国家/版本目录
	$(VENV_BIN)/python scripts/data_import/import_images_from_excel.py \
		--excel '$(DIAPER_EXCEL)' \
		--column '$(DIAPER_EXCEL_COLUMN)' \
		--output-dir $(DIAPER_RAW_DIR) \
		--metadata-dir $(DIAPER_RAW_METADATA_DIR) \
		--workers $(EXCEL_WORKERS) \
		--timeout $(EXCEL_TIMEOUT)

diaper-ls-import-json: ## 生成纸尿裤大类 LS 导入 JSON，无预标注 predictions
	$(VENV_BIN)/python scripts/label_studio/generate_single_class_import.py \
		--raw-report $(DIAPER_RAW_METADATA_DIR)/download_report.csv \
		--output $(DIAPER_LS_IMPORT_JSON) \
		--label-name '$(DIAPER_LABEL_NAME)' \
		--label-config-output $(DIAPER_LS_LABEL_CONFIG_XML) \
		--dataset-name $(DIAPER_DATASET_NAME)

diaper-ls-apply: ls-db-check diaper-prepare-dirs ## 导入纸尿裤大类任务到 Label Studio（每执行一次都会创建一个新 LS 项目）
	cd $(LS_WORK_DIR) && printf 'exec(open("$(PROJECT_ROOT)/scripts/label_studio/apply_import.py", encoding="utf-8").read())\nexit()\n' | \
		LS_IMPORT_JSON='$(DIAPER_LS_IMPORT_JSON)' \
		LS_LOCAL_FILES_PATH='$(DIAPER_RAW_DIR)' \
		LS_PROJECT_TITLE='Diaper Category $(DIAPER_COUNTRY) $(DIAPER_VERSION)' \
		LS_LABEL_CONFIG_XML='$(DIAPER_LS_LABEL_CONFIG_XML)' \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

diaper-ls-export: ls-db-check diaper-prepare-dirs ## 从 Label Studio 导出纸尿裤大类 JSON；需传 LS_PROJECT_ID=<项目ID>
	@[ -n "$(LS_PROJECT_ID)" ] || (echo "错误：请传入 LS_PROJECT_ID，例如：make diaper-ls-export LS_PROJECT_ID=2" && exit 1)
	mkdir -p $(DIAPER_LS_EXPORT_DIR)
	cd $(LS_WORK_DIR) && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio export \
		--data-dir $(LS_DATA_DIR) \
		--export-path $(DIAPER_LS_EXPORT_PATH) \
		$(LS_PROJECT_ID) $(LS_EXPORT_FORMAT)

diaper-ls-to-yolo: diaper-yaml ## 转换纸尿裤大类 LS 导出为 YOLO 数据集
	$(VENV_BIN)/python scripts/label_studio/export_single_class_to_yolo.py \
		--input $(DIAPER_LS_EXPORT_PATH) \
		--output-root $(DIAPER_DATASET_ROOT) \
		--label-name '$(DIAPER_LABEL_NAME)' \
		--report $(DIAPER_LS_TO_YOLO_REPORT) \
		$(LS_TO_YOLO_CLEAR_ARG) \
		$(LS_TO_YOLO_SKIP_EMPTY_ARG)

1-diaper-workflow-to-ls: diaper-import-excel diaper-yaml diaper-ls-import-json diaper-ls-apply ## 下载纸尿裤大类正式图片并导入 LS，无预标注

2-diaper-workflow-after-ls: diaper-ls-export diaper-ls-to-yolo ## 导出纸尿裤大类人工标注并转换 YOLO 数据集

diaper-prepare-dirs: ## 创建纸尿裤大类流程需要的临时、日志和导出目录
	@mkdir -p $(TMP_DIR) $(LS_WORK_DIR) $(LOG_DIR) $(DIAPER_LS_EXPORT_DIR)

01-diaper-ec2-upload-project: diaper-ec2-upload-project ## 01. 仅非 Git 部署环境：上传项目代码到 EC2

02-diaper-ec2-upload-data: diaper-ec2-upload-data ## 02. 仅新国家/版本首次使用：上传数据集到 EC2（训练 YAML 自动生成）

03-diaper-ec2-train-smoke: diaper-ec2-train-smoke ## 03. smoke 训练：yolo11n.pt / 640 / 5 epochs

04-diaper-ec2-evaluate: diaper-ec2-evaluate ## 04. 归档训练产物并生成 evaluation-summary.md

05-diaper-ec2-download-artifacts: diaper-ec2-download-artifacts ## 05. 下载完整训练归档目录

06-diaper-ec2-train-baseline: diaper-ec2-train-baseline ## 06. baseline 训练：yolo11s.pt / 960 / 100 epochs

07-diaper-ec2-train-improve: diaper-ec2-train-improve ## 07. improve 训练：yolo11m.pt / 960 / 150 epochs

08-diaper-ec2-predict: diaper-ec2-predict ## 08. 使用 EC2 模型做推理验证

09-diaper-ec2-download-model: diaper-ec2-download-model ## 09. 仅下载 EC2 best.pt 模型

diaper-ec2-upload-project: ## 仅非 Git 部署环境：dry-run 输出 rsync 上传项目代码命令；EC2_EXECUTE=1 才执行

# EC2 已通过 git clone 部署代码时：在本地提交后，登录 EC2 项目目录执行 git pull；不要执行本目标。
# 仅当 EC2 尚无某个国家/版本数据集时，使用下一个目标上传数据；训练 YAML 会由训练命令自动生成绝对路径版本。
# 下面保留 rsync 上传项目能力，供不使用 Git 部署的环境使用.
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py upload-project \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country '$(DIAPER_COUNTRY)' --version '$(DIAPER_VERSION)' \
		--dataset-root '$(DIAPER_DATASET_ROOT)' --data-yaml '$(DIAPER_DATA_YAML)' \
		--remote-data-yaml '$(EC2_REMOTE_DATA_YAML)' --train-name '$(DIAPER_TRAIN_NAME)' \
		--remote-final-model '$(EC2_REMOTE_FINAL_MODEL)' --local-model '$(DIAPER_FINAL_MODEL)' \
		$(EC2_EXECUTE_ARG)

diaper-ec2-upload-data: diaper-yaml ## 仅首次需要：上传当前纸尿裤数据到 EC2；训练 YAML 会由 EC2 训练命令自动生成绝对路径版本

# 说明：EC2 已通过 git clone 管理代码时，不需要用本命令上传项目代码；使用 git pull 获取提交后的更新。
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py upload-data \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country '$(DIAPER_COUNTRY)' --version '$(DIAPER_VERSION)' \
		--dataset-root '$(DIAPER_DATASET_ROOT)' --data-yaml '$(DIAPER_DATA_YAML)' \
		--remote-data-yaml '$(EC2_REMOTE_DATA_YAML)' --train-name '$(DIAPER_TRAIN_NAME)' \
		--remote-final-model '$(EC2_REMOTE_FINAL_MODEL)' --local-model '$(DIAPER_FINAL_MODEL)' \
		$(EC2_EXECUTE_ARG)

diaper-ec2-train: ## dry-run 输出 EC2 A10 训练命令；EC2_EXECUTE=1 才执行
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py train \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--country '$(DIAPER_COUNTRY)' --version '$(DIAPER_VERSION)' \
		--dataset-root '$(DIAPER_DATASET_ROOT)' --data-yaml '$(DIAPER_DATA_YAML)' \
		--remote-data-yaml '$(EC2_REMOTE_DATA_YAML)' --train-name '$(DIAPER_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(EC2_REMOTE_FINAL_MODEL)' \
		--local-model '$(DIAPER_FINAL_MODEL)' --epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) \
		--batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) \
		--profile '$(EC2_TRAIN_PROFILE)' --artifact-root '$(EC2_ARTIFACT_ROOT)' \
		$(EC2_RESUME_ARG) $(EC2_EXECUTE_ARG)

diaper-ec2-train-smoke: ## 使用 smoke 档位训练：yolo11n.pt / imgsz=640 / epochs=5
	$(MAKE) --no-print-directory diaper-ec2-train EC2_TRAIN_PROFILE=smoke

diaper-ec2-train-baseline: ## 使用 baseline 档位训练：yolo11s.pt / imgsz=960 / epochs=100
	$(MAKE) --no-print-directory diaper-ec2-train EC2_TRAIN_PROFILE=baseline

diaper-ec2-train-improve: ## 使用 improve 档位训练：yolo11m.pt / imgsz=960 / epochs=150
	$(MAKE) --no-print-directory diaper-ec2-train EC2_TRAIN_PROFILE=improve

diaper-ec2-evaluate: ## dry-run 输出 EC2 训练产物归档与 evaluation-summary.md 生成命令
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py evaluate \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--country '$(DIAPER_COUNTRY)' --version '$(DIAPER_VERSION)' \
		--dataset-root '$(DIAPER_DATASET_ROOT)' --data-yaml '$(DIAPER_DATA_YAML)' \
		--remote-data-yaml '$(EC2_REMOTE_DATA_YAML)' --train-name '$(DIAPER_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(EC2_REMOTE_FINAL_MODEL)' \
		--local-model '$(DIAPER_FINAL_MODEL)' --epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) \
		--batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) --profile '$(EC2_TRAIN_PROFILE)' \
		--artifact-root '$(EC2_ARTIFACT_ROOT)' --notes '$(EC2_EVAL_NOTES)' $(EC2_EXECUTE_ARG)

diaper-ec2-predict: ## dry-run 输出 EC2 推理验证命令；EC2_EXECUTE=1 才执行
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py predict \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--country '$(DIAPER_COUNTRY)' --version '$(DIAPER_VERSION)' \
		--dataset-root '$(DIAPER_DATASET_ROOT)' --data-yaml '$(DIAPER_DATA_YAML)' \
		--remote-data-yaml '$(EC2_REMOTE_DATA_YAML)' --train-name '$(DIAPER_TRAIN_NAME)' \
		--remote-final-model '$(EC2_REMOTE_FINAL_MODEL)' --local-model '$(DIAPER_FINAL_MODEL)' \
		--predict-source '$(EC2_PREDICT_SOURCE)' --imgsz $(EC2_TRAIN_IMGSZ) --device $(EC2_TRAIN_DEVICE) \
		$(EC2_EXECUTE_ARG)

diaper-ec2-download-model: ## dry-run 输出从 EC2 下载 best.pt 的 rsync 命令；EC2_EXECUTE=1 才执行
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py download-model \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country '$(DIAPER_COUNTRY)' --version '$(DIAPER_VERSION)' \
		--dataset-root '$(DIAPER_DATASET_ROOT)' --data-yaml '$(DIAPER_DATA_YAML)' \
		--remote-data-yaml '$(EC2_REMOTE_DATA_YAML)' --train-name '$(DIAPER_TRAIN_NAME)' \
		--remote-final-model '$(EC2_REMOTE_FINAL_MODEL)' --local-model '$(DIAPER_FINAL_MODEL)' \
		--profile '$(EC2_TRAIN_PROFILE)' --artifact-root '$(EC2_ARTIFACT_ROOT)' \
		$(EC2_EXECUTE_ARG)

diaper-ec2-download-artifacts: ## dry-run 输出从 EC2 下载完整训练归档目录的 rsync 命令
	$(VENV_BIN)/python scripts/cloud/ec2_diaper_workflow.py download-artifacts \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--country '$(DIAPER_COUNTRY)' --version '$(DIAPER_VERSION)' \
		--dataset-root '$(DIAPER_DATASET_ROOT)' --data-yaml '$(DIAPER_DATA_YAML)' \
		--remote-data-yaml '$(EC2_REMOTE_DATA_YAML)' --train-name '$(DIAPER_TRAIN_NAME)' \
		--remote-final-model '$(EC2_REMOTE_FINAL_MODEL)' --local-model '$(DIAPER_FINAL_MODEL)' \
		--profile '$(EC2_TRAIN_PROFILE)' --artifact-root '$(EC2_ARTIFACT_ROOT)' \
		--local-artifact-root '$(EC2_LOCAL_ARTIFACT_ROOT)' $(EC2_EXECUTE_ARG)
