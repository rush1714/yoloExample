# Softcare YOLO 数据导入与训练准备报告

日期：2026-08-05

## 1. 本次结论

- MacBook M1 Max 32G 可以用于本地训练 YOLO 检测模型。
- 当前阶段推荐使用 `yolo26s.pt` 作为首个 baseline；如果训练太慢，再降级为 `yolo26n.pt`。
- 已从 Excel 的 `整改后图片URL` 列下载原始图片，共 **361 张**。
- 当前图片没有人工标注，不能直接用于 YOLO 训练。
- 可以使用 YOLO-World / CVAT 自动标注能力做“预标注”，但结果必须人工复核。
- 当前最关键工作不是继续换更大的模型，而是尽快形成一批高质量 Softcare 包装检测框标注。

## 2. 已完成事项

### 2.1 Excel 图片导入

输入文件：

```text
/Users/guobiao/Downloads/8e96894159cc584f0c7a27faaa4acc45.xlsx
```

读取列：

```text
整改后图片URL
```

导入结果：

| 项目 | 数量 |
| --- | ---: |
| Excel 中识别出的图片 URL | 361 |
| 成功下载图片 | 361 |
| 下载失败 | 0 |

图片保存目录：

```text
datasets/softcare/raw/images/
```

下载报告：

```text
datasets/softcare/raw/metadata/download_report.csv
datasets/softcare/raw/metadata/download_report.json
```

使用命令：

```bash
uv run python scripts/import_images_from_excel.py \
  --excel '/Users/guobiao/Downloads/8e96894159cc584f0c7a27faaa4acc45.xlsx' \
  --column '整改后图片URL' \
  --workers 8
```

### 2.2 新增/更新脚本

| 文件 | 作用 |
| --- | --- |
| `scripts/import_images_from_excel.py` | 从 Excel 指定列读取图片 URL 并下载原图。 |
| `scripts/pseudo_label_yolo_world.py` | 使用 YOLO-World 开放词汇能力生成候选框伪标注。 |
| `scripts/train.py` | 训练脚本，默认 baseline 为 `models/yolo26s.pt`，训练输出在 `models/train/`，并自动导出 `models/softcare-best.pt`。 |
| `scripts/validate_dataset.py` | 校验 YOLO 图片和标签是否一一对应。 |
| `scripts/predict.py` | 使用训练完成的模型推理并输出 Softcare 包数。 |

### 2.3 新增/更新配置

| 文件 | 作用 |
| --- | --- |
| `data/softcare.yaml` | 正式人工标注数据集配置。 |
| `data/softcare_pseudo.yaml` | 自动预标注数据集配置。 |
| `pyproject.toml` | 添加 `openpyxl`、`clip` 等依赖。 |
| `README.md` | 补充 Mac 训练建议、目录说明、Excel 导入和自动预标注流程。 |

## 3. MacBook M1 Max 32G 模型选择建议

你的 MacBook M1 Max 32G 可以训练 YOLO。训练时建议使用 Apple Silicon MPS：

```bash
uv run python scripts/train.py --device mps --imgsz 960 --batch -1
```

模型选择建议如下：

| 模型 | 推荐程度 | 适合阶段 | 说明 |
| --- | --- | --- | --- |
| `yolo26n.pt` | 可用 | 冒烟测试、快速验证流程 | 最快、显存压力最低，但包装较小或遮挡多时容易漏检。 |
| `models/yolo26s.pt` | 推荐 | 第一版 baseline | M1 Max 32G 通常可以承受，速度和准确率更平衡。当前训练脚本默认使用它。 |
| `yolo26m.pt` | 后续对比 | 有更多高质量标注后 | 训练更慢，但可能提升小目标和复杂货架场景效果。建议 1000+ 张高质量标注后再比较。 |
| `yolo26l.pt` / `yolo26x.pt` | 暂不建议 | 非首轮 PoC | 本地训练迭代慢，不适合当前只有原始未标注图片的阶段。 |

当前场景中，货架图片里的商品包装通常较小，`imgsz` 往往比模型大小更关键。推荐第一版：

```bash
uv run python scripts/train.py \
  --base-model models/yolo26s.pt \
  --epochs 100 \
  --imgsz 960 \
  --batch -1 \
  --device mps
```

如果训练太慢，可先降级为：

```bash
uv run python scripts/train.py \
  --base-model yolo26n.pt \
  --epochs 100 \
  --imgsz 640 \
  --batch -1 \
  --device mps
```

## 4. 当前目录说明

```text
datasets/softcare/
├── raw/
│   ├── images/
│   │   └── 从 Excel 下载的 361 张原始未标注图片
│   └── metadata/
│       ├── download_report.csv
│       └── download_report.json
├── images/
│   ├── train/
│   ├── val/
│   └── test/
├── labels/
│   ├── train/
│   ├── val/
│   └── test/
└── pseudo/
    ├── images/
    ├── labels/
    └── metadata/
```

目录含义：

| 目录 | 含义 | 是否可直接训练 |
| --- | --- | --- |
| `datasets/softcare/raw/images/` | Excel 下载的原始图片，没有标签。 | 否 |
| `datasets/softcare/raw/metadata/` | 下载报告。 | 否 |
| `datasets/softcare/images/train/` | 正式训练图片。 | 是，需有对应标签 |
| `datasets/softcare/images/val/` | 训练过程验证图片。 | 是，需有对应标签 |
| `datasets/softcare/images/test/` | 最终验收测试图片。 | 不参与训练，只评估 |
| `datasets/softcare/labels/train/` | train 图片对应 YOLO 标签。 | 是 |
| `datasets/softcare/labels/val/` | val 图片对应 YOLO 标签。 | 是 |
| `datasets/softcare/labels/test/` | test 图片对应 YOLO 标签。 | 用于评估 |
| `datasets/softcare/pseudo/` | 自动预标注输出，需人工复核。 | 不建议直接训练 |

关键规则：

- `raw/images/` 只是原始图片，不能直接训练。
- YOLO 训练要求每张图片都有同名 `.txt` 标签。
- `pseudo/` 只是候选标签，必须人工检查误检和漏检。
- 正式训练使用 `data/softcare.yaml`。
- 自动预标注试验使用 `data/softcare_pseudo.yaml`。

## 5. 没有标注时的自动/半自动标注方案

### 5.1 方案 A：CVAT 自动标注，推荐

建议在 CVAT 中导入：

```text
datasets/softcare/raw/images/
```

然后使用 CVAT 的自动标注能力，例如 Grounding DINO / SAM / Segment Anything 插件，先生成候选框，再人工复核。

优点：

- 有可视化界面。
- 适合多人协作和审核。
- 可以直接导出 YOLO Detection 格式。

缺点：

- 需要部署或配置模型。
- 自动标注仍然需要人工检查。

### 5.2 方案 B：YOLO-World 预标注脚本

本项目已提供脚本：

```text
scripts/pseudo_label_yolo_world.py
```

建议先小批量试跑：

```bash
uv run python scripts/pseudo_label_yolo_world.py \
  --limit 20 \
  --prompt 'softcare diaper package' \
  --prompt 'baby diaper package' \
  --prompt 'diaper package' \
  --prompt 'package' \
  --conf 0.03 \
  --imgsz 960
```

如果候选框质量可以，再全量执行：

```bash
uv run python scripts/pseudo_label_yolo_world.py \
  --raw-dir datasets/softcare/raw/images \
  --output-root datasets/softcare/pseudo \
  --prompt 'softcare diaper package' \
  --prompt 'baby diaper package' \
  --prompt 'diaper package' \
  --prompt 'package' \
  --conf 0.03 \
  --imgsz 960
```

注意：

- `softcare` 文字如果太小、模糊、反光，开放词汇模型不一定能识别。
- `package` 会提高召回率，但误检会增加。
- 预标注输出不能直接作为最终训练数据。
- 需要用 CVAT / Label Studio 打开后人工删除误检、补漏检。

### 5.3 方案 C：OCR 辅助筛选 Softcare

如果目标是先找含 `Softcare` 文字的商品，可以后续增加 OCR 辅助：

- OCR 先筛选可能包含 Softcare 的图片或区域。
- YOLO 负责最终商品框检测与计数。

限制：

- 门店货架照片中文字经常很小、反光、倾斜或遮挡。
- OCR 不能替代检测框标注。
- 更适合作为辅助筛选，不适合作为唯一识别方式。

## 6. 推荐下一步流程

### 步骤 1：先抽 20 张做自动预标注

```bash
uv run python scripts/pseudo_label_yolo_world.py \
  --limit 20 \
  --prompt 'softcare diaper package' \
  --prompt 'baby diaper package' \
  --prompt 'diaper package' \
  --prompt 'package' \
  --conf 0.03 \
  --imgsz 960
```

### 步骤 2：人工复核候选框

检查目录：

```text
datasets/softcare/pseudo/images/
datasets/softcare/pseudo/labels/
```

建议用 CVAT 或 Label Studio 打开，人工完成：

- 删除误检框。
- 补充漏检框。
- 确认每个 Softcare 包装对应一个框。

### 步骤 3：导出/复制到正式训练目录

```text
datasets/softcare/images/train
datasets/softcare/images/val
datasets/softcare/images/test

datasets/softcare/labels/train
datasets/softcare/labels/val
datasets/softcare/labels/test
```

### 步骤 4：校验正式数据集

```bash
uv run python scripts/validate_dataset.py
```

### 步骤 5：训练 baseline 模型

```bash
uv run python scripts/train.py \
  --base-model models/yolo26s.pt \
  --epochs 100 \
  --imgsz 960 \
  --batch -1 \
  --device mps
```

### 步骤 6：推理验证

```bash
uv run python scripts/predict.py \
  data/samples/softcare-shelf.webp \
  --conf 0.35
```

输出：

```text
outputs/predict/<图片名>.json
outputs/predict/<图片名>-annotated.jpg
```

## 7. 本次测试结果

执行过的验证：

```bash
uv run python -m compileall -q scripts
```

通过。

图片下载验证：

```text
raw images: 361
download report rows: 361
download statuses: downloaded
```

自动预标注脚本小样本试跑：

- 处理前 3 张图片。
- 脚本可以运行并生成 YOLO 标签结构。
- 默认较严格提示词下候选框为 0，因此后续建议加入 `package` 并降低 `--conf` 到 `0.03`，用于提高召回，再人工筛选误检。

## 8. 风险与注意事项

1. **自动预标注不能直接代替人工标注**  
   误检和漏检都会影响训练质量，必须复核。

2. **当前 361 张原图不等于 361 张训练样本**  
   只有配套标签后才是训练样本。

3. **Softcare 字样太小可能无法靠开放词汇模型稳定识别**  
   可以用 `package` 提高召回，但会带来更多误检。

4. **正式测试集不能参与训练**  
   `test` 目录只用于最终验收，否则指标会虚高。

5. **第一版目标应是快速闭环**  
   先完成 100–300 张高质量人工复核标注，训练 `models/yolo26s.pt` baseline，再根据漏检/误检样本迭代。

## 9. 模型权重目录规范更新

本次按约定将项目内已有 `.pt` 权重统一移动到 `models/`：

```text
models/yolov8s-world.pt
models/clip/ViT-B-32.pt
```

代码同步调整：

- `scripts/train.py` 默认 baseline 为 `models/yolo26s.pt`，训练输出目录改为 `models/train/`，训练完成后自动复制 `best.pt` 到 `models/softcare-best.pt`。
- `scripts/pseudo_label_yolo_world.py` 默认 YOLO-World 权重改为 `models/yolov8s-world.pt`。
- `scripts/predict.py` 默认推理权重为 `models/softcare-best.pt`。
- 训练、预标注、推理脚本启动时会将 Ultralytics `weights_dir` 指向 `models/`，后续自动下载的 YOLO/CLIP `.pt` 权重也会尽量落到 `models/`。
- 命令中传入 `yolo26s.pt`、`yolov8s-world.pt` 这类裸文件名时，脚本会自动解析到 `models/<文件名>`。

## 10. OCR 辅助筛选方案更新

本次新增 OCR 辅助筛选，用于在原始图片中优先找出疑似包含 `Softcare` 字样的图片。

### 10.1 方案选择

| 方案 | 定位 | 说明 |
| --- | --- | --- |
| PaddleOCR / PP-OCR | 生产推荐 | 中文、复杂场景和工程化能力较成熟，适合后续服务化。 |
| RapidOCR ONNX | 当前 PoC 默认集成 | 基于 PP-OCR 思路，CPU 推理快，Mac 本地无需额外下载 EasyOCR 检测模型。 |
| EasyOCR | 备选引擎 | Python 集成简单，但首次运行需要下载检测模型，本地网络慢时可能耗时较长。 |

当前项目默认集成 RapidOCR ONNX，原因是启动快、CPU 推理可用、能直接嵌入现有 Python 脚本。后续如果 OCR 成为生产链路，建议进一步评估 PaddleOCR。

### 10.2 当前实现

新增脚本：

```text
scripts/ocr_filter_softcare.py
```

输入：

```text
datasets/softcare/raw/images/
```

输出：

```text
datasets/softcare/ocr/metadata/ocr_softcare_report.csv
datasets/softcare/ocr/metadata/ocr_softcare_report.json
datasets/softcare/ocr/metadata/ocr_candidates.txt
```

目录：

```text
datasets/softcare/ocr/
├── candidates/      # 可选：复制出来的 OCR 命中候选图片
└── metadata/        # OCR 报告和候选清单
```

小样本试跑命令：

```bash
uv run python scripts/ocr_filter_softcare.py \
  --limit 20 \
  --engine rapidocr \
  --keyword softcare \
  --keyword 'soft care' \
  --fuzzy-threshold 60 \
  --min-confidence 0.2
```

全量命令：

```bash
uv run python scripts/ocr_filter_softcare.py \
  --raw-dir datasets/softcare/raw/images \
  --engine rapidocr \
  --keyword softcare \
  --keyword 'soft care' \
  --fuzzy-threshold 60 \
  --min-confidence 0.2
```

### 10.3 与自动预标注集成

`pseudo_label_yolo_world.py` 已支持读取 OCR 候选清单：

```bash
uv run python scripts/pseudo_label_yolo_world.py \
  --raw-dir datasets/softcare/raw/images \
  --output-root datasets/softcare/pseudo \
  --candidates-file datasets/softcare/ocr/metadata/ocr_candidates.txt \
  --prompt 'softcare diaper package' \
  --prompt 'baby diaper package' \
  --prompt 'diaper package' \
  --prompt 'package' \
  --conf 0.03 \
  --imgsz 960
```

这样流程变为：

```text
raw/images 原图
  -> OCR 筛选 Softcare 候选图
  -> YOLO-World 只优先处理候选图
  -> pseudo 候选框
  -> CVAT/Label Studio 人工复核
  -> 正式 YOLO 数据集
```

### 10.4 风险

- OCR 命中只代表“可能有 Softcare”，不能直接得到准确商品框。
- OCR 未命中不代表图片一定没有 Softcare，不能删除未命中图片。
- 货架图片里的品牌字常常很小、模糊、反光或倾斜，OCR 召回率可能有限。
- OCR 适合提高优先级和减少人工查找成本，不适合作为唯一识别依据。

### 10.5 本次测试结果

已完成测试：

```bash
uv run python -m compileall -q scripts
uv run python scripts/ocr_filter_softcare.py --limit 2 --engine rapidocr --keyword softcare --keyword 'soft care' --fuzzy-threshold 60 --min-confidence 0.2
```

OCR 小样本结果：

```text
processed=2, matched=2
row00002_1d59f9162b2f.webp: Soltcare，score=73.04
row00002_78e277790497.webp: Saftcare，score=78.31
```

全量 OCR 筛选结果：

```text
processed=361
matched=171
候选清单：datasets/softcare/ocr/metadata/ocr_candidates.txt
```

部分命中样例：

```text
Soltcare / Saftcare / Softcare / SOFT / SOFT&SA / Kleesoft / esoft
```

说明：RapidOCR 能在样本中识别出接近 `Softcare` 的文本，但存在 `Soltcare`、`Saftcare` 这类 OCR 误读，也会因为模糊匹配召回 `Kleesoft`、`Soap` 等可能误检文本，因此脚本使用 `rapidfuzz` 做模糊匹配，输出仍需要人工复核。

预标注候选清单集成测试：

```bash
uv run python scripts/pseudo_label_yolo_world.py --candidates-file <候选清单> --limit 1 --conf 0.03 --imgsz 640
```

结果：脚本可以正确读取候选清单并只处理候选图片；测试样本候选框为 0，仍需人工复核和调参。

### 10.6 架构文档同步

已同步更新：

```text
设计.md
CLAUDE.md
README.md
```

新增约定：后续如果识别方案、数据流程、训练流程、OCR/YOLO/多模态架构发生优化或调整，必须同步更新 `设计.md`，确保架构文档与当前实现一致。
