# EC2 PyTorch 环境训练、验证与产物归档流程

## 已知环境

- EC2 已有 PyTorch 环境，进入方式：`source /opt/pytorch/bin/activate`。
- EC2 已安装：`python3 -m pip install -U ultralytics`。
- 本次不校验 EC2 SSH 连通性，只校验本地代码语法和 Makefile 命令展开。

## 目标

在现有 `diaper-category-ec2` 模块基础上补齐“训练后验证与效果分析”闭环：

1. EC2 远程命令默认先激活 `/opt/pytorch/bin/activate`，再执行 Python/Ultralytics。
2. 支持三档训练计划：
   - `smoke`：`yolo11n.pt`，`imgsz=640`，`epochs=5`，用于验证数据集格式和训练链路。
   - `baseline`：`yolo11s.pt`，`imgsz=960`，`epochs=100`，用于建立基线。
   - `improve`：`yolo11m.pt`，`imgsz=960`，`epochs=150` 默认，可覆盖为 100~150，用于对比提升。
3. 首轮 PoC 建议只投入 300~500 张有效标注图，先验证闭环，再扩大数据。
4. 每次重要训练完成后，将关键产物导出到可下载目录，并生成/更新 `evaluation-summary.md`：
   - 训练参数：profile、模型、imgsz、epochs、batch、device、数据集路径、标签数量。
   - 训练指标：读取 `results.csv`、`args.yaml` 等，汇总 best epoch、precision、recall、mAP50、mAP50-95 等能读到的字段。
   - 验证/推理产物：`weights/best.pt`、`weights/last.pt`、`results.csv`、`args.yaml`、`confusion_matrix.*`、PR/P/R/F1 曲线、预测可视化图。
   - 人工复核输出图：从 predict/val 输出中复制带框图片到归档目录。
   - 按问题类型归类：准备 `review/{false_positive,false_negative,wrong_class,duplicate_box,bad_image,annotation_issue,ok}/` 目录，便于人工把问题图片分类。
5. 增加下载 EC2 训练关键产物的命令，不只下载 best.pt。

## 拟新增/修改脚本

### 1. 修改 `scripts/cloud/ec2_diaper_workflow.py`

新增或调整参数：

- `--activate-cmd`：默认 `source /opt/pytorch/bin/activate`。
- `--profile`：`smoke | baseline | improve | custom`。
- `--train-command`：远端 Python 命令默认 `python3`，因为环境已通过 activate 准备好。
- `--artifact-root`：EC2 上训练归档目录，例如 `artifacts/diaper_category/<country>/<version>/<profile>/`。
- `--download-artifacts` action：下载整个归档目录。

远程命令统一包装为：

```bash
cd <EC2_PROJECT_ROOT> && source /opt/pytorch/bin/activate && python3 ...
```

训练 profile 映射：

```text
smoke    -> model=yolo11n.pt, imgsz=640, epochs=5
baseline -> model=yolo11s.pt, imgsz=960, epochs=100
improve  -> model=yolo11m.pt, imgsz=960, epochs=150
custom   -> 使用命令行传入 EC2_BASE_MODEL/EC2_TRAIN_IMGSZ/EC2_TRAIN_EPOCHS
```

### 2. 新增 `scripts/reports/summarize_yolo_run.py`

用途：在 EC2 或本地读取 Ultralytics run 目录，生成 `evaluation-summary.md`。

输入：

- `--run-dir models/train/<run_name>`
- `--dataset-yaml config/generated/...yaml`
- `--artifact-dir artifacts/diaper_category/<country>/<version>/<profile>`
- `--profile smoke|baseline|improve|custom`
- `--notes` 可选备注

输出：

```text
artifact-dir/
├── evaluation-summary.md
├── weights/best.pt
├── weights/last.pt
├── metrics/results.csv
├── metrics/args.yaml
├── plots/*.png|*.jpg
└── review/
    ├── false_positive/
    ├── false_negative/
    ├── wrong_class/
    ├── duplicate_box/
    ├── bad_image/
    ├── annotation_issue/
    └── ok/
```

脚本应只依赖标准库，方便 EC2 环境运行。

### 3. 可选增强 `scripts/inference/predict.py`

如果当前推理脚本只支持单图，则保留；EC2 侧先使用 Ultralytics `val` 与 train 产生的 plots。若需要批量导出人工复核图片，再新增独立脚本，不阻塞本轮。

## Makefile 模块调整

修改 `makefiles/diaper-category-ec2/Makefile.mk`：

新增变量：

- `EC2_ACTIVATE_CMD ?= source /opt/pytorch/bin/activate`
- `EC2_PYTHON_CMD ?= python3`
- `EC2_TRAIN_PROFILE ?= smoke`
- `EC2_ARTIFACT_ROOT ?= artifacts/diaper_category/$(DIAPER_COUNTRY)/$(DIAPER_VERSION)/$(EC2_TRAIN_PROFILE)`
- `EC2_LOCAL_ARTIFACT_ROOT ?= outputs/ec2/diaper_category/$(DIAPER_COUNTRY)/$(DIAPER_VERSION)/$(EC2_TRAIN_PROFILE)`
- profile 派生默认：根据 `EC2_TRAIN_PROFILE` 生成 `EC2_BASE_MODEL`、`EC2_TRAIN_IMGSZ`、`EC2_TRAIN_EPOCHS`。

新增/调整命令：

- `diaper-ec2-train-smoke`
- `diaper-ec2-train-baseline`
- `diaper-ec2-train-improve`
- `diaper-ec2-evaluate`：远端归档训练结果并生成 `evaluation-summary.md`。
- `diaper-ec2-download-artifacts`：下载完整归档目录。
- 保留 `diaper-ec2-train`，按 `EC2_TRAIN_PROFILE` 执行。
- 保留 `diaper-ec2-download-model`，只下载 best.pt。

## 文档更新

- 更新 `makefiles/diaper-category-ec2/README.md`：
  - 写清 EC2 环境前提：`source /opt/pytorch/bin/activate`，已安装 ultralytics。
  - 写清 smoke/baseline/improve 三档表格。
  - 写清首轮 PoC 只建议 300~500 张。
  - 写清训练后必须执行 evaluation 和下载 artifacts。
  - 写清 review 目录问题分类规则。
- 更新根 `README.md` 的纸尿裤 EC2 章节。
- 更新 `设计.md` 的 EC2 训练闭环。
- 更新 `docs/reports/2026-08-12-diaper-category-ec2-workflow.md`。

## 验证

- 不连接 EC2。
- 运行 Python 编译检查：新增/修改脚本。
- 运行单元测试：至少覆盖 profile 映射、远程命令包含 activate、summary 生成、artifact 目录结构。
- 运行 Make dry-run：
  - `make -n diaper-ec2-train-smoke EC2_HOST=example`
  - `make -n diaper-ec2-train-baseline EC2_HOST=example`
  - `make -n diaper-ec2-train-improve EC2_HOST=example`
  - `make -n diaper-ec2-evaluate EC2_HOST=example`
  - `make -n diaper-ec2-download-artifacts EC2_HOST=example`
- `git diff --check`。
