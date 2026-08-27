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

- `02-diaper-ec2-upload-data` **仍保留**，仅用于首次把新的国家/版本数据集上传到 EC2。当前 EC2 已存在 `CI/v2026-08-27_01` 数据时，不需要重复执行。
- `03/06/07` 训练命令会在 EC2 训练前自动生成使用**绝对数据目录**的 YAML，因此不需要通过 `02` 上传本地 YAML。

## EC2 A10 目录建议

```text
/home/ubuntu/yoloExample/
├── config/generated/diaper_category_ghana_v20260812.yaml
├── datasets/diaper_category/ghana/v20260812/
├── models/train/diaper_category_ghana_v20260812/weights/best.pt
└── models/ec2/diaper_category/ghana/v20260812/best.pt
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
  DIAPER_VERSION=v20260812
```

确认无误后加 `EC2_EXECUTE=1`：

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

make 03-diaper-ec2-train-smoke \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_TRAIN_BATCH=16 \
  EC2_TRAIN_DEVICE=0 \
  EC2_EXECUTE=1

make 04-diaper-ec2-evaluate \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_EXECUTE=1

make 05-diaper-ec2-download-artifacts \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_EXECUTE=1

make 06-diaper-ec2-train-baseline \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_EXECUTE=1

make 07-diaper-ec2-train-improve \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_EXECUTE=1

make 08-diaper-ec2-predict \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_PREDICT_SOURCE=/home/ubuntu/test.jpg \
  EC2_EXECUTE=1

make 09-diaper-ec2-download-model \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  EC2_EXECUTE=1
```

## 参数说明

| 变量 | 默认值 | 说明 | 示例 |
|---|---|---|---|
| `DIAPER_COUNTRY` | `default` | 国家/市场代码，用于目录分组。 | `DIAPER_COUNTRY=ghana` |
| `DIAPER_VERSION` | `v<今天日期>` | 数据版本，用于批次隔离。 | `DIAPER_VERSION=v20260812` |
| `DIAPER_EXCEL` | `$(EXCEL)` | 正式图片 Excel。 | `DIAPER_EXCEL=/path/images.xlsx` |
| `DIAPER_EXCEL_COLUMN` | `$(EXCEL_COLUMN)` | 图片 URL 列名。 | `DIAPER_EXCEL_COLUMN=整改后图片URL` |
| `DIAPER_LABEL_NAME` | `纸尿裤` | Label Studio 和 YOLO 单类别名。 | `DIAPER_LABEL_NAME=纸尿裤` |
| `DIAPER_DATASET_ROOT` | `datasets/diaper_category/<country>/<version>` | 当前国家/版本数据集根目录。 | 自动派生 |
| `DIAPER_DATA_YAML` | `config/generated/diaper_category_<country>_<version>.yaml` | 单类别 YAML。 | 自动派生 |
| `DIAPER_FINAL_MODEL` | `models/diaper_category/<country>/<version>/best.pt` | 下载回本地的 EC2 best.pt。 | 自动派生 |
| `EC2_HOST` | 空 | EC2 地址或 SSH Host。 | `EC2_HOST=1.2.3.4` |
| `EC2_USER` | `ubuntu` | SSH 用户。 | `EC2_USER=ubuntu` |
| `EC2_KEY` | 空 | SSH 私钥。 | `EC2_KEY=~/.ssh/a10.pem` |
| `EC2_PORT` | `22` | SSH 端口。 | `EC2_PORT=22` |
| `EC2_PROJECT_ROOT` | `/home/$(EC2_USER)/yoloExample` | EC2 项目根目录。 | `EC2_PROJECT_ROOT=/data/yoloExample` |
| `EC2_PYTHON_CMD` | `uv run python` | EC2 上执行 Python 的命令。 | `EC2_PYTHON_CMD='python'` |
| `EC2_BASE_MODEL` | `models/yolo26m.pt` | EC2 上基座模型路径。 | `EC2_BASE_MODEL=models/yolo26s.pt` |
| `EC2_TRAIN_DEVICE` | `0` | A10 GPU 设备号。 | `EC2_TRAIN_DEVICE=0` |
| `EC2_TRAIN_BATCH` | `16` | EC2 训练 batch。 | `EC2_TRAIN_BATCH=32` |
| `EC2_TRAIN_EPOCHS` | `100` | EC2 训练轮数。 | `EC2_TRAIN_EPOCHS=150` |
| `EC2_TRAIN_IMGSZ` | `960` | EC2 训练/推理尺寸。 | `EC2_TRAIN_IMGSZ=1280` |
| `EC2_EXECUTE` | `0` | 是否实际执行 SSH/rsync。 | `EC2_EXECUTE=1` |
| `EC2_PREDICT_SOURCE` | 样例图片 | EC2 上推理输入。 | `EC2_PREDICT_SOURCE=/home/ubuntu/test.jpg` |
