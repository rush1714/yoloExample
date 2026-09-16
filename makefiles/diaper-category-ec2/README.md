# 纸尿裤大类正式标注 + EC2 A10 流程

这是独立于品牌识别的新流程：只标注一个大类 `纸尿裤`，不做 OCR、YOLO-World 或 YOLOE 预标注。

## 本地目录

```text
datasets/diaper_category/<国家>/<版本>/
├── raw/images/
├── raw/metadata/download_report.csv
├── label_studio/diaper_category_label_studio_import.json
├── label_studio/label_config.xml
├── label_studio/exports/
├── images/{train,val,test}/
└── labels/{train,val,test}/
```

## 下载并导入 Label Studio

```bash
make diaper-workflow-to-ls \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  DIAPER_EXCEL=/path/to/images.xlsx \
  DIAPER_EXCEL_COLUMN=整改后图片URL \
  DIAPER_LABEL_NAME=纸尿裤
```
```bash
make diaper-workflow-to-ls \
  DIAPER_COUNTRY=CI \
  DIAPER_VERSION=v2026-08-26_01
```

导入后 Label Studio 标签只有一个：`纸尿裤`。

注意：`diaper-workflow-to-ls` 每执行一次都会创建一个新的 Label Studio 项目；如果只是继续标注已有项目，不要重复执行该命令，直接打开已有项目继续标注。若确实要重新导入一批新任务，再重新执行。

## 人工标注后导出 YOLO 数据集

```bash
make diaper-workflow-after-ls \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  LS_PROJECT_ID=<项目ID> \
  LS_TO_YOLO_CLEAR=1
```

## EC2 代码和数据同步规则

- EC2 项目代码已通过 `git clone` 管理时，**不要使用** `01-diaper-ec2-upload-project`；该命令仅供非 Git 部署环境使用。
- 本地代码修复完成并提交后，在 EC2 执行：

  ```bash
  cd /home/ec2-user/yoloExample
  git pull
  ```

- `02-diaper-ec2-upload-data` **仍保留**，仅用于首次把新的国家/版本数据集上传到 EC2。
- `03-diaper-ec2-train` 会在 EC2 训练前自动生成使用**绝对数据目录**的 YAML，因此不需要通过 `02` 上传本地 YAML。
- Ultralytics 可能为同名运行自动追加后缀；训练脚本会把真实路径写入 `artifacts/.../<EC2_RUN_NAME>/latest-run.txt`，`04-diaper-ec2-evaluate` 会读取该清单，不能手工假设固定 run 路径。

## EC2 A10 目录建议

```text
/home/ubuntu/yoloExample/
├── config/generated/diaper_category_ghana_v20260812.yaml
├── datasets/diaper_category/ghana/v20260812/
├── runs/detect/models/train/diaper_category_ghana_v20260812[-N]/weights/best.pt
├── models/ec2/diaper_category/ghana/v20260812/<EC2_RUN_NAME>/best.pt
└── artifacts/diaper_category/ghana/v20260812/<EC2_RUN_NAME>/
    ├── latest-run.txt
    ├── evaluation-summary.md
    ├── weights/
    ├── metrics/
    ├── plots/
    └── review/
```

## EC2 dry-run / 执行

默认只打印命令，不连接 EC2：

```bash
make diaper-ec2-upload-data \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812

make diaper-ec2-train \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_BASE_MODEL=yolo26m.pt \
  EC2_TRAIN_EPOCHS=100 \
  EC2_TRAIN_IMGSZ=960 \
  EC2_RUN_NAME=yolo26m_img960_e100
```

确认无误后加 `EC2_EXECUTE=1`。训练规模使用显式模型参数控制，`EC2_RUN_NAME` 只用于输出目录和评估报告标识：

```bash
make 01-diaper-ec2-upload-project \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_EXECUTE=1

# 仅在 EC2 尚未有该国家/版本数据集时执行；EC2 已有数据则跳过
make 02-diaper-ec2-upload-data \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_EXECUTE=1

# 代码已通过 git clone 管理时，到 EC2 项目目录拉取提交后的修复
ssh -i /path/key.pem ec2-user@<host> \
  'cd /home/ec2-user/yoloExample && git pull'

make 03-diaper-ec2-train \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_BASE_MODEL=yolo26m.pt \
  EC2_TRAIN_EPOCHS=100 \
  EC2_TRAIN_IMGSZ=960 \
  EC2_TRAIN_BATCH=16 \
  EC2_TRAIN_DEVICE=0 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_EXECUTE=1

make 04-diaper-ec2-evaluate \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_EXECUTE=1

make 05-diaper-ec2-download-artifacts \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_EXECUTE=1

make 06-diaper-ec2-predict \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_PREDICT_SOURCE=/home/ec2-user/test.jpg \
  EC2_EXECUTE=1

make 07-diaper-ec2-download-model \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_EXECUTE=1
```

## 参数说明

| 变量 | 默认值 | 说明 | 示例 |
|---|---|---|---|
| `DIAPER_COUNTRY` | `default` | 国家/市场代码，用于目录分组。 | `DIAPER_COUNTRY=ghana` |
| `DIAPER_VERSION` | `v<今天日期>` | 数据版本，用于批次隔离。 | `DIAPER_VERSION=v20260812` |
| `DIAPER_EXCEL` | `$(EXCEL)` | 正式图片 Excel。 | `DIAPER_EXCEL=/path/images.xlsx` |
| `DIAPER_EXCEL_COLUMN` | `$(EXCEL_COLUMN)` | 图片 URL 列名。 | `DIAPER_EXCEL_COLUMN=整改后图片URL` |
| `DIAPER_LABEL_NAME` | `diaper` | Label Studio、本地 YAML、EC2 训练自动 YAML 和新模型可视化中的单类别名。 | `DIAPER_LABEL_NAME=diaper` |

`DIAPER_LABEL_NAME` 必须在新训练开始前传入。例如：

```bash
make 03-diaper-ec2-train \
  DIAPER_COUNTRY=CI \
  DIAPER_VERSION=v2026-08-27_01 \
  DIAPER_LABEL_NAME=diaper \
  EC2_EXECUTE=1
```

已训练模型的类别显示名不会被代码修改自动更新；若旧模型显示 `纸尿裤`，需要重新训练，或在推理阶段单独覆盖模型 names。
| `DIAPER_DATASET_ROOT` | `datasets/diaper_category/<country>/<version>` | 当前国家/版本数据集根目录。 | 自动派生 |
| `DIAPER_DATA_YAML` | `config/generated/diaper_category_<country>_<version>.yaml` | 单类别 YAML。 | 自动派生 |
| `DIAPER_FINAL_MODEL` | `models/diaper_category/<country>/<version>/<EC2_RUN_NAME>/best.pt` | 下载回本地的 EC2 best.pt。 | 自动派生 |
| `EC2_HOST` | 空 | EC2 地址或 SSH Host。 | `EC2_HOST=1.2.3.4` |
| `EC2_USER` | `ubuntu` | SSH 用户。 | `EC2_USER=ubuntu` |
| `EC2_KEY` | 空 | SSH 私钥。 | `EC2_KEY=~/.ssh/a10.pem` |
| `EC2_PORT` | `22` | SSH 端口。 | `EC2_PORT=22` |
| `EC2_PROJECT_ROOT` | `/home/$(EC2_USER)/yoloExample` | EC2 项目根目录。 | `EC2_PROJECT_ROOT=/data/yoloExample` |
| `EC2_PYTHON_CMD` | `uv run python` | EC2 上执行 Python 的命令。 | `EC2_PYTHON_CMD='python'` |
| `EC2_BASE_MODEL` | `yolo26m.pt` | EC2 上基座模型路径或 Ultralytics 模型名。 | `EC2_BASE_MODEL=yolo26s.pt` |
| `EC2_TRAIN_DEVICE` | `0` | A10 GPU 设备号。 | `EC2_TRAIN_DEVICE=0` |
| `EC2_TRAIN_BATCH` | `16` | EC2 训练 batch。 | `EC2_TRAIN_BATCH=32` |
| `EC2_TRAIN_EPOCHS` | `100` | EC2 训练轮数。 | `EC2_TRAIN_EPOCHS=150` |
| `EC2_TRAIN_IMGSZ` | `960` | EC2 训练/推理尺寸。 | `EC2_TRAIN_IMGSZ=1280` |
| `EC2_RUN_NAME` | 自动派生 | 输出模型、归档和报告目录标识，不决定训练规模。 | `EC2_RUN_NAME=yolo26m_img960_e100` |
| `EC2_EXECUTE` | `0` | 是否实际执行 SSH/rsync。 | `EC2_EXECUTE=1` |
| `EC2_PREDICT_SOURCE` | 样例图片 | EC2 上推理输入。 | `EC2_PREDICT_SOURCE=/home/ubuntu/test.jpg` |

## 命令示例索引

| 命令 | 作用 | 示例 |
|---|---|---|
| `diaper-yaml` | 生成纸尿裤大类单类别 YOLO YAML | `make diaper-yaml DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 DIAPER_LABEL_NAME=diaper` |
| `diaper-import-excel` | 下载纸尿裤大类正式图片到国家/版本目录 | `make diaper-import-excel DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 DIAPER_EXCEL=/path/images.xlsx DIAPER_EXCEL_COLUMN=整改后图片URL` |
| `diaper-ls-import-json` | 生成纸尿裤大类 LS 导入 JSON，无预标注 predictions | `make diaper-ls-import-json DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 DIAPER_LABEL_NAME=diaper` |
| `diaper-ls-apply` | 导入纸尿裤大类任务到 Label Studio（每执行一次都会创建一个新 LS 项目） | `make diaper-ls-apply DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 DIAPER_LABEL_NAME=diaper` |
| `diaper-ls-export` | 从 Label Studio 导出纸尿裤大类 JSON；需传 LS_PROJECT_ID=<项目ID> | `make diaper-ls-export DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 LS_PROJECT_ID=<项目ID>` |
| `diaper-merge-ls-projects` | 导出多个 LS 项目并合并有有效框的任务；需传 LS_PROJECT_IDS=21,20 | `make diaper-merge-ls-projects DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 LS_PROJECT_IDS=21,20` |
| `diaper-ls-to-yolo` | 转换纸尿裤大类 LS 导出为 YOLO 数据集 | `make diaper-ls-to-yolo DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 DIAPER_LS_EXPORT_PATH=/path/label_studio_export.json LS_TO_YOLO_CLEAR=1` |
| `diaper-merge-ls-projects-to-yolo` | 导出多个 LS 项目、合并有效框并转换为 YOLO 训练集 | `make diaper-merge-ls-projects-to-yolo DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 LS_PROJECT_IDS=21,20 LS_TO_YOLO_CLEAR=1` |
| `1-diaper-workflow-to-ls` | 下载纸尿裤大类正式图片并导入 LS，无预标注 | `make 1-diaper-workflow-to-ls DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 DIAPER_LABEL_NAME=diaper` |
| `2-diaper-workflow-after-ls` | 导出纸尿裤大类人工标注并转换 YOLO 数据集 | `make 2-diaper-workflow-after-ls DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 LS_PROJECT_ID=<项目ID> LS_TO_YOLO_CLEAR=1` |
| `diaper-prepare-dirs` | 创建纸尿裤大类流程需要的临时、日志和导出目录 | `make diaper-prepare-dirs DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28` |
| `01-diaper-ec2-upload-project` | 01. 仅非 Git 部署环境：上传项目代码到 EC2 | `make 01-diaper-ec2-upload-project EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `02-diaper-ec2-upload-data` | 02. 上传当前纸尿裤数据集到 EC2（训练 YAML 自动生成） | `make 02-diaper-ec2-upload-data DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `03-diaper-ec2-train` | 03. 使用显式 EC2_* 模型参数训练 | `make 03-diaper-ec2-train DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_BASE_MODEL=yolo26m.pt EC2_TRAIN_EPOCHS=100 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `04-diaper-ec2-evaluate` | 04. 归档训练产物并生成 evaluation-summary.md | `make 04-diaper-ec2-evaluate DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `05-diaper-ec2-download-artifacts` | 05. 下载完整训练归档目录 | `make 05-diaper-ec2-download-artifacts DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `06-diaper-ec2-predict` | 06. 使用 EC2 模型做推理验证 | `make 06-diaper-ec2-predict DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_RUN_NAME=yolo26m_img960_e100 EC2_PREDICT_SOURCE=/home/ec2-user/test.jpg EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `07-diaper-ec2-download-model` | 07. 下载 EC2 best.pt 模型 | `make 07-diaper-ec2-download-model DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `diaper-ec2-upload-project` | 仅非 Git 部署环境：dry-run 输出 rsync 上传项目代码命令；EC2_EXECUTE=1 才执行 | `make diaper-ec2-upload-project DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `diaper-ec2-upload-data` | 仅首次需要：上传当前纸尿裤数据到 EC2；训练 YAML 会由 EC2 训练命令自动生成绝对路径版本 | `make diaper-ec2-upload-data DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `diaper-ec2-train` | dry-run 输出 EC2 训练命令；EC2_EXECUTE=1 才执行 | `make diaper-ec2-train DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_BASE_MODEL=yolo26m.pt EC2_TRAIN_EPOCHS=100 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `diaper-ec2-evaluate` | dry-run 输出 EC2 训练产物归档与 evaluation-summary.md 生成命令 | `make diaper-ec2-evaluate DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `diaper-ec2-predict` | dry-run 输出 EC2 推理验证命令；EC2_EXECUTE=1 才执行 | `make diaper-ec2-predict DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_RUN_NAME=yolo26m_img960_e100 EC2_PREDICT_SOURCE=/home/ec2-user/test.jpg EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `diaper-ec2-download-model` | dry-run 输出从 EC2 下载 best.pt 的 rsync 命令；EC2_EXECUTE=1 才执行 | `make diaper-ec2-download-model DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
| `diaper-ec2-download-artifacts` | dry-run 输出从 EC2 下载完整训练归档目录的 rsync 命令 | `make diaper-ec2-download-artifacts DIAPER_COUNTRY=CI DIAPER_VERSION=v2026-08-28 EC2_RUN_NAME=yolo26m_img960_e100 EC2_HOST=<host> EC2_KEY=/path/key.pem` |
