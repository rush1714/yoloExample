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
	@printf "EC2_EXECUTE=%s\n" "$(EC2_EXECUTE)"
