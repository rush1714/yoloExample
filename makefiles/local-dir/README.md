# 本地目录图片导入 / 标注 / EC2 衔接

本目录负责“图片已经在本机目录中”的流程：扫描本地目录、导入 Label Studio、人工标注后转 YOLO，以及把转换后的 YOLO 数据集上传到 EC2 训练。

## 本地标注闭环

```bash
make 1-local-dir-workflow-to-ls \
  LOCAL_IMAGES_DIR=/path/to/images \
  LOCAL_DATASET_NAME=my_images_v1 \
  LOCAL_LABEL_NAME=diaper

make 2-local-dir-workflow-after-ls \
  LOCAL_DATASET_NAME=my_images_v1 \
  LOCAL_LABEL_NAME=diaper \
  LS_PROJECT_ID=<项目ID> \
  LOCAL_LS_TO_YOLO_CLEAR=1
```

`LOCAL_DATASET_NAME` 只能是短名称；如果要改变输出目录，请使用 `LOCAL_DATASET_ROOT=/path/to/output`。

## EC2 训练

不再提供固定档位预设命令。训练规模统一通过显式模型参数控制：

```bash
make local-dir-ec2-upload-data \
  LOCAL_DATASET_NAME=my_images_v1 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem

make local-dir-ec2-train \
  LOCAL_DATASET_NAME=my_images_v1 \
  EC2_BASE_MODEL=yolo26m.pt \
  EC2_TRAIN_EPOCHS=100 \
  EC2_TRAIN_IMGSZ=960 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem

make local-dir-ec2-evaluate \
  LOCAL_DATASET_NAME=my_images_v1 \
  EC2_RUN_NAME=yolo26m_img960_e100
make local-dir-ec2-download-artifacts \
  LOCAL_DATASET_NAME=my_images_v1 \
  EC2_RUN_NAME=yolo26m_img960_e100
make local-dir-ec2-download-model \
  LOCAL_DATASET_NAME=my_images_v1 \
  EC2_RUN_NAME=yolo26m_img960_e100
```

所有 EC2 命令默认 dry-run，确认命令无误后才加 `EC2_EXECUTE=1`。

## 命令示例索引

| 命令 | 作用 | 示例 |
|---|---|---|
| `local-dir-check` | 检查本地目录导入参数，避免把路径误填到 LOCAL_DATASET_NAME | `make local-dir-check LOCAL_DATASET_NAME=my_images_v1` |
| `local-dir-yaml` | 生成本地目录单类别 YOLO YAML | `make local-dir-yaml LOCAL_DATASET_NAME=my_images_v1 LOCAL_LABEL_NAME=diaper` |
| `local-dir-ls-import-json` | 扫描本地图片目录并生成单类别 Label Studio 导入 JSON | `make local-dir-ls-import-json LOCAL_IMAGES_DIR=/path/to/images LOCAL_DATASET_NAME=my_images_v1 LOCAL_LABEL_NAME=diaper` |
| `local-dir-ls-apply` | 将本地目录图片任务导入 Label Studio（每执行一次创建新项目） | `make local-dir-ls-apply LOCAL_IMAGES_DIR=/path/to/images LOCAL_DATASET_NAME=my_images_v1 LOCAL_LABEL_NAME=diaper` |
| `1-local-dir-workflow-to-ls` | 扫描本地目录并导入 Label Studio | `make 1-local-dir-workflow-to-ls LOCAL_IMAGES_DIR=/path/to/images LOCAL_DATASET_NAME=my_images_v1 LOCAL_LABEL_NAME=diaper` |
| `local-dir-ls-export` | 从 Label Studio 导出本地目录标注 JSON；需传 LS_PROJECT_ID=<项目ID> | `make local-dir-ls-export LOCAL_DATASET_NAME=my_images_v1 LS_PROJECT_ID=<项目ID>` |
| `local-dir-ls-to-yolo` | 将本地目录 Label Studio 导出转换为 YOLO 训练集 | `make local-dir-ls-to-yolo LOCAL_DATASET_NAME=my_images_v1 LOCAL_LABEL_NAME=diaper LOCAL_LS_TO_YOLO_CLEAR=1` |
| `2-local-dir-workflow-after-ls` | 导出本地目录标注并转换 YOLO 训练集 | `make 2-local-dir-workflow-after-ls LOCAL_DATASET_NAME=my_images_v1 LOCAL_LABEL_NAME=diaper LS_PROJECT_ID=<项目ID> LOCAL_LS_TO_YOLO_CLEAR=1` |
| `local-dir-ec2-upload-data` | 上传本地目录 YOLO 数据集到 EC2（默认 dry-run；EC2_EXECUTE=1 才执行） | `make local-dir-ec2-upload-data LOCAL_DATASET_NAME=my_images_v1 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `local-dir-ec2-train` | 在 EC2 训练本地目录数据集（默认 dry-run；训练规模由 EC2_* 参数控制） | `make local-dir-ec2-train LOCAL_DATASET_NAME=my_images_v1 EC2_BASE_MODEL=yolo26m.pt EC2_TRAIN_EPOCHS=100 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `local-dir-ec2-evaluate` | 归档 EC2 本地目录训练产物并生成评估摘要（默认 dry-run） | `make local-dir-ec2-evaluate LOCAL_DATASET_NAME=my_images_v1 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `local-dir-ec2-download-artifacts` | 下载 EC2 本地目录训练归档目录（默认 dry-run） | `make local-dir-ec2-download-artifacts LOCAL_DATASET_NAME=my_images_v1 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `local-dir-ec2-download-model` | 下载 EC2 本地目录训练 best.pt（默认 dry-run） | `make local-dir-ec2-download-model LOCAL_DATASET_NAME=my_images_v1 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
