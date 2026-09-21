# 通用标签类别工作流

本模块把历史的品牌、纸尿裤、本地目录、S3 单类别流程统一到 `LABEL_SET` / `LABELS` 参数上。

## 类别配置

类别维护在可提交 Git 的 `config/label_categories.json` 中，也可以在 Web 控制台“类别管理”页面编辑。

| 参数 | 说明 | 默认值 |
|---|---|---|
| `LABEL_CATALOG` | 通用类别配置 JSON | `config/label_categories.json` |
| `LABEL_SET` | 类别列表名称 | `general` |
| `LABELS` | 多选类别，英文逗号分隔；控制台全选表示全部，命令行留空表示全部，`all` 仅作历史兼容 | 空值 |
| `COUNTRY` | 国家/市场代码，用于默认目录 | `default` |
| `DATA_VERSION` | 数据版本，用于默认目录 | 当天日期 |
| `LABEL_DATASET_NAME` | 数据集短名称；留空时自动从类别选择生成 | 自动生成 |

默认目录规则：

```text
datasets/<COUNTRY>/<DATA_VERSION>/<LABEL_DATASET_NAME>/
```

Excel、本地目录、S3 只表示导入或图片访问方式，不再作为一级目录拆分同一数据集。S3 上传清单和 EC2 下载清单统一放在数据集内的 `s3/metadata/`。

标准目录示例：

```text
datasets/GH/v2026-09-18/general_diaper_allround_purple/
├── raw/images/
├── raw/metadata/
├── label_studio/
├── s3/metadata/
├── images/{train,val,test}/
└── labels/{train,val,test}/
```

## 本地目录导入 LS

```bash
make 1-label-local-workflow-to-ls \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=diaper,allround_purple \
  LABEL_LOCAL_IMAGES_DIR=/path/to/images
```

本地目录流程会先把源图片复制/沉淀到标准 `raw/images/`，后续 Label Studio 导入、S3 上传和 YOLO 转换都围绕同一个 `LABEL_DATASET_ROOT` 工作。

人工标注后：

```bash
make 2-label-workflow-after-ls \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=diaper,allround_purple \
  LS_PROJECT_ID=<项目ID> \
  LABEL_LS_TO_YOLO_CLEAR=1
```

## Excel 导入 LS

```bash
make 1-label-excel-workflow-to-ls \
  COUNTRY=CI \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=diaper \
  EXCEL=/path/to/images.xlsx \
  EXCEL_COLUMN=整改后图片URL
```

## S3 图片导入 LS 与 EC2 训练

```bash
make 1-label-s3-workflow-to-ls \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=allround_purple \
  LABEL_LOCAL_IMAGES_DIR=/path/to/images \
  S3_BUCKET=<bucket> \
  LABEL_S3_PREFIX=GH/v2026-09-18/allround_purple

make 2-label-s3-workflow-after-ls \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=allround_purple \
  LS_PROJECT_ID=<项目ID> \
  LABEL_LS_TO_YOLO_CLEAR=1

make 3-label-s3-workflow-ec2-train \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=allround_purple \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem
```

该一键流程适合“还没有本地 YOLO 训练集、希望直接把图片先上传到 S3 再建 LS 项目”的情况。若已经完成“通用本地 LS 转 YOLO”，并且只想上传 `images/{train,val,test}` 中的训练图片，请单独执行：

```bash
make label-s3-upload-images \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=allround_purple \
  LABEL_LOCAL_IMAGES_DIR=datasets/GH/v2026-09-18/allround_purple/images \
  LABEL_RECURSIVE=1 \
  S3_BUCKET=<bucket>

make label-yolo-s3-to-ec2-manifest \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=allround_purple \
  LABEL_LS_TO_YOLO_SKIP_EMPTY=1
```

第二个命令会基于已有 YOLO `images/labels` 和 `s3/metadata/s3_images.json` 生成 `s3/metadata/ec2_image_manifest.json|csv`，不再读取 LS export，也不会重写训练集。

训练完成后，如果要用 EC2 上的模型批量验证一批 S3 图片，可传入 S3 上的 txt/csv/json/xlsx 清单，并指定结果上传目录：

```bash
make label-s3-ec2-predict-manifest \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=allround_purple \
  EC2_HOST=<host> \
  EC2_KEY=/path/key.pem \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_PREDICT_MANIFEST_SOURCE=s3://<bucket>/predict-inputs/images.xlsx \
  EC2_PREDICT_INPUT_COLUMN=整改后图片URL \
  EC2_PREDICT_OUTPUT_S3_URI=s3://<bucket>/predict-results/GH/v2026-09-18/run1 \
  EC2_PREDICT_LIMIT=20 \
  EC2_EXECUTE=1
```

推理结果会上传 `summary.json`、`summary.csv`、`json/` 单图结果和 `annotated/` 带框图片。EC2 命令默认 dry-run；确认命令无误后再加 `EC2_EXECUTE=1`。

## 兼容说明

旧的 `diaper-*`、`local-dir-*`、`brand-s3-*`、`BRAND=<品牌>` 入口仍保留，避免历史流程不可用。新项目建议优先使用本模块的 `label-*` 通用命令。
