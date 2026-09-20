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
datasets/<来源>/<COUNTRY>/<DATA_VERSION>/<LABEL_DATASET_NAME>/
```

其中 `<来源>` 由 `LABEL_DATA_DOMAIN` 控制，常用值为 `excel`、`local`、`s3`。

## 本地目录导入 LS

```bash
make 1-label-local-workflow-to-ls \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=diaper,allround_purple \
  LABEL_LOCAL_IMAGES_DIR=/path/to/images
```

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

EC2 命令默认 dry-run；确认命令无误后再加 `EC2_EXECUTE=1`。

## 兼容说明

旧的 `diaper-*`、`local-dir-*`、`brand-s3-*`、`BRAND=<品牌>` 入口仍保留，避免历史流程不可用。新项目建议优先使用本模块的 `label-*` 通用命令。
