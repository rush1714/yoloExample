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
| `S3_UPLOAD_WORKERS` | 并发上传线程数；断点续传会跳过已成功上传图片 | `8` |
| `S3_REGION` | S3 区域 | `ap-southeast-1` |
| `S3_PROFILE` | 本机 AWS profile，可为空 | `default` |
| `S3_IMAGE_URL_MODE` | LS 图片地址模式：`nginx`/`proxy`/`https`/`s3` | `nginx` |
| `S3_PROXY_BACKEND` | `brand-s3-proxy-start` 使用的后端：`nginx` 或旧 `python` | `nginx` |
| `S3_NGINX_MODE` | Nginx 回源模式：私有桶用 `presign`，公开桶可用 `direct` | `presign` |
| `S3_NGINX_PRESIGN_EXPIRES` | 预签名 URL 有效秒数；到期前 reload 刷新 | `604800` |
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

先 dry-run 验证扫描范围；脚本会读取已有 `s3_images.json`，跳过 `relative_path + s3_key + size_bytes` 一致且已成功上传的图片：

```bash
make brand-s3-upload-images \
  S3_DRY_RUN=1 \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LOCAL_IMAGES_DIR=/path/to/images \
  S3_BUCKET=<bucket> \
  S3_PREFIX=ci_20260916_01 \
  S3_UPLOAD_WORKERS=8
```

确认无误后真实上传：

```bash
make brand-s3-upload-images \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LOCAL_IMAGES_DIR=/path/to/images \
  S3_BUCKET=<bucket> \
  S3_PREFIX=ci_20260916_01 \
  S3_UPLOAD_WORKERS=8
```

输出：

- `datasets/s3/<name>/metadata/s3_images.json`
- `datasets/s3/<name>/metadata/s3_images.csv`
- `datasets/s3/<name>/metadata/s3_download_urls.txt`

这里的 `s3_images.json/csv` 是“上传与 Label Studio 导入清单”，记录全量上传图片及其 S3/HTTPS/Nginx/proxy 地址；它不是 EC2 训练下载清单。

如果旧上传进程已经上传了一部分但本地没有新清单，可先从 S3 目标目录反查对象并生成可续传清单：

```bash
make brand-s3-sync-manifest-from-s3 \
  S3_DATASET_NAME=GH_2026_09_15 \
  S3_LOCAL_IMAGES_DIR=datasets/diaper_category/GH/v2026-09-15/raw/images \
  S3_BUCKET=uat-smdp4cust-bak \
  S3_PREFIX=GH/2026_09_15/images \
  S3_REGION=af-south-1 \
  S3_PROFILE=smdp-yolo
```

该命令会写出 `s3_images.json|csv|txt`，其中 S3 上已存在且大小匹配的对象会标记为 `uploaded=true` / `status=s3_existing`，后续再执行 `brand-s3-upload-images` 会直接跳过。

### 2. 启动本地 S3 图片代理

默认代理后端已经切换为 Nginx。私有桶使用 `presign` 模式时，启动命令会先根据 `s3_images.json` 生成本地短 URL 到 S3 预签名 URL 的映射，再由 Nginx 负责转发和本地缓存；图片请求不再逐张经过 Python。

```bash
make brand-s3-proxy-start \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_BUCKET=<bucket> \
  S3_REGION=ap-southeast-1 \
  S3_PROFILE=<profile> \
  S3_NGINX_MODE=presign
```

代理默认地址：`http://127.0.0.1:3010`。预签名 URL 默认 7 天有效，接近过期时执行：

```bash
make brand-s3-nginx-reload S3_DATASET_NAME=ci_20260916_01 S3_BUCKET=<bucket> S3_PROFILE=<profile>
```

如果对象已经公开可读，可改用 `S3_NGINX_MODE=direct`。如果本机未安装 Nginx，可临时回退旧 Python 代理：`make brand-s3-proxy-start S3_PROXY_BACKEND=python ...`。

### 3. 生成并导入 Label Studio

```bash
make brand-s3-ls-import-json \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LABEL_NAME=diaper \
  S3_IMAGE_URL_MODE=nginx

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
  S3_PREFIX=ci_20260916_01 \
  S3_UPLOAD_WORKERS=8
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

这里的 `ec2_image_manifest.json/csv` 是“EC2 训练下载清单”，只包含标注转换后进入训练集的图片，并带有 `split`、`training_image_name`、`label_path`、`box_count` 等训练字段。后续 `brand-s3-ec2-upload-manifest` 会把 `ec2_image_manifest.json` 和 `ec2_image_manifest.csv` 都上传到 EC2；EC2 下载/训练实际读取的是 JSON 文件。

### 5. 兼容路径：本地 LS 标注后生成 S3 EC2 训练清单

如果你的流程是“本地图片导入 Label Studio 标注”，LS 导出里的图片仍是 `/data/local-files/?d=...` 本地地址；之后再把同一批图片上传到 S3，那么不要使用 `2-brand-s3-workflow-after-ls`。该命令只适合 LS 导出里已经带有 `s3_bucket` / `s3_key` 的 S3 导入项目。

这种情况下先确保已经有 S3 上传清单：

```text
datasets/s3/<S3_DATASET_NAME>/metadata/s3_images.json
```

然后用本地 LS 导出 JSON 与 `s3_images.json` 做匹配，生成 EC2 训练需要的 labels 和 manifest：

```bash
make local-ls-s3-to-yolo \
  LOCAL_LS_EXPORT_PATH=/path/to/local_label_studio_export.json \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LABEL_NAME=diaper \
  S3_LOCAL_IMAGES_DIR=/path/to/original/images \
  S3_MANIFEST_JSON=datasets/s3/ci_20260916_01/metadata/s3_images.json \
  S3_LS_TO_YOLO_CLEAR=1
```

如果还没有从本地目录 Label Studio 项目导出，也可以一键导出并转换：

```bash
make 2-local-ls-s3-workflow-after-ls \
  LOCAL_DATASET_NAME=<本地LS数据集名> \
  LS_PROJECT_ID=<项目ID> \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LABEL_NAME=diaper \
  S3_LOCAL_IMAGES_DIR=/path/to/original/images \
  S3_LS_TO_YOLO_CLEAR=1
```

如果同一批数据拆成多个 Label Studio 项目，可以直接让 `LS_PROJECT_ID` 使用英文逗号分隔多个项目 ID；命令会按顺序导出、只保留有有效框的任务、去重合并后再匹配 S3 上传清单：

```bash
make 2-local-ls-s3-merge-workflow-after-ls \
  LS_PROJECT_ID=21,20 \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_LABEL_NAME=diaper \
  S3_LOCAL_IMAGES_DIR=/path/to/original/images \
  S3_MANIFEST_JSON=datasets/s3/ci_20260916_01/metadata/s3_images.json \
  S3_LS_TO_YOLO_CLEAR=1
```

如只想先导出合并、不生成 YOLO/S3 EC2 清单，可执行：

```bash
make local-ls-s3-merge-projects LS_PROJECT_ID=21,20 S3_LABEL_NAME=diaper
```

匹配顺序为：本地绝对路径 `local_path` → `relative_path` → 文件名 `image_name`。如果仅文件名匹配但有重复文件名，脚本会跳过该任务并写入 warning，避免把标注错误绑定到其他 S3 图片。

### 6. 上传 manifest/labels/YAML 到 EC2

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

### 7. EC2 从 S3 下载图片

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

EC2 图片下载支持三种模式：

| 模式 | 说明 |
|---|---|
| `auto` | 默认值，优先使用 manifest 中的 `source_url` / `https_url` / `public_url` 或 `S3_PUBLIC_BASE_URL` 拼出的公共 URL；没有公共 URL 时回退 boto3。 |
| `public` | 强制使用公共 HTTP(S) URL 下载，不需要 EC2 配置 AWS credentials；没有公共 URL 或 URL 返回 403 时会直接失败。 |
| `boto3` | 使用 AWS SDK `download_file` 下载，需要 EC2 IAM Role 或 AWS credentials。 |

如果桶对象可以通过公共地址访问，推荐显式传：

```bash
make brand-s3-ec2-download-images \
  S3_DATASET_NAME=ci_20260916_01 \
  S3_PUBLIC_BASE_URL=https://uat-smdp4cust-bak.s3.af-south-1.amazonaws.com \
  S3_EC2_DOWNLOAD_MODE=public \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_EXECUTE=1
```

### 8. EC2 训练、评估和下载

EC2 训练不再使用固定档位命令，训练规模统一写成模型参数。`EC2_RUN_NAME` 只决定远端/本地模型和归档目录名，模型大小、轮数、图片尺寸由 `EC2_BASE_MODEL`、`EC2_TRAIN_EPOCHS`、`EC2_TRAIN_IMGSZ` 等参数决定。

如果已经完成步骤 4 或步骤 5，可以直接使用一键命令按顺序执行“上传 EC2 manifest/labels/YAML → EC2 下载 S3 图片 → EC2 训练”：

```bash
make 3-brand-s3-workflow-ec2-train \
  S3_DATASET_NAME=ci_20260916_01 \
  EC2_BASE_MODEL=yolo26m.pt \
  EC2_TRAIN_EPOCHS=100 \
  EC2_TRAIN_IMGSZ=960 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_EXECUTE=1
```

也可以分步执行，便于单独查看每一步日志：

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

如果没有权限修改 AWS S3 CORS，请不要使用 `S3_IMAGE_URL_MODE=https` 直连私有或无 CORS 的对象。默认 `nginx` 模式由本地 Nginx 代理读取 S3 对象、加上 CORS 响应头并启用本地缓存，Label Studio 只访问本机 `http://127.0.0.1:3010/image/<dataset>/<hash>.<ext>`。私有桶的 `presign` 映射有有效期，到期前执行 `brand-s3-nginx-reload` 刷新。

## 命令示例索引

| 命令 | 作用 | 示例 |
|---|---|---|
| `brand-s3-check-config` | 检查 S3 工作流关键参数 | `make brand-s3-check-config S3_DATASET_NAME=ci_20260916_01 S3_BUCKET=<bucket> S3_PREFIX=ci_20260916_01` |
| `brand-s3-upload-images` | 上传本地图片目录到 S3 并生成图片地址清单；S3_DRY_RUN=1 只生成清单 | `make brand-s3-upload-images S3_DATASET_NAME=ci_20260916_01 S3_LOCAL_IMAGES_DIR=/path/to/images S3_BUCKET=<bucket> S3_PREFIX=ci_20260916_01 S3_UPLOAD_WORKERS=8` |
| `brand-s3-sync-manifest-from-s3` | 从 S3 目标目录反查对象并生成可续传上传清单 | `make brand-s3-sync-manifest-from-s3 S3_DATASET_NAME=GH_2026_09_15 S3_LOCAL_IMAGES_DIR=datasets/diaper_category/GH/v2026-09-15/raw/images S3_BUCKET=uat-smdp4cust-bak S3_PREFIX=GH/2026_09_15/images S3_REGION=af-south-1 S3_PROFILE=smdp-yolo` |
| `brand-s3-ls-import-json` | 根据 S3 图片清单生成 Label Studio 导入 JSON 和标签配置 | `make brand-s3-ls-import-json S3_DATASET_NAME=ci_20260916_01 S3_LABEL_NAME=diaper S3_IMAGE_URL_MODE=nginx` |
| `brand-s3-nginx-start` | 生成配置并启动本地 Nginx 图片代理 | `make brand-s3-nginx-start S3_DATASET_NAME=ci_20260916_01 S3_BUCKET=<bucket> S3_PROFILE=<profile>` |
| `brand-s3-nginx-reload` | 刷新 Nginx map/预签名 URL 并 reload | `make brand-s3-nginx-reload S3_DATASET_NAME=ci_20260916_01 S3_BUCKET=<bucket> S3_PROFILE=<profile>` |
| `brand-s3-nginx-stop` | 停止本地 Nginx 图片代理 | `make brand-s3-nginx-stop S3_DATASET_NAME=ci_20260916_01` |
| `brand-s3-proxy-start` | 启动本地图片代理；默认 Nginx，可 `S3_PROXY_BACKEND=python` 回退旧代理 | `make brand-s3-proxy-start S3_DATASET_NAME=ci_20260916_01 S3_BUCKET=<bucket> S3_PROFILE=<profile>` |
| `brand-s3-ls-apply` | 将 S3/Nginx/proxy 图片任务导入 Label Studio | `make brand-s3-ls-apply S3_DATASET_NAME=ci_20260916_01` |
| `1-brand-s3-workflow-to-ls` | 上传 S3、启动 Nginx 代理、生成并导入 Label Studio | `make 1-brand-s3-workflow-to-ls S3_DATASET_NAME=ci_20260916_01 S3_LOCAL_IMAGES_DIR=/path/to/images S3_BUCKET=<bucket> S3_UPLOAD_WORKERS=8` |
| `brand-s3-ls-export` | 从 Label Studio 导出 S3 图片标注 JSON；需传 LS_PROJECT_ID=<项目ID> | `make brand-s3-ls-export S3_DATASET_NAME=ci_20260916_01 LS_PROJECT_ID=<项目ID>` |
| `brand-s3-ls-to-yolo` | 将 S3 图片 Label Studio 导出转换为 YOLO 标签和 EC2 下载清单 | `make brand-s3-ls-to-yolo S3_DATASET_NAME=ci_20260916_01 S3_LABEL_NAME=diaper S3_LS_TO_YOLO_CLEAR=1` |
| `2-brand-s3-workflow-after-ls` | 导出 S3 图片标注并生成 YOLO 标签/EC2 图片清单 | `make 2-brand-s3-workflow-after-ls S3_DATASET_NAME=ci_20260916_01 LS_PROJECT_ID=<项目ID> S3_LS_TO_YOLO_CLEAR=1` |
| `local-ls-s3-to-yolo` | 本地地址 LS 导出结合 s3_images.json 生成 YOLO 标签/EC2 图片清单 | `make local-ls-s3-to-yolo LOCAL_LS_EXPORT_PATH=/path/to/export.json S3_DATASET_NAME=ci_20260916_01 S3_LOCAL_IMAGES_DIR=/path/to/images S3_LS_TO_YOLO_CLEAR=1` |
| `2-local-ls-s3-workflow-after-ls` | 导出本地目录 LS 项目并结合 S3 上传清单生成 YOLO 标签/EC2 图片清单 | `make 2-local-ls-s3-workflow-after-ls LOCAL_DATASET_NAME=<本地LS数据集名> LS_PROJECT_ID=<项目ID> S3_DATASET_NAME=ci_20260916_01 S3_LOCAL_IMAGES_DIR=/path/to/images S3_LS_TO_YOLO_CLEAR=1` |
| `3-brand-s3-workflow-ec2-train` | 上传 S3 训练清单到 EC2、下载 S3 图片并启动训练，默认 dry-run | `make 3-brand-s3-workflow-ec2-train S3_DATASET_NAME=ci_20260916_01 EC2_BASE_MODEL=yolo26m.pt EC2_TRAIN_EPOCHS=100 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-upload-manifest` | 上传 S3 标签、EC2 图片清单和 YAML 到 EC2，默认 dry-run | `make brand-s3-ec2-upload-manifest S3_DATASET_NAME=ci_20260916_01 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-download-images` | 在 EC2 上按 manifest 从 S3 下载训练图片，默认 dry-run | `make brand-s3-ec2-download-images S3_DATASET_NAME=ci_20260916_01 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-train` | 在 EC2 下载 S3 图片并训练，默认 dry-run | `make brand-s3-ec2-train S3_DATASET_NAME=ci_20260916_01 EC2_BASE_MODEL=yolo26m.pt EC2_TRAIN_EPOCHS=100 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-evaluate` | 归档 EC2 S3 数据集训练产物并生成评估摘要，默认 dry-run | `make brand-s3-ec2-evaluate S3_DATASET_NAME=ci_20260916_01 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-download-artifacts` | 下载 EC2 S3 数据集训练归档目录，默认 dry-run | `make brand-s3-ec2-download-artifacts S3_DATASET_NAME=ci_20260916_01 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `brand-s3-ec2-download-model` | 下载 EC2 S3 数据集 best.pt，默认 dry-run | `make brand-s3-ec2-download-model S3_DATASET_NAME=ci_20260916_01 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
