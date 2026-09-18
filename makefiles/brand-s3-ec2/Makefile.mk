# S3 训练图片上传、Label Studio 标注衔接与 EC2 下载训练流程。

# ── S3 数据集与配置参数 ───────────────────────────────────────
# 本地私有配置文件；可复制 config/brand_s3_ec2.example.yaml 后按实际桶和目录填写。
BRAND_S3_CONFIG ?= $(PROJECT_ROOT)/config/brand_s3_ec2.local.yaml
# S3 数据集短名称；用于 datasets/s3/<name>、config/generated/s3_<name>.yaml 等路径。
S3_DATASET_NAME ?= local_dataset
# 单类别标签名；Label Studio 与 YOLO YAML 均使用该名称。
S3_LABEL_NAME ?= diaper
# 本地待上传图片目录。
S3_LOCAL_IMAGES_DIR ?= $(LOCAL_IMAGES_DIR)
# S3 工作流本地输出根目录，只保存清单、LS 导出、YOLO 标签，不保存训练图片大文件。
S3_DATASET_ROOT ?= $(PROJECT_ROOT)/datasets/s3/$(S3_DATASET_NAME)
# S3 桶名、业务对象前缀、区域和可选 profile/endpoint；实际上传会自动归入 yolo-training/<S3_PREFIX>。
S3_BUCKET ?=
S3_PREFIX ?= $(S3_DATASET_NAME)
S3_REGION ?= ap-southeast-1
S3_PROFILE ?=
S3_ENDPOINT_URL ?=
S3_PUBLIC_BASE_URL ?=
# Label Studio 默认通过本地 Nginx 代理地址加载 S3 图片，避免依赖桶 CORS 配置。
S3_IMAGE_URL_MODE ?= nginx
S3_PROXY_HOST ?= 127.0.0.1
S3_PROXY_PORT ?= 3010
S3_PROXY_BASE_URL ?= http://$(S3_PROXY_HOST):$(S3_PROXY_PORT)
S3_PROXY_ALLOWED_ORIGIN ?= http://localhost:$(LS_PORT)
S3_PROXY_BACKEND ?= nginx
S3_NGINX_BIN ?= nginx
S3_NGINX_MODE ?= presign
S3_NGINX_PRESIGN_EXPIRES ?= 604800
S3_NGINX_RUNTIME_DIR ?= $(PROJECT_ROOT)/.tmp/s3-nginx/$(S3_DATASET_NAME)
S3_NGINX_CONF ?= $(S3_NGINX_RUNTIME_DIR)/nginx.conf
S3_NGINX_MAP ?= $(S3_NGINX_RUNTIME_DIR)/s3_image_map.conf
S3_NGINX_CACHE_DIR ?= $(S3_NGINX_RUNTIME_DIR)/cache
S3_NGINX_PID ?= $(S3_NGINX_RUNTIME_DIR)/nginx.pid
S3_RECURSIVE ?= 1
S3_LIMIT ?=
S3_DRY_RUN ?= 0
S3_UPLOAD_WORKERS ?= 8
S3_LIMIT_ARG := $(if $(S3_LIMIT),--limit $(S3_LIMIT),)
S3_RECURSIVE_ARG := $(if $(filter 0 false no,$(S3_RECURSIVE)),--no-recursive,--recursive)
S3_DRY_RUN_ARG := $(if $(filter 1 true yes,$(S3_DRY_RUN)),--dry-run,)
S3_MANIFEST_JSON ?= $(S3_DATASET_ROOT)/metadata/s3_images.json
S3_LS_IMPORT_JSON ?= $(S3_DATASET_ROOT)/label_studio/s3_label_studio_import.json
S3_LS_LABEL_CONFIG_XML ?= $(S3_DATASET_ROOT)/label_studio/label_config.xml
S3_LS_EXPORT_DIR ?= $(S3_DATASET_ROOT)/label_studio/exports
S3_LS_EXPORT_PATH ?= $(S3_LS_EXPORT_DIR)/label_studio_export.json
S3_LS_TO_YOLO_REPORT ?= $(S3_DATASET_ROOT)/metadata/label_studio_to_yolo_report.json
S3_EC2_IMAGE_MANIFEST_JSON ?= $(S3_DATASET_ROOT)/metadata/ec2_image_manifest.json
S3_EC2_IMAGE_MANIFEST_CSV ?= $(S3_DATASET_ROOT)/metadata/ec2_image_manifest.csv
S3_DATA_YAML ?= $(CONFIG_GENERATED_DIR)/s3_$(S3_DATASET_NAME).yaml
S3_LS_TO_YOLO_CLEAR ?= 0
S3_LS_TO_YOLO_SKIP_EMPTY ?= 0
S3_LS_TO_YOLO_CLEAR_ARG := $(if $(filter 1 true yes,$(S3_LS_TO_YOLO_CLEAR)),--clear-output,)
S3_LS_TO_YOLO_SKIP_EMPTY_ARG := $(if $(filter 1 true yes,$(S3_LS_TO_YOLO_SKIP_EMPTY)),--skip-empty-annotations,)

# ── S3 数据集 EC2 参数 ────────────────────────────────────────
S3_EC2_REMOTE_DATASET_ROOT ?= datasets/s3/$(S3_DATASET_NAME)
S3_EC2_REMOTE_DATA_YAML ?= config/generated/s3_$(S3_DATASET_NAME).yaml
S3_EC2_REMOTE_MANIFEST_JSON ?= datasets/s3/$(S3_DATASET_NAME)/metadata/ec2_image_manifest.json
S3_EC2_REMOTE_MANIFEST_CSV ?= datasets/s3/$(S3_DATASET_NAME)/metadata/ec2_image_manifest.csv
S3_EC2_TRAIN_NAME ?= s3_$(S3_DATASET_NAME)
S3_EC2_REMOTE_FINAL_MODEL ?= models/ec2/s3/$(S3_DATASET_NAME)/$(EC2_RUN_NAME)/best.pt
S3_FINAL_MODEL ?= $(PROJECT_ROOT)/models/s3/$(S3_DATASET_NAME)/$(EC2_RUN_NAME)/best.pt
S3_EC2_ARTIFACT_ROOT ?= artifacts/s3/$(S3_DATASET_NAME)/$(EC2_RUN_NAME)
S3_EC2_LATEST_RUN_FILE ?= $(S3_EC2_ARTIFACT_ROOT)/latest-run.txt
S3_EC2_LOCAL_ARTIFACT_ROOT ?= outputs/ec2/s3/$(S3_DATASET_NAME)/$(EC2_RUN_NAME)
# EC2 下载 S3 图片的模式：auto 优先公共 URL，public 强制公共 URL，boto3 使用 AWS SDK/IAM。
S3_EC2_DOWNLOAD_MODE ?= auto

.PHONY: brand-s3-check-config brand-s3-upload-images brand-s3-sync-manifest-from-s3 brand-s3-ls-import-json brand-s3-proxy-start brand-s3-python-proxy-start \
	brand-s3-nginx-render-config brand-s3-nginx-start brand-s3-nginx-reload brand-s3-nginx-stop brand-s3-ls-apply \
	1-brand-s3-workflow-to-ls brand-s3-ls-export brand-s3-ls-to-yolo 2-brand-s3-workflow-after-ls \
	local-ls-s3-to-yolo 2-local-ls-s3-workflow-after-ls \
	brand-s3-ec2-upload-manifest brand-s3-ec2-download-images brand-s3-ec2-train brand-s3-ec2-evaluate brand-s3-ec2-download-artifacts \
	brand-s3-ec2-download-model 3-brand-s3-workflow-ec2-train

brand-s3-check-config: ## 检查 S3 工作流关键参数
	@printf "BRAND_S3_CONFIG=%s\n" "$(BRAND_S3_CONFIG)"
	@printf "S3_DATASET_NAME=%s\n" "$(S3_DATASET_NAME)"
	@printf "S3_LOCAL_IMAGES_DIR=%s\n" "$(S3_LOCAL_IMAGES_DIR)"
	@printf "S3_DATASET_ROOT=%s\n" "$(S3_DATASET_ROOT)"
	@printf "S3_BUCKET=%s\n" "$(S3_BUCKET)"
	@printf "S3_PREFIX=%s\n" "$(S3_PREFIX)"
	@printf "S3_REGION=%s\n" "$(S3_REGION)"
	@printf "S3_IMAGE_URL_MODE=%s\n" "$(S3_IMAGE_URL_MODE)"
	@printf "S3_PROXY_BACKEND=%s\n" "$(S3_PROXY_BACKEND)"
	@printf "S3_PROXY_BASE_URL=%s\n" "$(S3_PROXY_BASE_URL)"
	@printf "S3_NGINX_MODE=%s\n" "$(S3_NGINX_MODE)"

brand-s3-upload-images: ## 上传本地图片目录到 S3 并生成图片地址清单；S3_DRY_RUN=1 只生成清单
	$(VENV_BIN)/python scripts/s3/upload_images_to_s3.py \
		--config '$(BRAND_S3_CONFIG)' \
		--dataset-name '$(S3_DATASET_NAME)' \
		--label-name '$(S3_LABEL_NAME)' \
		--input-dir '$(S3_LOCAL_IMAGES_DIR)' \
		--dataset-root '$(S3_DATASET_ROOT)' \
		--bucket '$(S3_BUCKET)' \
		--prefix '$(S3_PREFIX)' \
		--region '$(S3_REGION)' \
		--profile '$(S3_PROFILE)' \
		--endpoint-url '$(S3_ENDPOINT_URL)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' \
		--proxy-base-url '$(S3_PROXY_BASE_URL)' \
		--workers $(S3_UPLOAD_WORKERS) \
		$(S3_RECURSIVE_ARG) $(S3_LIMIT_ARG) $(S3_DRY_RUN_ARG)

brand-s3-sync-manifest-from-s3: ## 从 S3 目标目录反查对象并生成可续传上传清单
	$(VENV_BIN)/python scripts/s3/upload_images_to_s3.py \
		--config '$(BRAND_S3_CONFIG)' \
		--dataset-name '$(S3_DATASET_NAME)' \
		--label-name '$(S3_LABEL_NAME)' \
		--input-dir '$(S3_LOCAL_IMAGES_DIR)' \
		--dataset-root '$(S3_DATASET_ROOT)' \
		--bucket '$(S3_BUCKET)' \
		--prefix '$(S3_PREFIX)' \
		--region '$(S3_REGION)' \
		--profile '$(S3_PROFILE)' \
		--endpoint-url '$(S3_ENDPOINT_URL)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' \
		--proxy-base-url '$(S3_PROXY_BASE_URL)' \
		$(S3_RECURSIVE_ARG) $(S3_LIMIT_ARG) \
		--sync-from-s3

brand-s3-ls-import-json: ## 根据 S3 图片清单生成 Label Studio 导入 JSON 和标签配置
	$(VENV_BIN)/python scripts/label_studio/generate_s3_import.py \
		--config '$(BRAND_S3_CONFIG)' \
		--manifest '$(S3_MANIFEST_JSON)' \
		--output '$(S3_LS_IMPORT_JSON)' \
		--label-config-output '$(S3_LS_LABEL_CONFIG_XML)' \
		--dataset-name '$(S3_DATASET_NAME)' \
		--label-name '$(S3_LABEL_NAME)' \
		--dataset-root '$(S3_DATASET_ROOT)' \
		--image-url-mode '$(S3_IMAGE_URL_MODE)' \
		--proxy-base-url '$(S3_PROXY_BASE_URL)'

brand-s3-proxy-start: ## 启动本地 S3 图片代理；默认使用 Nginx，可传 S3_PROXY_BACKEND=python 回退旧代理
	@if [ "$(S3_PROXY_BACKEND)" = "python" ]; then \
		$(MAKE) brand-s3-python-proxy-start \
			BRAND_S3_CONFIG='$(BRAND_S3_CONFIG)' S3_BUCKET='$(S3_BUCKET)' S3_REGION='$(S3_REGION)' S3_PROFILE='$(S3_PROFILE)' \
			S3_ENDPOINT_URL='$(S3_ENDPOINT_URL)' S3_PROXY_ALLOWED_ORIGIN='$(S3_PROXY_ALLOWED_ORIGIN)' S3_PROXY_HOST='$(S3_PROXY_HOST)' S3_PROXY_PORT='$(S3_PROXY_PORT)'; \
	else \
		$(MAKE) brand-s3-nginx-start \
			BRAND_S3_CONFIG='$(BRAND_S3_CONFIG)' S3_DATASET_NAME='$(S3_DATASET_NAME)' S3_DATASET_ROOT='$(S3_DATASET_ROOT)' \
			S3_MANIFEST_JSON='$(S3_MANIFEST_JSON)' S3_BUCKET='$(S3_BUCKET)' S3_REGION='$(S3_REGION)' S3_PROFILE='$(S3_PROFILE)' \
			S3_ENDPOINT_URL='$(S3_ENDPOINT_URL)' S3_PUBLIC_BASE_URL='$(S3_PUBLIC_BASE_URL)' S3_PROXY_BASE_URL='$(S3_PROXY_BASE_URL)' \
			S3_PROXY_ALLOWED_ORIGIN='$(S3_PROXY_ALLOWED_ORIGIN)' S3_PROXY_HOST='$(S3_PROXY_HOST)' S3_PROXY_PORT='$(S3_PROXY_PORT)' \
			S3_NGINX_BIN='$(S3_NGINX_BIN)' S3_NGINX_MODE='$(S3_NGINX_MODE)' S3_NGINX_PRESIGN_EXPIRES='$(S3_NGINX_PRESIGN_EXPIRES)' \
			S3_NGINX_CONF='$(S3_NGINX_CONF)' S3_NGINX_MAP='$(S3_NGINX_MAP)' S3_NGINX_CACHE_DIR='$(S3_NGINX_CACHE_DIR)' S3_NGINX_PID='$(S3_NGINX_PID)'; \
	fi

brand-s3-python-proxy-start: ## 启动旧 Python S3 图片代理，作为 Nginx 不可用时的回退
	$(VENV_BIN)/python scripts/s3/s3_image_proxy.py \
		--config '$(BRAND_S3_CONFIG)' \
		--bucket '$(S3_BUCKET)' \
		--region '$(S3_REGION)' \
		--profile '$(S3_PROFILE)' \
		--endpoint-url '$(S3_ENDPOINT_URL)' \
		--allowed-origin '$(S3_PROXY_ALLOWED_ORIGIN)' \
		--host '$(S3_PROXY_HOST)' \
		--port $(S3_PROXY_PORT)

brand-s3-nginx-render-config: ## 根据 S3 图片清单生成本地 Nginx 图片代理配置
	$(VENV_BIN)/python scripts/s3/render_nginx_image_proxy.py \
		--config '$(BRAND_S3_CONFIG)' \
		--manifest '$(S3_MANIFEST_JSON)' \
		--dataset-name '$(S3_DATASET_NAME)' \
		--dataset-root '$(S3_DATASET_ROOT)' \
		--bucket '$(S3_BUCKET)' \
		--region '$(S3_REGION)' \
		--profile '$(S3_PROFILE)' \
		--endpoint-url '$(S3_ENDPOINT_URL)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' \
		--proxy-base-url '$(S3_PROXY_BASE_URL)' \
		--allowed-origin '$(S3_PROXY_ALLOWED_ORIGIN)' \
		--host '$(S3_PROXY_HOST)' \
		--port $(S3_PROXY_PORT) \
		--mode '$(S3_NGINX_MODE)' \
		--presign-expires $(S3_NGINX_PRESIGN_EXPIRES) \
		--output-conf '$(S3_NGINX_CONF)' \
		--map-output '$(S3_NGINX_MAP)' \
		--cache-dir '$(S3_NGINX_CACHE_DIR)' \
		--pid-path '$(S3_NGINX_PID)'

brand-s3-nginx-start: brand-s3-nginx-render-config ## 启动本地 Nginx 图片代理并启用本地缓存
	@if [ -f '$(S3_NGINX_PID)' ]; then \
		$(S3_NGINX_BIN) -c '$(S3_NGINX_CONF)' -s reload; \
	else \
		$(S3_NGINX_BIN) -c '$(S3_NGINX_CONF)'; \
	fi
	@printf "S3 Nginx 图片代理已启动：%s\n" "$(S3_PROXY_BASE_URL)"

brand-s3-nginx-reload: brand-s3-nginx-render-config ## 重新生成 Nginx 代理配置并 reload，适合刷新预签名 URL
	$(S3_NGINX_BIN) -c '$(S3_NGINX_CONF)' -s reload
	@printf "S3 Nginx 图片代理已重载：%s\n" "$(S3_PROXY_BASE_URL)"

brand-s3-nginx-stop: ## 停止本地 Nginx 图片代理
	@if [ -f '$(S3_NGINX_PID)' ]; then \
		$(S3_NGINX_BIN) -c '$(S3_NGINX_CONF)' -s quit; \
	else \
		echo "未找到 Nginx pid 文件：$(S3_NGINX_PID)"; \
	fi

brand-s3-ls-apply: ls-db-check prepare-dirs ## 将 S3/Nginx/proxy 图片任务导入 Label Studio
	cd $(LS_WORK_DIR) && printf 'exec(open("$(PROJECT_ROOT)/scripts/label_studio/apply_import.py", encoding="utf-8").read())\nexit()\n' | \
		LS_IMPORT_JSON='$(S3_LS_IMPORT_JSON)' \
		LS_LOCAL_FILES_PATH='$(PROJECT_ROOT)' \
		LS_PROJECT_TITLE='S3 Images $(S3_DATASET_NAME)' \
		LS_PROJECT_DESCRIPTION='S3 图片单类别标注项目；图片通过 S3 URL、本地 Nginx 或 Python 代理加载。' \
		LS_LOCAL_FILES_STORAGE_TITLE='S3 Images $(S3_DATASET_NAME)' \
		LS_LOCAL_FILES_STORAGE_DESCRIPTION='S3 image tasks do not depend on local image storage; this storage only satisfies Label Studio import permissions.' \
		LS_LABEL_CONFIG_XML='$(S3_LS_LABEL_CONFIG_XML)' \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

1-brand-s3-workflow-to-ls: brand-s3-upload-images brand-s3-nginx-start brand-s3-ls-import-json brand-s3-ls-apply ## 上传 S3、启动 Nginx 代理、生成并导入 Label Studio

brand-s3-ls-export: ls-db-check prepare-dirs ## 从 Label Studio 导出 S3 图片标注 JSON；需传 LS_PROJECT_ID=<项目ID>
	@[ -n "$(LS_PROJECT_ID)" ] || (echo "错误：请传入 LS_PROJECT_ID，例如：make brand-s3-ls-export LS_PROJECT_ID=2" && exit 1)
	mkdir -p '$(S3_LS_EXPORT_DIR)'
	cd $(LS_WORK_DIR) && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio export \
		--data-dir $(LS_DATA_DIR) \
		--export-path '$(S3_LS_EXPORT_PATH)' \
		$(LS_PROJECT_ID) $(LS_EXPORT_FORMAT)

brand-s3-ls-to-yolo: ## 将 S3 图片 Label Studio 导出转换为 YOLO 标签和 EC2 下载清单
	$(VENV_BIN)/python scripts/label_studio/export_s3_single_class_to_yolo.py \
		--config '$(BRAND_S3_CONFIG)' \
		--input '$(S3_LS_EXPORT_PATH)' \
		--output-root '$(S3_DATASET_ROOT)' \
		--dataset-name '$(S3_DATASET_NAME)' \
		--label-name '$(S3_LABEL_NAME)' \
		--data-yaml '$(S3_DATA_YAML)' \
		$(S3_LS_TO_YOLO_CLEAR_ARG) $(S3_LS_TO_YOLO_SKIP_EMPTY_ARG) \
		--report '$(S3_LS_TO_YOLO_REPORT)' \
		--ec2-manifest-json '$(S3_EC2_IMAGE_MANIFEST_JSON)' \
		--ec2-manifest-csv '$(S3_EC2_IMAGE_MANIFEST_CSV)'

2-brand-s3-workflow-after-ls: brand-s3-ls-export brand-s3-ls-to-yolo ## 导出 S3 图片标注并生成 YOLO 标签/EC2 图片清单

local-ls-s3-to-yolo: ## 将本地地址 LS 导出结合 S3 上传清单生成 YOLO 标签/EC2 图片清单
	$(VENV_BIN)/python scripts/label_studio/export_local_s3_to_yolo.py \
		--config '$(BRAND_S3_CONFIG)' \
		--input '$(LOCAL_LS_EXPORT_PATH)' \
		--s3-manifest '$(S3_MANIFEST_JSON)' \
		--output-root '$(S3_DATASET_ROOT)' \
		--dataset-name '$(S3_DATASET_NAME)' \
		--label-name '$(S3_LABEL_NAME)' \
		--local-images-dir '$(S3_LOCAL_IMAGES_DIR)' \
		--data-yaml '$(S3_DATA_YAML)' \
		$(S3_LS_TO_YOLO_CLEAR_ARG) $(S3_LS_TO_YOLO_SKIP_EMPTY_ARG) \
		--report '$(S3_LS_TO_YOLO_REPORT)' \
		--ec2-manifest-json '$(S3_EC2_IMAGE_MANIFEST_JSON)' \
		--ec2-manifest-csv '$(S3_EC2_IMAGE_MANIFEST_CSV)'

2-local-ls-s3-workflow-after-ls: local-dir-ls-export local-ls-s3-to-yolo ## 导出本地地址 LS 标注，并结合 S3 上传清单生成 EC2 图片清单

brand-s3-ec2-upload-manifest: ## 上传 S3 标签、EC2 图片清单和 YAML 到 EC2，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py upload-manifest \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--dataset-name '$(S3_DATASET_NAME)' --label-name '$(S3_LABEL_NAME)' \
		--dataset-root '$(S3_DATASET_ROOT)' --data-yaml '$(S3_DATA_YAML)' \
		--ec2-manifest-json '$(S3_EC2_IMAGE_MANIFEST_JSON)' \
		--ec2-manifest-csv '$(S3_EC2_IMAGE_MANIFEST_CSV)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' --download-mode '$(S3_EC2_DOWNLOAD_MODE)' \
		--remote-dataset-root '$(S3_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(S3_EC2_REMOTE_MANIFEST_JSON)' \
		--remote-manifest-csv '$(S3_EC2_REMOTE_MANIFEST_CSV)' \
		--train-name '$(S3_EC2_TRAIN_NAME)' \
		--remote-final-model '$(S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(S3_FINAL_MODEL)' \
		$(EC2_EXECUTE_ARG)

brand-s3-ec2-download-images: ## 在 EC2 上按 manifest 从 S3 下载训练图片，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py download-images \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--dataset-name '$(S3_DATASET_NAME)' --label-name '$(S3_LABEL_NAME)' \
		--dataset-root '$(S3_DATASET_ROOT)' --data-yaml '$(S3_DATA_YAML)' \
		--ec2-manifest-json '$(S3_EC2_IMAGE_MANIFEST_JSON)' \
		--ec2-manifest-csv '$(S3_EC2_IMAGE_MANIFEST_CSV)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' --download-mode '$(S3_EC2_DOWNLOAD_MODE)' \
		--remote-dataset-root '$(S3_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(S3_EC2_REMOTE_MANIFEST_JSON)' \
		--remote-manifest-csv '$(S3_EC2_REMOTE_MANIFEST_CSV)' \
		$(EC2_EXECUTE_ARG)

brand-s3-ec2-train: ## 在 EC2 下载 S3 图片并训练，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py train \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--dataset-name '$(S3_DATASET_NAME)' --label-name '$(S3_LABEL_NAME)' \
		--dataset-root '$(S3_DATASET_ROOT)' --data-yaml '$(S3_DATA_YAML)' \
		--ec2-manifest-json '$(S3_EC2_IMAGE_MANIFEST_JSON)' \
		--ec2-manifest-csv '$(S3_EC2_IMAGE_MANIFEST_CSV)' \
		--public-base-url '$(S3_PUBLIC_BASE_URL)' --download-mode '$(S3_EC2_DOWNLOAD_MODE)' \
		--remote-dataset-root '$(S3_EC2_REMOTE_DATASET_ROOT)' \
		--remote-data-yaml '$(S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(S3_EC2_REMOTE_MANIFEST_JSON)' \
		--remote-manifest-csv '$(S3_EC2_REMOTE_MANIFEST_CSV)' \
		--train-name '$(S3_EC2_TRAIN_NAME)' --base-model '$(EC2_BASE_MODEL)' \
		--remote-final-model '$(S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(S3_FINAL_MODEL)' \
		--epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) --batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(S3_EC2_ARTIFACT_ROOT)' --latest-run-file '$(S3_EC2_LATEST_RUN_FILE)' \
		$(EC2_RESUME_ARG) $(EC2_EXECUTE_ARG)

3-brand-s3-workflow-ec2-train: brand-s3-ec2-upload-manifest brand-s3-ec2-download-images brand-s3-ec2-train ## 上传 S3 训练清单到 EC2、下载 S3 图片并启动训练，默认 dry-run

brand-s3-ec2-evaluate: ## 归档 EC2 S3 数据集训练产物并生成评估摘要，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py evaluate \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' --python-cmd '$(EC2_PYTHON_CMD)' \
		--dataset-name '$(S3_DATASET_NAME)' --label-name '$(S3_LABEL_NAME)' \
		--dataset-root '$(S3_DATASET_ROOT)' --data-yaml '$(S3_DATA_YAML)' \
		--ec2-manifest-json '$(S3_EC2_IMAGE_MANIFEST_JSON)' \
		--remote-dataset-root '$(S3_EC2_REMOTE_DATASET_ROOT)' --remote-data-yaml '$(S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(S3_EC2_REMOTE_MANIFEST_JSON)' --train-name '$(S3_EC2_TRAIN_NAME)' \
		--base-model '$(EC2_BASE_MODEL)' --remote-final-model '$(S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(S3_FINAL_MODEL)' \
		--epochs $(EC2_TRAIN_EPOCHS) --imgsz $(EC2_TRAIN_IMGSZ) --batch $(EC2_TRAIN_BATCH) --device $(EC2_TRAIN_DEVICE) \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(S3_EC2_ARTIFACT_ROOT)' --latest-run-file '$(S3_EC2_LATEST_RUN_FILE)' \
		--notes '$(EC2_EVAL_NOTES)' $(EC2_EXECUTE_ARG)

brand-s3-ec2-download-artifacts: ## 下载 EC2 S3 数据集训练归档目录，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py download-artifacts \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--dataset-name '$(S3_DATASET_NAME)' --label-name '$(S3_LABEL_NAME)' \
		--dataset-root '$(S3_DATASET_ROOT)' --data-yaml '$(S3_DATA_YAML)' \
		--ec2-manifest-json '$(S3_EC2_IMAGE_MANIFEST_JSON)' \
		--remote-dataset-root '$(S3_EC2_REMOTE_DATASET_ROOT)' --remote-data-yaml '$(S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(S3_EC2_REMOTE_MANIFEST_JSON)' --train-name '$(S3_EC2_TRAIN_NAME)' \
		--remote-final-model '$(S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(S3_FINAL_MODEL)' \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(S3_EC2_ARTIFACT_ROOT)' \
		--local-artifact-root '$(S3_EC2_LOCAL_ARTIFACT_ROOT)' $(EC2_EXECUTE_ARG)

brand-s3-ec2-download-model: ## 下载 EC2 S3 数据集 best.pt，默认 dry-run
	$(VENV_BIN)/python scripts/ec2/s3_workflow.py download-model \
		--host '$(EC2_HOST)' --user '$(EC2_USER)' --port $(EC2_PORT) $(EC2_KEY_ARG) \
		--ec2-project-root '$(EC2_PROJECT_ROOT)' --activate-cmd '$(EC2_ACTIVATE_CMD)' \
		--dataset-name '$(S3_DATASET_NAME)' --label-name '$(S3_LABEL_NAME)' \
		--dataset-root '$(S3_DATASET_ROOT)' --data-yaml '$(S3_DATA_YAML)' \
		--ec2-manifest-json '$(S3_EC2_IMAGE_MANIFEST_JSON)' \
		--remote-dataset-root '$(S3_EC2_REMOTE_DATASET_ROOT)' --remote-data-yaml '$(S3_EC2_REMOTE_DATA_YAML)' \
		--remote-manifest-json '$(S3_EC2_REMOTE_MANIFEST_JSON)' --train-name '$(S3_EC2_TRAIN_NAME)' \
		--remote-final-model '$(S3_EC2_REMOTE_FINAL_MODEL)' --local-model '$(S3_FINAL_MODEL)' \
		--run-name '$(EC2_RUN_NAME)' --artifact-root '$(S3_EC2_ARTIFACT_ROOT)' \
		$(EC2_EXECUTE_ARG)
