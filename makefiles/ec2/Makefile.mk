# EC2 公共连接、训练参数与 dry-run 开关。
# 具体数据来源流程只保留自己的 upload/train/evaluate/download 目标。

# EC2 地址或 SSH Host 别名；默认值用于本地 dry-run 预览，真实执行前请覆盖。
EC2_HOST ?= 3.232.95.101
# EC2 SSH 用户。
EC2_USER ?= ec2-user
# SSH 私钥路径；为空时不传 -i。
EC2_KEY ?= ~/.ssh/smdp-yolo-gpu-key.pem
# SSH 端口。
EC2_PORT ?= 22
# EC2 上项目根目录。
EC2_PROJECT_ROOT ?= /home/$(EC2_USER)/yoloExample
# EC2 上执行训练/推理前激活环境。
EC2_ACTIVATE_CMD ?= source /opt/pytorch/bin/activate
# EC2 上 Python 执行命令。
EC2_PYTHON_CMD ?= python3
# EC2 训练使用的基座模型；需要不同模型时直接覆盖本参数。
EC2_BASE_MODEL ?= yolo26m.pt
# EC2 训练轮数。
EC2_TRAIN_EPOCHS ?= 100
# EC2 训练/推理图片尺寸。
EC2_TRAIN_IMGSZ ?= 960
# EC2 训练 batch；-1 交给 Ultralytics 自动估算。
EC2_TRAIN_BATCH ?= -1
# EC2 训练/推理设备；CUDA 单卡一般为 0。
EC2_TRAIN_DEVICE ?= 0
# 运行标识只用于模型、归档和报告目录；训练规模由上面的显式模型参数决定。
EC2_RUN_NAME ?= $(basename $(notdir $(EC2_BASE_MODEL)))_img$(EC2_TRAIN_IMGSZ)_e$(EC2_TRAIN_EPOCHS)
# 评估摘要备注。
EC2_EVAL_NOTES ?= training start
# EC2 批量推理输入清单，支持 s3://、http(s):// 或 EC2 本地 txt/csv/json/xlsx 文件。
EC2_PREDICT_MANIFEST_SOURCE ?=
# 本地待上传到 EC2 的批量推理清单；推荐 Excel/CSV/JSON/TXT 用这个参数。
EC2_PREDICT_LOCAL_MANIFEST ?=
# 本地清单上传到 EC2 后的远端路径；留空时自动放到 EC2_PREDICT_WORK_DIR/manifest/。
EC2_PREDICT_REMOTE_MANIFEST ?=
# EC2 批量推理结果上传目录，必须是 s3://bucket/prefix。
EC2_PREDICT_OUTPUT_S3_URI ?=
# EC2 推理使用的模型；留空时各流程默认使用对应训练产物 best.pt。
EC2_PREDICT_MODEL ?=
# CSV/Excel/JSON 清单中的图片地址列名；留空时自动扫描。
EC2_PREDICT_INPUT_COLUMN ?=
# EC2 本地推理工作目录；留空时由具体流程按数据集和运行名分层。
EC2_PREDICT_WORK_DIR ?=
# EC2 推理置信度阈值。
EC2_PREDICT_CONF ?= 0.35
# EC2 推理图片尺寸。
EC2_PREDICT_IMGSZ ?= $(EC2_TRAIN_IMGSZ)
# EC2 推理数量上限；0 表示全量。
EC2_PREDICT_LIMIT ?= 0
# 是否在下载 EC2 推理结果时同步下载原始推理图片。
EC2_PREDICT_DOWNLOAD_SOURCE_IMAGES ?= 1
# HTTP(S) 原始推理图片下载超时秒数，避免单张图片长时间卡住。
EC2_PREDICT_SOURCE_DOWNLOAD_TIMEOUT ?= 30
# 本地下载 EC2 推理结果和原始图片的并发数。
EC2_PREDICT_DOWNLOAD_WORKERS ?= 8
# 本地推理结果下载目录；留空时由具体流程按数据集和运行名分层。
EC2_PREDICT_LOCAL_RESULT_ROOT ?=
# 本地原始推理图片下载目录；留空时由具体流程放到 datasets/.../predict/images。
EC2_PREDICT_LOCAL_SOURCE_IMAGE_ROOT ?=
EC2_PREDICT_DOWNLOAD_SOURCE_IMAGES_ARG := $(if $(filter 1 true yes,$(EC2_PREDICT_DOWNLOAD_SOURCE_IMAGES)),--download-source-images,)
# 真实执行开关：默认只打印 SSH/rsync 命令，传 EC2_EXECUTE=1 才连接远端。
EC2_EXECUTE ?= 0
EC2_EXECUTE_ARG := $(if $(filter 1 true yes,$(EC2_EXECUTE)),--execute,)
EC2_KEY_ARG := $(if $(EC2_KEY),--key $(EC2_KEY),)
EC2_RESUME_ARG := $(if $(filter 1 true yes,$(TRAIN_RESUME)),--resume,)

.PHONY: ec2-print-params

ec2-print-params: ## 显示 EC2 公共连接与训练参数
	@printf "EC2_HOST=%s\n" "$(EC2_HOST)"
	@printf "EC2_USER=%s\n" "$(EC2_USER)"
	@printf "EC2_PORT=%s\n" "$(EC2_PORT)"
	@printf "EC2_PROJECT_ROOT=%s\n" "$(EC2_PROJECT_ROOT)"
	@printf "EC2_BASE_MODEL=%s\n" "$(EC2_BASE_MODEL)"
	@printf "EC2_TRAIN_EPOCHS=%s\n" "$(EC2_TRAIN_EPOCHS)"
	@printf "EC2_TRAIN_IMGSZ=%s\n" "$(EC2_TRAIN_IMGSZ)"
	@printf "EC2_TRAIN_BATCH=%s\n" "$(EC2_TRAIN_BATCH)"
	@printf "EC2_TRAIN_DEVICE=%s\n" "$(EC2_TRAIN_DEVICE)"
	@printf "EC2_RUN_NAME=%s\n" "$(EC2_RUN_NAME)"
	@printf "EC2_PREDICT_MANIFEST_SOURCE=%s\n" "$(EC2_PREDICT_MANIFEST_SOURCE)"
	@printf "EC2_PREDICT_LOCAL_MANIFEST=%s\n" "$(EC2_PREDICT_LOCAL_MANIFEST)"
	@printf "EC2_PREDICT_OUTPUT_S3_URI=%s\n" "$(EC2_PREDICT_OUTPUT_S3_URI)"
	@printf "EC2_PREDICT_MODEL=%s\n" "$(EC2_PREDICT_MODEL)"
	@printf "EC2_PREDICT_CONF=%s\n" "$(EC2_PREDICT_CONF)"
	@printf "EC2_PREDICT_IMGSZ=%s\n" "$(EC2_PREDICT_IMGSZ)"
	@printf "EC2_PREDICT_LIMIT=%s\n" "$(EC2_PREDICT_LIMIT)"
	@printf "EC2_PREDICT_SOURCE_DOWNLOAD_TIMEOUT=%s\n" "$(EC2_PREDICT_SOURCE_DOWNLOAD_TIMEOUT)"
	@printf "EC2_PREDICT_DOWNLOAD_WORKERS=%s\n" "$(EC2_PREDICT_DOWNLOAD_WORKERS)"
	@printf "EC2_EXECUTE=%s\n" "$(EC2_EXECUTE)"
