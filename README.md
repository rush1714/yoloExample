# YOLO Softcare 纸尿裤识别示例

本项目用于本地验证门店照片中的 **Softcare 纸尿裤包装识别与数量统计**，对应 [`设计.md`](设计.md) 的“阶段 1：YOLO 基础陈列识别”。

> 通用 YOLO 预训练模型并不认识 Softcare 品牌或包装；要可靠地统计包数，必须先标注 Softcare 包装并训练专用模型。自动标注只能做“预标注/候选框”，最终仍建议人工复核。

## 识别范围

- 类别：`softcare_diaper`
- 标注对象：图片中每一包可辨认的 Softcare 纸尿裤包装。
- 结果：每一个检测框代表一包，`softcare_count` 即检测框总数。

## MacBook M1 Max 32G 训练建议

你的 MacBook M1 Max 32G 可以训练 YOLO 检测模型，训练时使用 Apple Silicon 的 MPS：

```bash
uv run python scripts/train.py --device mps --imgsz 960 --batch -1
```

模型选择建议：

| 模型 | 适合阶段 | 说明 |
| --- | --- | --- |
| `yolo26n.pt` | 冒烟测试、快速验证流程 | 最快、显存压力最低，但包装较小或遮挡多时容易漏检。 |
| `yolo26s.pt` | **推荐首选 baseline** | M1 Max 32G 通常可以承受，速度和准确率更平衡；本项目训练脚本默认使用它。 |
| `yolo26m.pt` | 数据量更多后的精度对比 | 训练更慢，但可能提升小目标和复杂货架场景效果。建议有 1000+ 张高质量标注后再比较。 |
| `yolo26l.pt` / `yolo26x.pt` | 不建议本地首轮使用 | 对 M1 Max 也能尝试，但迭代慢，不适合当前只有原始未标注图片的阶段。 |

当前目标是货架照片里的商品包装，小目标较多，`imgsz` 比模型大小更关键。建议先用 `yolo26s.pt + imgsz=960`；如果训练太慢或内存压力大，降为 `yolo26n.pt` 或 `imgsz=640`。

## 标注是否必要

**需要。** 这是品牌/SKU 级别目标检测，不是 COCO 预训练模型内置类别。

1. 收集不同门店、货架、距离、角度、光照、遮挡条件下的图片；PoC 建议从 300–500 张开始，生产效果通常需要更多真实场景数据。
2. 每包 Softcare 纸尿裤绘制一个矩形框；被遮挡的包装只要可辨认，也标注其可见部分。
3. 第一阶段只用一个类别：`softcare_diaper`（类别 ID 为 `0`）。
4. 按 `70% / 20% / 10%` 划分训练、验证、测试数据。来自同一原图或连拍序列的图片必须只存在于其中一个划分，避免数据泄漏。

### 标注工具

| 工具 | 适用场景 | 说明 |
| --- | --- | --- |
| [CVAT](https://www.cvat.ai/) | 多人协作、审核和长期数据集建设 | 开源、自托管，支持检测框与 YOLO 导出，优先推荐。可接入 SAM、Grounding DINO 等做半自动标注。 |
| [Label Studio](https://labelstud.io/) | 通用标注与可配置审核流 | 开源、自托管，适合后续扩展图文或多任务标注。 |
| [Labelme](https://github.com/wkentaro/labelme) | 少量本地快速标注 | 轻量 Python 桌面工具，需将其 JSON 标注转换成 YOLO 格式。 |
| [makesense.ai](https://www.makesense.ai/) | 少量 PoC 数据 | 浏览器端工具，无需部署；不建议将业务敏感图片上传到第三方服务。 |

导出时请选择 **YOLO Detection** 格式。每张图片对应一个同名 `.txt` 标签文件，每行格式如下：

```text
<class_id> <center_x> <center_y> <width> <height>
```

四个坐标均为相对图片宽高的归一化值，范围是 `0` 到 `1`。例如：

```text
0 0.512500 0.430000 0.250000 0.350000
```

## 安装

要求 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync
```

首次训练或自动预标注会下载 YOLO/CLIP 权重。Apple Silicon 训练使用 `--device mps`。

## 目录说明

```text
datasets/softcare/
├── raw/                         # Excel 下载下来的“原始未标注图片”，不能直接训练
│   ├── images/                  # 361 张原始图片已下载到这里
│   └── metadata/                # 下载报告 download_report.csv/json
├── ocr/                         # OCR Softcare 关键词筛选结果
│   ├── candidates/              # 可选：复制出来的 OCR 命中候选图片
│   └── metadata/                # OCR 报告和候选清单 ocr_candidates.txt
├── images/                      # 人工确认后的正式训练图片
│   ├── train/                   # 训练集图片：模型用来学习
│   ├── val/                     # 验证集图片：训练过程中调参/早停参考
│   └── test/                    # 测试集图片：最终验收，不能参与训练
├── labels/                      # 与 images 一一对应的 YOLO 标签
│   ├── train/                   # train 图片对应的 .txt 标签
│   ├── val/                     # val 图片对应的 .txt 标签
│   └── test/                    # test 图片对应的 .txt 标签
└── pseudo/                      # 自动预标注输出，必须人工复核后再作为正式训练数据
    ├── images/{train,val,test}/
    ├── labels/{train,val,test}/
    └── metadata/
```

关键规则：

- `raw/images/`：只存从 Excel 下载的原图，没有标签，**不能直接训练**。
- `ocr/...`：OCR 识别 `Softcare` 文字后的候选清单和报告，只用于提高处理优先级；OCR 未命中不代表一定没有 Softcare。
- `images/...` + `labels/...`：正式训练数据。每张图片必须有一个同名 `.txt` 标签文件。
- `pseudo/...`：YOLO-World 自动生成的候选标签，可能误检/漏检，只能作为人工复核起点。
- `data/softcare.yaml`：正式训练数据配置，指向 `datasets/softcare/images` 和 `datasets/softcare/labels`。
- `data/softcare_pseudo.yaml`：伪标注数据配置，指向 `datasets/softcare/pseudo`，仅建议在人工复核后临时试训。
- `models/`：统一存放所有 `.pt` 权重，包括预训练模型、YOLO-World、CLIP 和训练完成的 Softcare 模型；训练输出默认在 `models/train/`。命令里写 `yolo26s.pt`、`yolov8s-world.pt` 这类裸文件名时，脚本会自动解析到 `models/<文件名>`。
- `outputs/predict/`：推理 JSON 和带框图片输出。
- `models/softcare-best.pt`：默认推理模型路径，训练完成后脚本会自动复制 `best.pt` 到这里。

## 从 Excel 下载原始图片

你的 Excel `/Users/guobiao/Downloads/8e96894159cc584f0c7a27faaa4acc45.xlsx` 中的 `整改后图片URL` 列可以用下面命令导入：

```bash
uv run python scripts/import_images_from_excel.py \
  --excel '/Users/guobiao/Downloads/8e96894159cc584f0c7a27faaa4acc45.xlsx' \
  --column '整改后图片URL' \
  --workers 8
```

下载结果：

- 原图目录：`datasets/softcare/raw/images/`
- 下载报告：`datasets/softcare/raw/metadata/download_report.csv`

## OCR 辅助筛选 Softcare

OCR 用来先筛选可能包含 `Softcare` 字样的图片，减少后续自动预标注和人工复核的处理量。当前本地 PoC 默认使用 **RapidOCR ONNX**，它基于 PP-OCR 思路、CPU 推理快、无需额外下载 EasyOCR 检测模型；脚本也保留 `--engine easyocr` 作为备选。如果后续要做生产化服务，建议优先评估 **PaddleOCR / PP-OCR**，它在中文、复杂场景和工程化部署上更成熟。

先小批量试跑：

```bash
uv run python scripts/ocr_filter_softcare.py \
  --limit 20 \
  --engine rapidocr \
  --keyword softcare \
  --keyword 'soft care' \
  --fuzzy-threshold 60 \
  --min-confidence 0.2
```

全量筛选：

```bash
uv run python scripts/ocr_filter_softcare.py \
  --raw-dir datasets/softcare/raw/images \
  --engine rapidocr \
  --keyword softcare \
  --keyword 'soft care' \
  --fuzzy-threshold 60 \
  --min-confidence 0.2
```

输出：

- `datasets/softcare/ocr/metadata/ocr_softcare_report.csv`：每张图片的 OCR 命中情况。
- `datasets/softcare/ocr/metadata/ocr_softcare_report.json`：完整 OCR 文本、置信度和坐标。
- `datasets/softcare/ocr/metadata/ocr_candidates.txt`：命中 Softcare 的候选图片清单。

注意：OCR 未命中不代表图片一定没有 Softcare，尤其是文字很小、模糊、反光或被遮挡时。OCR 只用于“优先级排序”，不能替代人工标注。

## 自动/半自动标注

可以用自动工具减少人工画框工作，但不要直接相信自动结果。

### 方案 A：CVAT 自动标注（推荐）

在 CVAT 中导入 `datasets/softcare/raw/images/`，使用 Grounding DINO / SAM / Segment Anything 插件做预标注，然后人工删除误检、补漏检，最后导出 YOLO Detection 格式。

优点：有可视化审核界面，适合真实项目；缺点是需要部署或配置模型。

### 方案 B：本项目 YOLO-World 预标注脚本

脚本会根据开放词汇提示词生成候选框，并统一写成类别 `softcare_diaper`：

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

说明：

- `--candidates-file` 可接入 OCR 命中的候选清单，只优先处理疑似 Softcare 图片；如果想全量处理，移除该参数。
- `softcare` 文字很小或模糊时，开放词汇检测不一定能识别；`package` 会提高召回，但误检会明显增加。
- 该脚本更适合“先找候选框，再人工审核”，不适合直接生成最终训练集。
- 可以先用 `--limit 20` 试跑，看候选框质量后再全量处理。

复核完成后，把确认后的图片和标签导出/复制到正式目录：

```text
datasets/softcare/images/train|val|test
datasets/softcare/labels/train|val|test
```

### 方案 C：Label Studio 人工复核

当前本地 Label Studio 运行在：

```text
http://localhost:9001
```

本项目提供两个脚本：

| 脚本 | 作用 |
| --- | --- |
| `scripts/import_label_studio.py` | 生成 Label Studio 标准任务 JSON，图片来自原始 URL，YOLO 伪标注作为 `predictions`。 |
| `scripts/apply_label_studio_import.py` | 通过本地 `label-studio shell` 写入当前 Label Studio 实例。 |

生成导入 JSON：

```bash
uv run python scripts/import_label_studio.py
```

导入到本地 Label Studio：

```bash
cd /tmp && PYTHONSAFEPATH=1 \
  /Users/guobiao/PRO/me/yoloExample/.venv/bin/label-studio shell <<'PY'
exec(open('/Users/guobiao/PRO/me/yoloExample/scripts/apply_label_studio_import.py', encoding='utf-8').read())
PY
```

当前已导入项目：

```text
项目：Softcare Diaper Review - 2026-08-05
地址：http://localhost:9001/projects/2/data
任务数：361
带预标注任务数：153
候选框数：1102
```

说明：Label Studio 1.23 默认使用 Personal Access Token 的 `Authorization: Bearer <token>`；当前本地实例没有提供 PAT，且 legacy token 已禁用，因此这里采用本地 `label-studio shell` 导入方式。

## 数据集校验

训练前先校验图片、标签是否一一对应，以及标签坐标和类别是否合法：

```bash
uv run python scripts/validate_dataset.py
```

## 下载单张示例图片

```bash
uv run python scripts/download_sample.py
```

该命令会下载给定图片到 `data/samples/softcare-shelf.webp`。此图片只可用于**训练后推理验证**；单张图片不足以训练出可用模型。

## 训练

完成标注并通过数据集校验后执行：

```bash
uv run python scripts/train.py \
  --base-model models/yolo26s.pt \
  --epochs 100 \
  --imgsz 960 \
  --batch -1 \
  --device mps
```

- Apple Silicon 使用 `--device mps`；没有 GPU 时移除该参数或使用 `--device cpu`。
- 训练结果默认在 `models/train/softcare/`，原始最佳权重为 `models/train/softcare/weights/best.pt`；脚本会自动复制一份到 `models/softcare-best.pt` 作为默认推理模型。
- 商品包装在原图中较小，建议从 `--imgsz 960` 开始；如果速度太慢，可临时降到 `640`。

## 推理与计数

训练结束后默认使用 `models/softcare-best.pt` 推理。每一个 `softcare_diaper` 检测框算作一包：

```bash
uv run python scripts/predict.py \
  data/samples/softcare-shelf.webp \
  --conf 0.35
```

也可以直接传入 HTTP(S) 图片 URL：

```bash
uv run python scripts/predict.py \
  'https://uat-smdp4cust-cdn.globaltradecoo.com/CustomerComponent/67cfc8156160c2fd227aef004b771854.webp'
```

输出包含：

- `outputs/predict/<图片名>.json`：`softcare_count`、置信度和像素级检测框坐标。
- `outputs/predict/<图片名>-annotated.jpg`：画有检测框的结果图，用于人工复核。

示例 JSON：

```json
{
  "softcare_count": 3,
  "detections": [
    {
      "class_id": 0,
      "class_name": "softcare_diaper",
      "confidence": 0.9214,
      "xyxy": [125.2, 80.1, 340.8, 488.5]
    }
  ]
}
```

## 验收与迭代

保留一批从未参与训练的门店照片作为测试集；逐张人工核对真实包数与 `softcare_count`，并评估检测 precision、recall、F1 及计数绝对误差。将漏检、误检、反光、遮挡和远距离小包装等失败样本回流标注后重新训练。

当前 Demo 仅实现 Python 模型训练与推理。后续集成时，Python 模型服务应返回本脚本的 JSON；Spring Boot 负责鉴权、图片业务记录与调用模型服务，Vue 3 负责上传、显示带框图片和 `softcare_count`。这与既有的“YOLO 识别 → 规则引擎 → 审核结果”架构一致。
