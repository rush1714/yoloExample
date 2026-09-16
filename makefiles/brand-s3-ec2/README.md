# brand-s3-ec2：S3 训练图片 + Label Studio + EC2 流程

该流程用于把本地图片目录上传到 S3，Label Studio 标注时直接使用 S3 图片地址，并在 EC2 训练前再由 EC2 从 S3 下载训练图片。它解决两类问题：

1. 本地不再反复复制/同步大量训练图片到 EC2。
2. 没有 AWS S3 CORS 配置权限时，Label Studio 可通过本地只读代理加载 S3 图片。

## 目录约定

```text
datasets/s3/<S3_DATASET_NAME>/
├── metadata/
│   ├── s3_images.json
│   ├── s3_images.csv
│   ├── s3_download_urls.txt
│   ├── ec2_image_manifest.json
│   ├── ec2_image_manifest.csv
│   └── label_studio_to_yolo_report.json
├── label_studio/
│   ├── s3_label_studio_import.json
│   ├── label_config.xml
│   └── exports/label_studio_export.json
└── labels/{train,val,test}/
```

注意：本地 `datasets/s3/<name>/images/` 默认不生成，也不要求存在；EC2 会在训练前按 manifest 下载图片到远端 `images/{train,val,test}`。

## 配置

复制示例配置后填写真实参数：

```bash
cp config/brand_s3_ec2.example.yaml config/brand_s3_ec2.local.yaml
```

`config/brand_s3_ec2.local.yaml` 已加入 `.gitignore`，不要提交。建议不要把 AWS access key/secret 写进配置文件：

- 本地上传：使用 `AWS_PROFILE`、`aws configure` 或环境变量。
- EC2 下载：优先使用 EC2 IAM Role；也可在远端配置 AWS profile/环境变量。

常用 Make 参数：

| 变量 | 说明 | 示例 |
|---|---|---|
| `BRAND_S3_CONFIG` | S3 流程配置文件 | `config/brand_s3_ec2.local.yaml` |
| `S3_DATASET_NAME` | 数据集短名称 | `ci_20260916_01` |
| `S3_LABEL_NAME` | 单类别标签名 | `diaper` |
| `S3_LOCAL_IMAGES_DIR` | 本地待上传图片目录 | `/Users/you/images` |
| `S3_BUCKET` | S3 桶名 | `my-yolo-bucket` |
| `S3_PREFIX` | S3 业务对象前缀；实际上传自动归入 `yolo-training/<S3_PREFIX>` | `ci_20260916_01` |
| `S3_REGION` | S3 区域 | `ap-southeast-1` |
| `S3_PROFILE` | 本机 AWS profile，可为空 | `default` |
| `S3_IMAGE_URL_MODE` | LS 图片地址模式：`proxy`/`https`/`s3` | `proxy` |
| `S3_PROXY_PORT` | 本地图片代理端口 | `3010` |
| `EC2_EXECUTE` | 是否真实执行 EC2 SSH/rsync | `0` / `1` |

## 推荐流程

### 0. 检查参数

```bash
make brand-s3-check-config \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_BUCKET=<bucket> \
  S3_PREFIX=ci_20260916_01
```

### 1. 上传本地图片到 S3

先 dry-run 验证扫描范围：

```bash
make brand-s3-upload-images \
  S3_DRY_RUN=1 \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LOCAL_IMAGES_DIR=/path/to/images \
  S3_BUCKET=<bucket> \
  S3_PREFIX=ci_20260916_01
```

确认无误后真实上传：

```bash
make brand-s3-upload-images \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LOCAL_IMAGES_DIR=/path/to/images \
  S3_BUCKET=<bucket> \
  S3_PREFIX=ci_20260916_01
```

输出：

- `datasets/s3/<name>/metadata/s3_images.json`
- `datasets/s3/<name>/metadata/s3_images.csv`
- `datasets/s3/<name>/metadata/s3_download_urls.txt`

### 2. 启动本地 S3 图片代理

如果桶是私有的、或者没有权限配置 S3 CORS，请使用默认 proxy 模式：

```bash
make brand-s3-proxy-start \
  S3_BUCKET=<bucket> \
  S3_REGION=ap-southeast-1
```

保持该命令运行，然后打开 Label Studio。代理默认地址：`http://127.0.0.1:3010`。

### 3. 生成并导入 Label Studio

```bash
make brand-s3-ls-import-json \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LABEL_NAME=diaper

make brand-s3-ls-apply \
  S3_DATASET_NAME=ci_20260916_01
```

也可以使用一键命令：

```bash
make 1-brand-s3-workflow-to-ls \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LABEL_NAME=diaper \
  S3_LOCAL_IMAGES_DIR=/path/to/images \
  S3_BUCKET=<bucket> \
  S3_PREFIX=ci_20260916_01
```

> 注意：proxy 模式下，一键命令不会自动在后台托管长期代理。标注时请另开终端运行 `make brand-s3-proxy-start ...`。

### 4. 标注后生成 YOLO labels 和 EC2 图片清单

```bash
make 2-brand-s3-workflow-after-ls \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LABEL_NAME=diaper \
  LS_PROJECT_ID=<项目ID> \
  S3_LS_TO_YOLO_CLEAR=1
```

该步骤不会下载图片，只生成：

- `labels/{train,val,test}/*.txt`
- `metadata/ec2_image_manifest.json`
- `metadata/ec2_image_manifest.csv`
- `config/generated/s3_<S3_DATASET_NAME>.yaml`

### 5. 上传 manifest/labels/YAML 到 EC2

默认只打印命令，不执行：

```bash
make brand-s3-ec2-upload-manifest \
  S3_DATASET_NAME=ci_20260916_01 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem
```

确认后执行：

```bash
make brand-s3-ec2-upload-manifest \
  S3_DATASET_NAME=ci_20260916_01 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_EXECUTE=1
```

### 6. EC2 从 S3 下载图片

```bash
make brand-s3-ec2-download-images \
  S3_DATASET_NAME=ci_20260916_01 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_EXECUTE=1
```

该命令在 EC2 上读取 `metadata/ec2_image_manifest.json`，把图片下载到：

```text
datasets/s3/<S3_DATASET_NAME>/images/{train,val,test}/
```

### 7. EC2 训练、评估和下载

EC2 训练不再使用固定档位命令，训练规模统一写成模型参数。`EC2_RUN_NAME` 只决定远端/本地模型和归档目录名，模型大小、轮数、图片尺寸由 `EC2_BASE_MODEL`、`EC2_TRAIN_EPOCHS`、`EC2_TRAIN_IMGSZ` 等参数决定。

```bash
make brand-s3-ec2-train \
  S3_DATASET_NAME=ci_20260916_01 \
  EC2_BASE_MODEL=yolo26m.pt \
  EC2_TRAIN_EPOCHS=100 \
  EC2_TRAIN_IMGSZ=960 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_EXECUTE=1

make brand-s3-ec2-evaluate \
  S3_DATASET_NAME=ci_20260916_01 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_EXECUTE=1

make brand-s3-ec2-download-artifacts \
  S3_DATASET_NAME=ci_20260916_01 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_EXECUTE=1

make brand-s3-ec2-download-model \
  S3_DATASET_NAME=ci_20260916_01 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_EXECUTE=1
```

## Web 控制台

启动：

```bash
make web-console
```

打开 `http://localhost:3000`，左侧选择“图片来源 / 标注准备 → 本地目录 → S3 → LS”或“EC2 训练 / 推理 / 下载 → S3 图片数据集 → EC2”。EC2 相关命令默认 dry-run，需要在页面中把 `EC2_EXECUTE` 改成 `1` 才会真实连接远端。

## CORS 说明

如果没有权限修改 AWS S3 CORS，请不要使用 `S3_IMAGE_URL_MODE=https` 直连私有或无 CORS 的对象。默认 `proxy` 模式由本地代理读取 S3 对象并加上 CORS 响应头，Label Studio 只访问本机 `http://127.0.0.1:3010/image?...`。

## 命令示例索引

| 命令 | 作用 | 示例 |
|---|---|---|
| `brand-s3-check-config` | 检查 S3 工作流关键参数 | `make brand-s3-check-config S3_DATASET_NAME=ci_20260916_01 S3_BUCKET=<bucket> S3_PREFIX=ci_20260916_01` |
| `brand-s3-upload-images` | 上传本地图片目录到 S3 并生成图片地址清单；S3_DRY_RUN=1 只生成清单 | `make brand-s3-upload-images S3_DATASET_NAME=ci_20260916_01 S3_LOCAL_IMAGES_DIR=/path/to/images S3_BUCKET=<bucket> S3_PREFIX=ci_20260916_01` |
| `brand-s3-ls-import-json` | 根据 S3 图片清单生成 Label Studio 导入 JSON 和标签配置 | `make brand-s3-ls-import-json S3_DATASET_NAME=ci_20260916_01 S3_LABEL_NAME=diaper` |
| `brand-s3-proxy-start` | 启动本地 S3 图片代理，供 Label Studio 加载私有桶图片 | `make brand-s3-proxy-start S3_BUCKET=<bucket> S3_REGION=ap-southeast-1` |
| `brand-s3-ls-apply` | 将 S3/proxy 图片任务导入 Label Studio | `make brand-s3-ls-apply S3_DATASET_NAME=ci_20260916_01` |
| `1-brand-s3-workflow-to-ls` | 上传 S3、生成并导入 Label Studio | `make 1-brand-s3-workflow-to-ls S3_DATASET_NAME=ci_20260916_01 S3_LOCAL_IMAGES_DIR=/path/to/images S3_BUCKET=<bucket>` |
| `brand-s3-ls-export` | 从 Label Studio 导出 S3 图片标注 JSON；需传 LS_PROJECT_ID=<项目ID> | `make brand-s3-ls-export S3_DATASET_NAME=ci_20260916_01 LS_PROJECT_ID=<项目ID>` |
| `brand-s3-ls-to-yolo` | 将 S3 图片 Label Studio 导出转换为 YOLO 标签和 EC2 下载清单 | `make brand-s3-ls-to-yolo S3_DATASET_NAME=ci_20260916_01 S3_LABEL_NAME=diaper S3_LS_TO_YOLO_CLEAR=1` |
| `2-brand-s3-workflow-after-ls` | 导出 S3 图片标注并生成 YOLO 标签/EC2 图片清单 | `make 2-brand-s3-workflow-after-ls S3_DATASET_NAME=ci_20260916_01 LS_PROJECT_ID=<项目ID> S3_LS_TO_YOLO_CLEAR=1` |
| `brand-s3-ec2-upload-manifest` | 上传 S3 标签、EC2 图片清单和 YAML 到 EC2，默认 dry-run | `make brand-s3-ec2-upload-manifest S3_DATASET_NAME=ci_20260916_01 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-download-images` | 在 EC2 上按 manifest 从 S3 下载训练图片，默认 dry-run | `make brand-s3-ec2-download-images S3_DATASET_NAME=ci_20260916_01 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-train` | 在 EC2 下载 S3 图片并训练，默认 dry-run | `make brand-s3-ec2-train S3_DATASET_NAME=ci_20260916_01 EC2_BASE_MODEL=yolo26m.pt EC2_TRAIN_EPOCHS=100 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-evaluate` | 归档 EC2 S3 数据集训练产物并生成评估摘要，默认 dry-run | `make brand-s3-ec2-evaluate S3_DATASET_NAME=ci_20260916_01 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-download-artifacts` | 下载 EC2 S3 数据集训练归档目录，默认 dry-run | `make brand-s3-ec2-download-artifacts S3_DATASET_NAME=ci_20260916_01 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-download-model` | 下载 EC2 S3 数据集 best.pt，默认 dry-run | `make brand-s3-ec2-download-model S3_DATASET_NAME=ci_20260916_01 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
