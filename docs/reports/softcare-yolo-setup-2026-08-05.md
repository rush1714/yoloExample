NLTK_DISABLE_IMPORT_SECURITY=1
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
datasets/multibrand/raw/images/
```

下载报告：

```text
datasets/multibrand/raw/metadata/download_report.csv
datasets/multibrand/raw/metadata/download_report.json
```

命名规则更新：图片文件名改为 `row<Excel行号>_<原附件名称>.<后缀>`，例如 `row00002_67cfc8156160c2fd227aef004b771854.webp`。原附件名称本身是业务侧 hash 且唯一，因此不再使用完整 URL 的 SHA1 前 12 位。

使用命令：

```bash
uv run python scripts/data_import/import_images_from_excel.py \
  --excel '/Users/guobiao/Downloads/8e96894159cc584f0c7a27faaa4acc45.xlsx' \
  --column '整改后图片URL' \
  --workers 8
```

### 2.2 新增/更新脚本

| 文件 | 作用 |
| --- | --- |
| `scripts/data_import/import_images_from_excel.py` | 从 Excel 指定列读取图片 URL 并下载原图。 |
| `scripts/pseudo_label/generate_yolo_world.py` | 使用 YOLO-World 开放词汇能力生成候选框伪标注。 |
| `scripts/training/train.py` | 训练脚本，默认 baseline 为 `models/yolo26s.pt`，训练输出在 `models/train/`，并自动导出 `models/multibrand-best.pt`。 |
| `scripts/training/validate_dataset.py` | 校验 YOLO 图片和标签是否一一对应。 |
| `scripts/inference/predict.py` | 使用训练完成的模型推理并输出 Softcare 包数。 |

### 2.3 新增/更新配置

| 文件 | 作用 |
| --- | --- |
| `data/multibrand.yaml` | 正式人工标注数据集配置。 |
| `data/multibrand_pseudo.yaml` | 自动预标注数据集配置。 |
| `pyproject.toml` | 添加 `openpyxl`、`clip` 等依赖。 |
| `README.md` | 补充 Mac 训练建议、目录说明、Excel 导入和自动预标注流程。 |

## 3. MacBook M1 Max 32G 模型选择建议

你的 MacBook M1 Max 32G 可以训练 YOLO。训练时建议使用 Apple Silicon MPS：

```bash
uv run python scripts/training/train.py --device mps --imgsz 960 --batch -1
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
uv run python scripts/training/train.py \
  --base-model models/yolo26s.pt \
  --epochs 100 \
  --imgsz 960 \
  --batch -1 \
  --device mps
```

如果训练太慢，可先降级为：

```bash
uv run python scripts/training/train.py \
  --base-model yolo26n.pt \
  --epochs 100 \
  --imgsz 640 \
  --batch -1 \
  --device mps
```

## 4. 当前目录说明

```text
datasets/multibrand/
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
| `datasets/multibrand/raw/images/` | Excel 下载的原始图片，没有标签。 | 否 |
| `datasets/multibrand/raw/metadata/` | 下载报告。 | 否 |
| `datasets/multibrand/images/train/` | 正式训练图片。 | 是，需有对应标签 |
| `datasets/multibrand/images/val/` | 训练过程验证图片。 | 是，需有对应标签 |
| `datasets/multibrand/images/test/` | 最终验收测试图片。 | 不参与训练，只评估 |
| `datasets/multibrand/labels/train/` | train 图片对应 YOLO 标签。 | 是 |
| `datasets/multibrand/labels/val/` | val 图片对应 YOLO 标签。 | 是 |
| `datasets/multibrand/labels/test/` | test 图片对应 YOLO 标签。 | 用于评估 |
| `datasets/multibrand/pseudo/` | 自动预标注输出，需人工复核。 | 不建议直接训练 |

关键规则：

- `raw/images/` 只是原始图片，不能直接训练。
- YOLO 训练要求每张图片都有同名 `.txt` 标签。
- `pseudo/` 只是候选标签，必须人工检查误检和漏检。
- 正式训练使用 `data/multibrand.yaml`。
- 自动预标注试验使用 `data/multibrand_pseudo.yaml`。

## 5. 没有标注时的自动/半自动标注方案

### 5.1 方案 A：CVAT 自动标注，推荐

建议在 CVAT 中导入：

```text
datasets/multibrand/raw/images/
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
scripts/pseudo_label/generate_yolo_world.py
```

建议先小批量试跑：

```bash
uv run python scripts/pseudo_label/generate_yolo_world.py \
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
uv run python scripts/pseudo_label/generate_yolo_world.py \
  --raw-dir datasets/multibrand/raw/images \
  --output-root datasets/multibrand/pseudo \
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
uv run python scripts/pseudo_label/generate_yolo_world.py \
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
datasets/multibrand/pseudo/images/
datasets/multibrand/pseudo/labels/
```

建议用 CVAT 或 Label Studio 打开，人工完成：

- 删除误检框。
- 补充漏检框。
- 确认每个 Softcare 包装对应一个框。

### 步骤 3：导出/复制到正式训练目录

```text
datasets/multibrand/images/train
datasets/multibrand/images/val
datasets/multibrand/images/test

datasets/multibrand/labels/train
datasets/multibrand/labels/val
datasets/multibrand/labels/test
```

### 步骤 4：校验正式数据集

```bash
uv run python scripts/training/validate_dataset.py
```

### 步骤 5：训练 baseline 模型

```bash
uv run python scripts/training/train.py \
  --base-model models/yolo26s.pt \
  --epochs 100 \
  --imgsz 960 \
  --batch -1 \
  --device mps
```

### 步骤 6：推理验证

```bash
uv run python scripts/inference/predict.py \
  data/samples/multibrand-shelf.webp \
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

- `scripts/training/train.py` 默认 baseline 为 `models/yolo26s.pt`，训练输出目录改为 `models/train/`，训练完成后自动复制 `best.pt` 到 `models/multibrand-best.pt`。
- `scripts/pseudo_label/generate_yolo_world.py` 默认 YOLO-World 权重改为 `models/yolov8s-world.pt`。
- `scripts/inference/predict.py` 默认推理权重为 `models/multibrand-best.pt`。
- 训练、预标注、推理脚本启动时会将 Ultralytics `weights_dir` 指向 `models/`，后续自动下载的 YOLO/CLIP `.pt` 权重也会尽量落到 `models/`。
- 命令中传入 `yolo26s.pt`、`yolov8s-world.pt` 这类裸文件名时，脚本会自动解析到 `models/<文件名>`。

## 10. Label Studio 导入与人工复核更新

### 10.1 最新文档要点

通过 Context7 查询 Label Studio / Label Studio SDK 最新文档后，确认推荐导入方式：

- HTTP API 使用 Personal Access Token，认证头为 `Authorization: Bearer <token>`。
- legacy token 认证头为 `Authorization: Token <token>`，但当前本地 Label Studio 1.23 已禁用 legacy token。
- 对图片目标检测任务，Label Studio 的矩形框结果使用百分比坐标：`x`、`y`、`width`、`height` 都是 0–100。
- 预标注应放在任务的 `predictions` 字段中，结果类型为 `rectanglelabels`。

当前本地实例：

```text
Label Studio URL: http://localhost:9001
Version: 1.23.0
```

因为当前没有可用 Personal Access Token，且 legacy token 被禁用，所以本次采用本地 `label-studio shell` 写入当前实例。

### 10.2 新增脚本

| 脚本 | 作用 |
| --- | --- |
| `scripts/label_studio/generate_import.py` | 生成 Label Studio 标准任务 JSON；图片使用本地文件服务路径 `/data/local-files/?d=<absolute_path>`；YOLO 伪标注转换为 `predictions`。 |
| `scripts/label_studio/apply_import.py` | 通过本地 Label Studio Django shell 创建项目、任务、prediction 和 Local Files storage 权限记录。 |

生成导入 JSON：

```bash
uv run python scripts/label_studio/generate_import.py
```

输出：

```text
datasets/multibrand/label_studio/multibrand_label_studio_import.json
```

生成结果：

```text
tasks=361
tasks_with_predictions=153
prediction_boxes=1102
```

导入命令：

```bash
cd /tmp && PYTHONSAFEPATH=1 \
  /Users/guobiao/PRO/me/yoloExample/.venv/bin/label-studio shell <<'PY'
exec(open('/Users/guobiao/PRO/me/yoloExample/scripts/label_studio/apply_import.py', encoding='utf-8').read())
PY
```

### 10.3 导入结果

历史已导入项目：

```text
project_id=2
project_title=Softcare Diaper Review - 2026-08-05
url=http://localhost:9001/projects/2/data
tasks=361
tasks_with_predictions=153
predictions=153
prediction_boxes=1102
```

Review 后脚本会在重新执行 `make ls-apply` 时创建新项目，并输出新的 `project_id`、项目地址、Local Files storage ID。

说明：

- 361 个任务对应 Excel 下载的 361 张原图。
- 153 个任务带 YOLO-World 预标注预测。
- 1102 个候选框需要在 Label Studio 中人工删除误检、补充漏检。
- 图片字段使用本地文件服务路径 `/data/local-files/?d=<absolute_path>`，避免远程 CDN CORS 问题。`source_url` 保留原始 URL，`local_path` 和 `row_number` 作为辅助字段。

### 10.4 后续操作

在 Label Studio 中打开 `make ls-apply` 输出的项目地址；历史项目地址为：

```text
http://localhost:9001/projects/2/data
```

人工复核流程：

1. 检查已有 `softcare_diaper` 预标注框。
2. 删除误检框。
3. 补充漏检的 Softcare 纸尿裤包装框。
4. 每包可辨认 Softcare 包装保留一个矩形框。
5. 导出 YOLO Detection 格式。
6. 将导出结果整理到正式训练目录：

```text
datasets/multibrand/images/train|val|test
datasets/multibrand/labels/train|val|test
```

## 11. OCR 辅助筛选方案更新

本次新增 OCR 辅助筛选，用于在原始图片中优先找出疑似包含目标品牌字样的图片。2026-08-06 已进一步增加品牌标识库 `data/brand_keywords.json`，OCR 与 YOLO-World 预标注默认共用该品牌库。

### 11.1 方案选择

| 方案 | 定位 | 说明 |
| --- | --- | --- |
| PaddleOCR / PP-OCR | 生产推荐 | 中文、复杂场景和工程化能力较成熟，适合后续服务化。 |
| RapidOCR ONNX | 当前 PoC 默认集成 | 基于 PP-OCR 思路，CPU 推理快，Mac 本地无需额外下载 EasyOCR 检测模型。 |
| EasyOCR | 备选引擎 | Python 集成简单，但首次运行需要下载检测模型，本地网络慢时可能耗时较长。 |

当前项目默认集成 RapidOCR ONNX，原因是启动快、CPU 推理可用、能直接嵌入现有 Python 脚本。后续如果 OCR 成为生产链路，建议进一步评估 PaddleOCR。

### 11.2 当前实现

新增/更新文件：

```text
scripts/ocr/filter_brand_candidates.py
data/brand_keywords.json
```

品牌库当前包含：`KLEESOFT`、`SOFTCARE`、`DOFFI`、`LAVITA`、`NICEDAY`、`MOSSE`、`MAYA`、`CLINCLEER`、`VEESPER`、`CUETTIE`、`T-GUARD`、`ATHENA`、`MCGEL`、`FASKIT`、`DR.X`、`Avril`、`DIAMOND`、`JIEBAI`、`MEDIPOWER`、`KINPOWER`。脚本自动忽略用户原始清单中的数字序号、重复项和 `★` 纯符号。

输入：

```text
datasets/multibrand/raw/images/
```

输出：

```text
datasets/multibrand/ocr/metadata/ocr_softcare_report.csv
datasets/multibrand/ocr/metadata/ocr_softcare_report.json
datasets/multibrand/ocr/metadata/ocr_candidates.txt
```

目录：

```text
datasets/multibrand/ocr/
├── candidates/      # 可选：复制出来的 OCR 命中候选图片
└── metadata/        # OCR 报告和候选清单
```

小样本试跑命令：

```bash
uv run python scripts/ocr/filter_brand_candidates.py \
  --raw-dir datasets/multibrand/raw/images \
  --brand-library data/brand_keywords.json \
  --limit 20 \
  --engine rapidocr \
  --fuzzy-threshold 60 \
  --min-confidence 0.2
```

全量命令：

```bash
uv run python scripts/ocr/filter_brand_candidates.py \
  --raw-dir datasets/multibrand/raw/images \
  --brand-library data/brand_keywords.json \
  --engine rapidocr \
  --fuzzy-threshold 60 \
  --min-confidence 0.2
```

### 11.3 与自动预标注集成

`pseudo_label_yolo_world.py` 已支持读取 OCR 候选清单：

```bash
uv run python scripts/pseudo_label/generate_yolo_world.py \
  --raw-dir datasets/multibrand/raw/images \
  --output-root datasets/multibrand/pseudo \
  --candidates-file datasets/multibrand/ocr/metadata/ocr_candidates.txt \
  --brand-library data/brand_keywords.json \
  --brand-filter SOFTCARE \
  --include-brand-package-prompts \
  --prompt package \
  --nms-iou 0.45 \
  --containment-threshold 0.85 \
  --max-area-ratio 0.45 \
  --conf 0.03 \
  --imgsz 960
```

这样流程变为：

```text
raw/images 原图
  -> OCR 按品牌标识库筛选候选图
  -> YOLO-World 默认只用 SOFTCARE 目标品牌提示词并优先处理候选图
  -> NMS/覆盖过滤/最大面积过滤减少重复框和整图大框
  -> pseudo 候选框
  -> CVAT/Label Studio 人工复核
  -> 正式 YOLO 数据集
```

### 11.4 风险

- OCR 命中只代表“可能有目标品牌”，不能直接得到准确商品框。
- OCR 未命中不代表图片一定没有目标品牌，不能删除未命中图片。
- 货架图片里的品牌字常常很小、模糊、反光或倾斜，OCR 召回率可能有限。
- OCR 适合提高优先级和减少人工查找成本，不适合作为唯一识别依据。

### 11.5 本次测试结果

已完成测试：

```bash
uv run python -m compileall -q scripts
uv run python scripts/ocr/filter_brand_candidates.py --limit 2 --engine rapidocr --keyword softcare --keyword 'soft care' --fuzzy-threshold 60 --min-confidence 0.2
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
候选清单：datasets/multibrand/ocr/metadata/ocr_candidates.txt
```

部分命中样例：

```text
Soltcare / Saftcare / Softcare / SOFT / SOFT&SA / Kleesoft / esoft
```

说明：RapidOCR 能在样本中识别出接近 `Softcare` 的文本，但存在 `Soltcare`、`Saftcare` 这类 OCR 误读，也会因为模糊匹配召回 `Kleesoft`、`Soap` 等可能误检文本，因此脚本使用 `rapidfuzz` 做模糊匹配，输出仍需要人工复核。

预标注候选清单集成测试：

```bash
uv run python scripts/pseudo_label/generate_yolo_world.py --candidates-file <候选清单> --limit 1 --conf 0.03 --imgsz 640
```

结果：脚本可以正确读取候选清单并只处理候选图片；测试样本候选框为 0，仍需人工复核和调参。

2026-08-06 品牌标识库测试：

```text
ocr_count=20
contains_digits=False
contains_star=False
prompt_count=62
```

说明：OCR 与预标注脚本均能读取 `data/brand_keywords.json`；纯数字序号、重复品牌和 `★` 纯符号已被过滤。Review 后确认：全品牌提示词会把其它品牌/整排货架也作为 `softcare_diaper` 候选，造成大框覆盖小框和重复框；因此 Makefile 默认使用 `PSEUDO_BRAND_FILTER_ARGS=--brand-filter SOFTCARE`，并增加 `PSEUDO_NMS_IOU`、`PSEUDO_CONTAINMENT`、`PSEUDO_MAX_AREA_RATIO` 过滤重复框和整图大框。

2026-08-06 预标注重复框修复测试：

```text
修复前：全品牌库 + 品牌包装提示词，小样本 1 张生成 17 个框，包含 LAVITA/NICEDAY 等非目标品牌大框和接近整图框。
修复后：SOFTCARE 目标品牌过滤 + package + NMS/覆盖/最大面积过滤，小样本 1 张生成 4 个候选框，去除了整图大框和其它品牌大框。
```

### 11.6 架构文档同步

已同步更新：

```text
设计.md
CLAUDE.md
README.md
```

新增约定：后续如果识别方案、数据流程、训练流程、OCR/YOLO/多模态架构发生优化或调整，必须同步更新 `设计.md`，确保架构文档与当前实现一致。

## 12. Label Studio 启动配置优化：PostgreSQL + 本地文件服务 + Makefile

### 12.1 问题背景

之前 Label Studio 导入的 JSON 中 `image` 字段使用远程 CDN URL（`https://uat-smdp4cust-cdn.globaltradecoo.com/...`），浏览器加载图片时 CDN 不允许来自 `http://localhost:9001` 的跨域请求，导致：

```text
[Error] Failed to load resource: Origin http://localhost:9001 is not allowed by Access-Control-Allow-Origin
```

### 12.2 解决方案

1. **图片改用本地文件服务路径**：`import_label_studio.py` 生成的 JSON 中 `image` 字段改为 `/data/local-files/?d=<absolute_path>`，Label Studio 通过内置的本地文件服务直接提供图片，不再依赖外部 CDN。
2. **数据库改用 PostgreSQL**：替换默认的 SQLite，提升并发性能和数据可靠性。
3. **创建 Local Files storage 权限记录**：Label Studio 1.23 的 `/data/local-files/` 端点不仅要求开启本地文件服务，还要求项目绑定对应 Local Files storage；`make ls-apply` 会自动注册 `datasets/multibrand/raw/images/`。
4. **Makefile 一键启动**：封装所有环境变量和启动参数，简化操作。

### 12.3 新增文件

| 文件 | 作用 |
| --- | --- |
| `Makefile` | 封装 Label Studio 数据库初始化、启动、停止、检查、导入等命令 |

### 12.4 修改文件

| 文件 | 变更 |
| --- | --- |
| `scripts/label_studio/generate_import.py` | `image` 字段从远程 URL 改为 URL 编码后的 `/data/local-files/?d=<absolute_path>` |
| `scripts/label_studio/apply_import.py` | 导入时创建 Local Files storage，并为每个任务创建本地文件 storage link，确保图片端点有项目权限 |

### 12.5 环境变量配置

通过 Makefile 自动设置以下环境变量：

```text
LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=/
NLTK_DISABLE_IMPORT_SECURITY=1
DJANGO_DB=postgresql
POSTGRE_USER=guobiao
POSTGRE_NAME=labelstudio
POSTGRE_HOST=localhost
POSTGRE_PORT=5432
```

### 12.6 Make 命令

当前 Makefile 已按业务顺序补齐 1–7 步主流程，参数都有默认值，并可在命令行覆盖：

| 顺序 | 命令 | 作用 |
| --- | --- | --- |
| 1 | `make step-1-import-excel` | 从 Excel 下载原始图片。 |
| 2 | `make step-2-ocr` | OCR 识别并生成候选清单。 |
| 3 | `make step-3-pseudo-label` | YOLO-World 预标注。 |
| 4 | `make step-4-import-ls` | 生成 Label Studio JSON 并导入本地 LS。 |
| 5 | `make step-5-export-ls-to-train LS_PROJECT_ID=<项目ID>` | 导出 Label Studio JSON 并转换为正式 YOLO 训练集。 |
| 6 | `make step-6-train` | 校验后训练模型。 |
| 7 | `make step-7-validate` | 校验正式数据集并执行一次推理验证。 |

常用辅助命令：

| 命令 | 作用 |
| --- | --- |
| `make help` | 显示所有可用命令，并附带常用参数默认值、可选值和调参效果 |
| `make help-params` | 只显示 Make 参数说明 |
| `make workflow-to-ls` | 执行步骤 1–4，到 Label Studio 导入完成 |
| `make workflow-after-ls LS_PROJECT_ID=<项目ID>` | 人工复核后执行步骤 5–7 |
| `make ls-setup` | 首次初始化 PostgreSQL 数据库并执行迁移 |
| `make ls-start` | 后台启动 Label Studio（端口 9001，PostgreSQL，本地文件服务），日志写入 `logs/label-studio.log` |
| `make ls-stop` | 停止 Label Studio，并清理 `logs/label-studio.pid` |
| `make ls-migrate` | 执行 Django 数据库迁移（首次使用需要） |
| `make ls-shell` | 进入 Label Studio Django shell |
| `make ls-export LS_PROJECT_ID=<项目ID>` | 从 Label Studio 导出 JSON |
| `make ls-to-yolo` | 将 Label Studio JSON 转换为 `datasets/multibrand/images|labels/` |
| `make ls-db-create` | 如果 PostgreSQL 数据库不存在则创建 |
| `make ls-db-check` | 检查 PostgreSQL 数据库连接 |

关键默认参数：`EXCEL`、`EXCEL_COLUMN`、`RAW_DIR`、`OCR_ENGINE`、`OCR_MIN_CONFIDENCE`、`OCR_FUZZY_THRESHOLD`、`OCR_LIMIT`、`PSEUDO_BRAND_FILTER_ARGS`、`PSEUDO_CONF`、`PSEUDO_NMS_IOU`、`PSEUDO_CONTAINMENT`、`PSEUDO_MAX_AREA_RATIO`、`PSEUDO_LIMIT`、`LS_PROJECT_ID`、`LS_EXPORT_PATH`、`TRAIN_EPOCHS`、`TRAIN_DEVICE`、`PREDICT_SOURCE`。示例：`make step-6-train TRAIN_EPOCHS=50 TRAIN_DEVICE=cpu`。完整说明可执行 `make help-params`。

### 12.7 首次使用流程

```bash
# 0. 创建 PostgreSQL 数据库并执行数据库迁移
make ls-setup

# 1-4. Excel 下载 -> OCR -> 预标注 -> 导入 Label Studio
make workflow-to-ls

# 后台启动 Label Studio，打开 make ls-apply 输出的项目地址做人工复核
make ls-start

# 可选：查看启动日志
tail -f logs/label-studio.log

# 人工复核完成后，导出、转换正式训练集、训练和验证
make workflow-after-ls LS_PROJECT_ID=<项目ID>
```

说明：Label Studio shell/start 的工作目录已改为项目内 `.tmp/label-studio/`，不再使用 `/tmp`。

### 12.8 测试结果

- PostgreSQL 数据库 `labelstudio` 连接正常。
- 导入 JSON 中 `image` 字段已改为 `/data/local-files/?d=/Users/guobiao/PRO/me/yoloExample/datasets/multibrand/raw/images/...`。
- 重新生成 JSON：`tasks=361, tasks_with_predictions=153, prediction_boxes=1102`。
- Review 后修复 Makefile `ls-stop` 目标中的括号错误，`make help`、`make -n ls-stop`、`make -n ls-apply` 均可正常解析。
- Review 后确认 Label Studio 1.23 本地文件服务要求 Local Files storage 权限；已更新 `scripts/label_studio/apply_import.py`，导入项目时自动创建 storage 和 storage link。
- 已验证运行时配置：`DJANGO_DB=postgresql`、数据库名 `labelstudio`、`LOCAL_FILES_SERVING_ENABLED=True`、`LOCAL_FILES_DOCUMENT_ROOT=/`。
- 2026-08-06 更新：`make ls-start` 已改为后台启动，日志写入 `logs/label-studio.log`，PID 写入 `logs/label-studio.pid`；重复执行会提示已有 PID，不会重复启动；`make ls-stop` 会停止进程并清理 PID 文件。
- 2026-08-06 更新：Makefile 已补齐 1–7 步顺序化目标、`workflow-to-ls` 和 `workflow-after-ls` 组合目标；新增 `scripts/label_studio/export_to_yolo.py`，用于将 Label Studio JSON 导出转换为正式 YOLO 训练集；Label Studio 命令工作目录改为项目内 `.tmp/label-studio/`。
- 2026-08-06 更新：`make help` 已扩展为同时展示命令和常用参数说明，新增 `make help-params` 单独展示所有关键参数的默认值、可选值和调参影响；Makefile 顶部也补充了逐项中文注释。
- 2026-08-06 更新：已完成多品牌多类别改造。`data/brand_keywords.json` 成为统一类别来源，新增 `scripts/common/brand_library.py` 和 `scripts/config/write_brand_yolo_yaml.py`；`make brand-yaml` 会生成多品牌 `data/multibrand.yaml`、`data/multibrand_pseudo.yaml`；YOLO-World 预标注按品牌写入不同 class_id；Label Studio 导入项目自动生成 20 个品牌标签；Label Studio 导出转 YOLO 会按品牌标签写多类别标签；推理输出改为 `brand_counts` 和 `total_count`。
- 2026-08-06 更新：完成多品牌目录重构。数据根目录从 `datasets/softcare/` 迁移为 `datasets/multibrand/`；YAML 从 `data/softcare*.yaml` 迁移为 `data/multibrand*.yaml`；脚本按流程归类到 `scripts/data_import/`、`scripts/ocr/`、`scripts/pseudo_label/`、`scripts/label_studio/`、`scripts/training/`、`scripts/inference/`、`scripts/config/`、`scripts/common/`。
- 2026-08-06 更新：修复多品牌预标注跨品牌重叠框问题。`scripts/pseudo_label/generate_yolo_world.py` 新增 `--cross-brand-dedup`、`--cross-brand-iou`、`--cross-brand-containment`；Makefile 默认启用跨品牌去重。1 张样本对比：未启用跨品牌去重时 8 个框，启用后减少到 4 个框，去除了 LAVITA/KINPOWER 等覆盖同一位置的重复候选。
- 2026-08-06 更新：`scripts/data_import/import_images_from_excel.py` 的原图命名规则从 `行号 + URL SHA1 前 12 位` 改为 `行号 + 原附件名称`，保持与业务附件 hash 文件名一致，便于和上游附件追踪。
- 2026-08-06 更新：Makefile 新增 `datasets-clean-preview` 和 `datasets-clean-ignored`。前者预览 `datasets/` 下会被 `.gitignore` 忽略并清理的文件，后者执行 `git clean -fdX -- datasets/` 删除这些生成文件。
