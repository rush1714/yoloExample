# 按流程拆分 Makefile 方案

## 目标

将根目录 `Makefile` 从“大而全”的单文件改造成：

- 根 `Makefile` 只保留公共变量、公共工具命令、帮助入口和 `include`。
- 每类完整业务流程放到独立目录中，每个目录包含：
  - `Makefile.mk`：该流程的完整 make 目标。
  - `README.md`：该流程如何使用、参数说明、常用示例。
- 保持原有 `make <target>` 调用方式不变，例如仍可在项目根目录执行：
  - `make workflow-to-ls`
  - `make workflow-to-ls-llm`
  - `make workflow-to-ls-visual`
  - `make diaper-workflow-to-ls`
  - `make diaper-ec2-train`

GNU Make 支持 `include path/to/file.mk`，所以可以这样拆分。

## 目录结构

新增目录：

```text
makefiles/
├── common/
│   ├── Makefile.mk
│   └── README.md
├── brand-ocr-yoloworld/
│   ├── Makefile.mk
│   └── README.md
├── brand-llm-ocr-yoloworld/
│   ├── Makefile.mk
│   └── README.md
├── brand-local-visual-llm/
│   ├── Makefile.mk
│   └── README.md
├── brand-yoloe-visual/
│   ├── Makefile.mk
│   └── README.md
└── diaper-category-ec2/
    ├── Makefile.mk
    └── README.md
```

## 各目录职责

### 1. `makefiles/common/`

保留通用基础能力：

- 项目公共变量：`PROJECT_ROOT`、`VENV_BIN`、`TMP_DIR`、`LOG_DIR`、Label Studio 基础环境变量等。
- 公共数据参数：Excel 下载基础参数、品牌库参数、训练基础参数、推理基础参数。
- 公共目标：
  - `help`
  - `help-params`
  - `prepare-dirs`
  - `brand-check`
  - `brand-list`
  - `brand-yaml`
  - `ls-setup`
  - `ls-start`
  - `ls-stop`
  - `ls-migrate`
  - `ls-shell`
  - `ls-db-create`
  - `ls-db-check`
  - `train`
  - `data-validate`
  - `predict`
  - `datasets-clean-*`
  - `bak-data`

### 2. `makefiles/brand-ocr-yoloworld/`

常规 OCR + YOLO-World 预标注 + LS + 训练验证完整流程：

- `step-1-import-excel`
- `step-2-ocr`
- `step-3-pseudo-label`
- `step-4-import-ls`
- `step-5-export-ls-to-train`
- `step-6-train`
- `step-7-validate`
- `workflow-to-ls`
- `workflow-after-ls`
- 底层目标：`excel-import`、`ocr`、`pseudo-label`、`ls-import-json`、`ls-apply`、`ls-export`、`ls-to-yolo`

README 示例：

```bash
make workflow-to-ls BRAND=SOFTCARE PSEUDO_LIMIT=20
make workflow-after-ls BRAND=SOFTCARE LS_PROJECT_ID=2 TRAIN_EPOCHS=50
```

### 3. `makefiles/brand-llm-ocr-yoloworld/`

Ollama 本地视觉大模型 OCR + YOLO-World 预标注 + LS + 训练验证完整流程：

- `step-2-ocr-llm`
- `workflow-to-ls-llm`
- 底层目标：`ocr-llm`
- 复用公共 `excel-import`、`pseudo-label`、`ls-import-json`、`ls-apply`、`ls-export`、`ls-to-yolo`、`train`、`predict`

README 示例：

```bash
make workflow-to-ls-llm BRAND=SOFTCARE OCR_RESUME=1 LLM_OCR_MODEL=gemma3:12b
make workflow-after-ls BRAND=SOFTCARE LS_PROJECT_ID=2
```

### 4. `makefiles/brand-local-visual-llm/`

本地 llama/Ollama 视觉模型相关流程说明目录。

当前代码中“本地视觉大模型 OCR”主要由 `ocr-llm` 承担；如果后续新增“本地视觉大模型直接预标注”脚本，也放在此目录。

现阶段该目录会提供别名式完整流程，避免只暴露单个命令：

- `workflow-to-ls-local-visual-llm`：等价于 `workflow-to-ls-llm`，但 README 明确这是本地视觉大模型 OCR 路径。
- `local-visual-llm-ocr`
- `local-visual-llm-workflow-after-ls`

README 示例：

```bash
make workflow-to-ls-local-visual-llm BRAND=SOFTCARE LLM_OCR_MODEL=gemma3:12b OCR_RESUME=1
make local-visual-llm-workflow-after-ls BRAND=SOFTCARE LS_PROJECT_ID=2
```

### 5. `makefiles/brand-yoloe-visual/`

YOLOE visual prompt + 品牌参考图预标注完整流程：

- `visual-prompts-import`
- `step-3-pseudo-label-visual`
- `workflow-to-ls-visual`
- `pseudo-label-visual`

README 示例：

```bash
make visual-prompts-import VISUAL_PROMPTS_LIMIT=3
make workflow-to-ls-visual BRAND=SOFTCARE PSEUDO_LIMIT=20 PSEUDO_VISUAL_DEVICE=mps
make workflow-after-ls BRAND=SOFTCARE LS_PROJECT_ID=2
```

### 6. `makefiles/diaper-category-ec2/`

纸尿裤大类正式标注 + EC2 A10 训练/推理完整流程：

- `diaper-yaml`
- `diaper-import-excel`
- `diaper-ls-import-json`
- `diaper-ls-apply`
- `diaper-ls-export`
- `diaper-ls-to-yolo`
- `diaper-workflow-to-ls`
- `diaper-workflow-after-ls`
- `diaper-ec2-upload-project`
- `diaper-ec2-upload-data`
- `diaper-ec2-train`
- `diaper-ec2-predict`
- `diaper-ec2-download-model`

README 示例：

```bash
make diaper-workflow-to-ls DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812 DIAPER_EXCEL=/path/images.xlsx
make diaper-workflow-after-ls DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812 LS_PROJECT_ID=3
make diaper-ec2-upload-data EC2_HOST=<host> EC2_KEY=/path/key.pem DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812
make diaper-ec2-train EC2_HOST=<host> EC2_KEY=/path/key.pem DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812 EC2_EXECUTE=1
make diaper-ec2-download-model EC2_HOST=<host> EC2_KEY=/path/key.pem DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812 EC2_EXECUTE=1
```

## 根 Makefile 改造

根 `Makefile` 改为：

```make
# 公共变量与基础目标
include makefiles/common/Makefile.mk

# 多品牌/单品牌常规 OCR + YOLO-World
include makefiles/brand-ocr-yoloworld/Makefile.mk

# Ollama 本地视觉大模型 OCR + YOLO-World
include makefiles/brand-llm-ocr-yoloworld/Makefile.mk

# 本地视觉大模型流程别名与说明
include makefiles/brand-local-visual-llm/Makefile.mk

# YOLOE visual prompt
include makefiles/brand-yoloe-visual/Makefile.mk

# 纸尿裤大类 + EC2
include makefiles/diaper-category-ec2/Makefile.mk
```

## 兼容性原则

- 不改已有目标名称，避免已有命令失效。
- 每个模块内的目标都可从项目根目录直接 `make <target>` 执行。
- `README.md` 增加“Makefile 模块化说明”，但每个流程的详细用法写入各自目录 README。
- `make help` 继续展示所有 include 进来的 `##` 目标。
- 验证不连接 EC2，只做语法、命令展开、单测和 `git diff --check`。

## 验证步骤

1. `make -n workflow-to-ls BRAND=SOFTCARE PSEUDO_LIMIT=1`
2. `make -n workflow-to-ls-llm BRAND=SOFTCARE OCR_RESUME=1`
3. `make -n workflow-to-ls-visual BRAND=SOFTCARE PSEUDO_LIMIT=1`
4. `make -n diaper-workflow-to-ls DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812`
5. `make -n diaper-ec2-train EC2_HOST=example DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812`
6. `python -m py_compile` 针对新增/修改脚本。
7. `python -m unittest discover tests`
8. `git diff --check`
