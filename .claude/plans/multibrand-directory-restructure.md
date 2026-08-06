# 多品牌目录与代码结构重构计划

## 背景问题

当前项目已经升级为多品牌多类别，但很多目录和配置仍然叫 `softcare`：

- 数据集根目录：`datasets/softcare/`
- YAML：`data/softcare.yaml`、`data/softcare_pseudo.yaml`
- Label Studio 导入文件：`softcare_label_studio_import.json`
- 训练/推理默认路径和文档中仍有 Softcare 单品牌表述
- `scripts/` 下所有脚本平铺，后续流程继续扩展会越来越难维护

需要把目录、配置和代码组织方式改成“多品牌业务流程”结构。

## 新目录设计

### 1. 数据目录

将：

```text
datasets/softcare/
```

迁移为：

```text
datasets/multibrand/
├── raw/                         # Excel 下载的原始未标注图片
│   ├── images/
│   └── metadata/
├── ocr/                         # OCR 品牌候选筛选结果
│   ├── candidates/
│   └── metadata/
├── pseudo/                      # YOLO-World 多品牌预标注输出
│   ├── images/{train,val,test}/
│   ├── labels/{train,val,test}/
│   └── metadata/
├── label_studio/                # Label Studio 导入/导出中间文件
│   └── exports/
├── images/{train,val,test}/     # 人工复核后的正式训练图片
└── labels/{train,val,test}/     # 人工复核后的正式 YOLO 多类别标签
```

说明：

- `datasets/multibrand` 表示业务数据集，不再绑定某一个品牌。
- 若 `datasets/softcare` 已存在，会整体迁移到 `datasets/multibrand`。
- 旧路径不再作为默认路径使用。

### 2. 配置目录

保留 `data/` 作为“配置与少量样例”目录，但重命名 YAML：

```text
data/
├── brand_keywords.json          # 多品牌类别来源，保留
├── multibrand.yaml              # 正式训练集 YAML
├── multibrand_pseudo.yaml       # 伪标注集 YAML
└── samples/
    └── multibrand-shelf.webp    # 示例图片，可由旧 softcare-shelf.webp 复制/重命名
```

旧文件：

```text
data/softcare.yaml
data/softcare_pseudo.yaml
```

将迁移/替换为：

```text
data/multibrand.yaml
data/multibrand_pseudo.yaml
```

`make brand-yaml` 后续只写新 YAML。

### 3. 模型与输出目录

使用多品牌命名：

```text
models/multibrand-best.pt
models/train/multibrand/
outputs/predict/
```

旧 `models/softcare-best.pt` 不再作为默认模型，但不主动删除，避免误删历史模型。

### 4. 代码目录

将平铺 `scripts/*.py` 按用途/步骤归类为：

```text
scripts/
├── common/
│   ├── __init__.py
│   └── brand_library.py                 # 品牌库、类别、Label Studio XML、YAML 公共逻辑
├── data_import/
│   ├── __init__.py
│   ├── import_images_from_excel.py       # step-1
│   └── download_sample.py                # 样例图片下载
├── ocr/
│   ├── __init__.py
│   └── filter_brand_candidates.py        # step-2
├── pseudo_label/
│   ├── __init__.py
│   └── generate_yolo_world.py            # step-3
├── label_studio/
│   ├── __init__.py
│   ├── generate_import.py                # step-4 生成 JSON
│   ├── apply_import.py                   # step-4 导入 LS
│   └── export_to_yolo.py                 # step-5 导出转 YOLO
├── training/
│   ├── __init__.py
│   ├── validate_dataset.py               # step-7 / train 前校验
│   └── train.py                          # step-6
├── inference/
│   ├── __init__.py
│   └── predict.py                        # step-7 推理验证
└── config/
    ├── __init__.py
    └── write_brand_yolo_yaml.py          # brand-yaml
```

旧脚本文件将用 `git mv`/`mv` 迁移，Makefile 改为调用新路径。

## 代码调整策略

### import 路径

迁移后脚本不再平铺，因此需要统一处理 imports：

- 公共模块改为：`scripts/common/brand_library.py`
- 各脚本开头加入 `scripts` 根目录到 `sys.path`，然后使用：

```python
from common.brand_library import ...
```

- `training/train.py` 对 `validate_dataset` 的导入改为包内或显式路径导入。

### 默认路径替换

全部默认路径从 softcare 改为 multibrand：

- `datasets/softcare` -> `datasets/multibrand`
- `data/softcare.yaml` -> `data/multibrand.yaml`
- `data/softcare_pseudo.yaml` -> `data/multibrand_pseudo.yaml`
- `softcare_label_studio_import.json` -> `multibrand_label_studio_import.json`
- `Softcare Diaper Review ...` -> `Multi Brand Package Review ...`
- `models/softcare-best.pt` -> `models/multibrand-best.pt`

## Makefile 调整

主要变量改为：

```make
DATASET_ROOT       ?= $(PROJECT_ROOT)/datasets/multibrand
RAW_DIR            ?= $(DATASET_ROOT)/raw/images
OCR_OUTPUT_DIR     ?= $(DATASET_ROOT)/ocr
PSEUDO_ROOT        ?= $(DATASET_ROOT)/pseudo
TRAIN_DATA_YAML    ?= $(PROJECT_ROOT)/data/multibrand.yaml
BRAND_DATA_YAML    ?= $(PROJECT_ROOT)/data/multibrand.yaml
BRAND_PSEUDO_YAML  ?= $(PROJECT_ROOT)/data/multibrand_pseudo.yaml
LS_IMPORT_JSON     ?= $(DATASET_ROOT)/label_studio/multibrand_label_studio_import.json
LS_LABEL_CONFIG_XML ?= $(DATASET_ROOT)/label_studio/label_config.xml
TRAIN_NAME         ?= multibrand
FINAL_MODEL        ?= $(PROJECT_ROOT)/models/multibrand-best.pt
PREDICT_SOURCE     ?= $(PROJECT_ROOT)/data/samples/multibrand-shelf.webp
```

脚本命令改为新路径，例如：

```make
$(VENV_BIN)/python scripts/data_import/import_images_from_excel.py
$(VENV_BIN)/python scripts/ocr/filter_brand_candidates.py
$(VENV_BIN)/python scripts/pseudo_label/generate_yolo_world.py
$(VENV_BIN)/python scripts/label_studio/generate_import.py
$(VENV_BIN)/python scripts/label_studio/apply_import.py
$(VENV_BIN)/python scripts/label_studio/export_to_yolo.py
$(VENV_BIN)/python scripts/training/train.py
$(VENV_BIN)/python scripts/training/validate_dataset.py
$(VENV_BIN)/python scripts/inference/predict.py
$(VENV_BIN)/python scripts/config/write_brand_yolo_yaml.py
```

## 兼容与迁移处理

1. 如果存在 `datasets/softcare` 且 `datasets/multibrand` 不存在，则迁移目录。
2. 如果两者都存在，优先保留 `datasets/multibrand`，不覆盖。
3. 旧 YAML 可保留或删除；默认 Makefile 不再使用旧 YAML。
4. 旧脚本路径不保留包装脚本，避免双入口混乱；文档全部更新为新路径。
5. `.gitignore` 更新为忽略 `datasets/*/raw/images`、`datasets/*/pseudo/images`、`datasets/*/images`，已基本兼容多数据集命名。

## 文档更新

同步修改：

- `README.md`
- `设计.md`
- `docs/reports/softcare-yolo-setup-2026-08-05.md`（可保留历史文件名，但追加多品牌目录重构小节）
- 如需要，可新建 `docs/reports/multibrand-structure-2026-08-06.md`，记录本次结构重构。

重点说明：

- 新目录结构。
- 新脚本分层。
- 新 YAML 名称。
- Make 参数新默认值。
- 从旧 `softcare` 到新 `multibrand` 的迁移说明。

## 验证计划

执行以下验证：

```bash
make help
make brand-yaml
.venv/bin/python -m compileall -q scripts
make -n workflow-to-ls
make -n workflow-after-ls LS_PROJECT_ID=1
make -n step-3-pseudo-label PSEUDO_USE_OCR_CANDIDATES=0 PSEUDO_LIMIT=1
make data-validate
```

再做功能烟测：

```bash
make step-3-pseudo-label PSEUDO_USE_OCR_CANDIDATES=0 PSEUDO_LIMIT=1 PSEUDO_ROOT=.tmp/restructure-pseudo-test
make ls-import-json LS_IMPORT_JSON=.tmp/restructure_ls_import.json PSEUDO_ROOT=.tmp/restructure-pseudo-test
```

验证：

- 多品牌 YAML names 正确。
- 预标注标签 class_id 正确。
- Label Studio JSON predictions 多标签正确。
- 数据集校验通过。

## 风险

- 当前 git 工作区已有大量由 OCR/预标注产生的改动，目录迁移会让 diff 变大。
- 旧 Label Studio 项目仍指向旧路径任务，不建议继续复用；应基于新路径重新导入新项目。
- 如果用户希望保留旧 softcare 目录作备份，需要在执行前复制一份；本计划默认迁移而不是复制，以避免双数据源混乱。
