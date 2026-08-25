# 纸尿裤大类标注与 EC2 训练新流程

## 背景与目标

新增一套独立于现有多品牌识别的“纸尿裤大类”流程：

- 按国家和版本下载正式图片，目录带版本号，便于后续不同国家、多轮数据集并行管理。
- 本流程先不做自动预标注，只把原始图片导入 Label Studio，交给同事人工标注。
- 标签不是品牌，而是单一大类：`纸尿裤`。
- 规划并实现 SSH/rsync 上传到 AWS EC2 A10 机器、远程训练/推理命令、下载训练后模型的脚本或 Make 命令。
- EC2 连接无需实际校验，只校验本地代码语法和 Makefile 命令展开。

## 目录规则

新增数据根目录：

```text
datasets/diaper_category/<COUNTRY>/<VERSION>/
├── raw/
│   ├── images/              # Excel 下载的正式原图
│   └── metadata/            # download_report.csv/json
├── label_studio/
│   ├── diaper_category_label_studio_import.json
│   └── exports/             # LS 导出 JSON 与转换报告
├── images/{train,val,test}/ # 人工标注导出的 YOLO 训练图
└── labels/{train,val,test}/ # 人工标注导出的 YOLO 标签
```

配置文件：

```text
config/generated/diaper_category_<COUNTRY>_<VERSION>.yaml
```

YAML 中只包含一个类别：

```yaml
names:
  0: 纸尿裤
```

EC2 远端建议目录：

```text
<EC2_PROJECT_ROOT>/
├── scripts/
├── config/generated/diaper_category_<COUNTRY>_<VERSION>.yaml
├── datasets/diaper_category/<COUNTRY>/<VERSION>/...
├── models/train/diaper_category_<COUNTRY>_<VERSION>/weights/{best,last}.pt
└── models/ec2/diaper_category/<COUNTRY>/<VERSION>/best.pt
```

## 新增 Make 参数

- `DIAPER_COUNTRY ?= default`
- `DIAPER_VERSION ?= v$(date +%Y%m%d)`（可手动覆盖）
- `DIAPER_EXCEL ?= $(EXCEL)`
- `DIAPER_EXCEL_COLUMN ?= $(EXCEL_COLUMN)`
- `DIAPER_DATASET_ROOT ?= datasets/diaper_category/$(DIAPER_COUNTRY)/$(DIAPER_VERSION)`
- `DIAPER_LABEL_NAME ?= 纸尿裤`
- `DIAPER_CLASS_NAME ?= diaper`
- `DIAPER_DATA_YAML ?= config/generated/diaper_category_$(DIAPER_COUNTRY)_$(DIAPER_VERSION).yaml`
- EC2：`EC2_HOST`、`EC2_USER`、`EC2_KEY`、`EC2_PORT`、`EC2_PROJECT_ROOT`、`EC2_PYTHON_CMD` 等。

## 新增脚本

1. `scripts/config/write_single_class_yolo_yaml.py`
   - 生成单类别 YOLO YAML。
   - 支持中文显示名 `纸尿裤`。

2. `scripts/label_studio/generate_single_class_import.py`
   - 从下载报告 CSV 生成 Label Studio 任务 JSON。
   - 不读取 pseudo labels，不生成 predictions。
   - 输出 Label Studio XML 标签配置，标签值为 `纸尿裤`。

3. `scripts/label_studio/export_single_class_to_yolo.py`
   - 从 Label Studio JSON 导出读取 `纸尿裤` 矩形框。
   - 转换为 YOLO class_id=0。
   - 按 70/20/10 稳定划分 train/val/test。
   - 可选 `--clear-output` 和 `--skip-empty-annotations`。

4. `scripts/cloud/ec2_diaper_workflow.py`
   - 生成并执行（或 dry-run）rsync/ssh 命令。
   - 子命令：`upload-data`、`upload-project`、`train`、`predict`、`download-model`。
   - Make 默认只展开命令；实际执行依赖用户提供 EC2 参数。

## 新增 Make 命令

本地数据与标注：

- `diaper-yaml`：生成纸尿裤大类 YAML。
- `diaper-import-excel`：下载正式图片到国家/版本目录。
- `diaper-ls-import-json`：生成无预标注的 Label Studio 导入 JSON。
- `diaper-ls-apply`：复用 Label Studio shell 创建项目并导入任务（必要时可增强 apply 脚本支持标签配置文件）。
- `diaper-ls-export`：导出 LS JSON。
- `diaper-ls-to-yolo`：人工标注完成后转换为 YOLO 训练集。
- `diaper-workflow-to-ls`：下载图片 + 生成 YAML + 生成 LS JSON + 导入 LS。
- `diaper-workflow-after-ls`：导出 LS + 转 YOLO。

EC2：

- `diaper-ec2-upload-project`：上传代码和必要配置到 EC2。
- `diaper-ec2-upload-data`：上传当前国家/版本数据集和 YAML。
- `diaper-ec2-train`：在 EC2 上执行训练，默认 `TRAIN_DEVICE=0`。
- `diaper-ec2-predict`：在 EC2 上执行推理验证。
- `diaper-ec2-download-model`：下载 EC2 上训练好的 `best.pt` 到本地模型目录。

## 验证策略

- 不连接 EC2，不验证 SSH 连通性。
- 运行 Python 编译检查。
- 用临时下载报告和临时 LS 导出 JSON 做单元测试：
  - 单类别 YAML 正确生成。
  - LS 导入 JSON 没有 predictions，标签配置为 `纸尿裤`。
  - LS 导出可转换为 class_id=0 的 YOLO txt。
  - EC2 脚本 dry-run 命令包含 rsync/ssh/train/download 关键参数。
- Makefile 使用 `make -n` 检查命令展开。
- 更新 `README.md`、`设计.md` 和 `docs/reports/`。
