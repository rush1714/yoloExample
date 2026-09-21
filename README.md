# YOLO 多品牌包装识别示例

本项目用于本地验证门店照片中的 **多品牌纸尿裤/护理用品包装识别与数量统计**，对应 [`设计.md`](设计.md) 的“YOLO 基础陈列识别”。

> 通用 YOLO 预训练模型并不认识这些业务品牌或包装；要可靠地统计各品牌包数，必须先标注品牌包装并训练专用多类别模型。自动标注只能做“预标注/候选框”，最终仍建议人工复核。

## 识别范围

- 类别来源：新流程统一读取 `config/label_categories.json`，通过 `LABEL_SET` 选择类别列表，通过 `LABELS` 多选类别；历史品牌库 `config/brand_keywords.json` 和 `BRAND=<品牌>` 命令保留兼容。
- 标注对象：图片中每一包可辨认的目标品牌包装。
- 结果：每个检测框代表一包，推理 JSON 会输出 `brand_counts` 和 `total_count`。

## MacBook M1 Max 32G 训练建议

你的 MacBook M1 Max 32G 可以训练 YOLO 检测模型，训练时使用 Apple Silicon 的 MPS：

```bash
uv run python scripts/training/train.py --device mps --imgsz 960 --batch -1
```

模型选择建议：

| 模型 | 适合阶段 | 说明 |
| --- | --- | --- |
| `yolo26n.pt` | 冒烟测试、快速验证流程 | 最快、显存压力最低，但包装较小或遮挡多时容易漏检。 |
| `yolo26s.pt` | **推荐首选基线模型** | M1 Max 32G 通常可以承受，速度和准确率更平衡；本项目训练脚本默认使用它。 |
| `yolo26m.pt` | 数据量更多后的精度对比 | 训练更慢，但可能提升小目标和复杂货架场景效果。建议有 1000+ 张高质量标注后再比较。 |
| `yolo26l.pt` / `yolo26x.pt` | 不建议本地首轮使用 | 对 M1 Max 也能尝试，但迭代慢，不适合当前只有原始未标注图片的阶段。 |

当前目标是货架照片里的商品包装，小目标较多，`imgsz` 比模型大小更关键。建议先用 `yolo26s.pt + imgsz=960`；如果训练太慢或内存压力大，降为 `yolo26n.pt` 或 `imgsz=640`。

## 标注是否必要

**需要。** 这是品牌/SKU 级别目标检测，不是 COCO 预训练模型内置类别。

1. 收集不同门店、货架、距离、角度、光照、遮挡条件下的图片；PoC 建议从 300–500 张开始，生产效果通常需要更多真实场景数据。
2. 每包目标品牌包装绘制一个矩形框；被遮挡的包装只要可辨认，也标注其可见部分。
3. 类别 ID 由 `config/brand_keywords.json` 的 `class_id` 决定；当前 `SOFTCARE` 固定为 `0`，其它品牌依次映射为 `kleesoft`、`doffi` 等。
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
datasets/multibrand/
├── raw/                         # Excel 下载下来的“原始未标注图片”，不能直接训练
│   ├── images/                  # 361 张原始图片已下载到这里
│   └── metadata/                # 下载报告 download_report.csv/json
├── ocr/                         # OCR 品牌关键词筛选结果
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
- `ocr/...`：OCR 识别品牌库关键词后的候选清单和报告，只用于提高处理优先级；OCR 未命中不代表一定没有目标品牌。
- `images/...` + `labels/...`：正式训练数据。每张图片必须有一个同名 `.txt` 标签文件，标签中的 class_id 来自 `config/brand_keywords.json`。
- `pseudo/...`：YOLO-World 自动生成的多品牌候选标签，可能误检/漏检，只能作为人工复核起点。
- `config/label_categories.json`：通用标签类别配置，是新流程 Label Studio、YOLO YAML、本地/EC2 训练的统一类别来源，可在控制台“类别管理”中维护并提交 Git。
- `config/brand_keywords.json`：历史品牌标识库，仍被品牌 OCR/YOLO-World 兼容流程使用；默认通用类别配置不再内置 `brands` 集合，通用训练/标注场景优先维护 `config/label_categories.json` 中的 `general` 类别集合。
- `config/generated/multibrand.yaml`：全品牌正式训练数据配置；由 `make brand-yaml` 根据品牌库生成。
- `config/generated/multibrand_pseudo.yaml`：全品牌伪标注数据配置；由 `make brand-yaml` 根据品牌库生成。
- `config/generated/<品牌>.yaml`：单品牌正式训练配置；执行 `make brand-yaml BRAND=<品牌>` 自动生成。
- `models/`：统一存放所有 `.pt` 权重，包括预训练模型、YOLO-World、CLIP 和训练完成的多品牌模型；训练输出默认在 `models/train/`。命令里写 `yolo26s.pt`、`yolov8s-world.pt` 这类裸文件名时，脚本会自动解析到 `models/<文件名>`。
- `outputs/predict/`：推理 JSON 和带框图片输出。
- `models/<品牌>-best.pt`：训练完成后的推理模型；全品牌默认是 `models/multibrand-best.pt`，单品牌随 `BRAND` 自动命名。

## 从 Excel 下载原始图片

你的 Excel `/Users/guobiao/Downloads/8e96894159cc584f0c7a27faaa4acc45.xlsx` 中的 `整改后图片URL` 列可以用下面命令导入：

```bash
uv run python scripts/data_import/import_images_from_excel.py \
  --excel '/Users/guobiao/Downloads/8e96894159cc584f0c7a27faaa4acc45.xlsx' \
  --column '整改后图片URL' \
  --workers 8
```

下载结果：

- 原图目录：`datasets/multibrand/raw/images/`
- 下载报告：`datasets/multibrand/raw/metadata/download_report.csv`
- 图片命名：`row<Excel行号>_<原附件名称>.<后缀>`，例如 `row00002_67cfc8156160c2fd227aef004b771854.webp`；原附件名称本身是业务 hash，因此不再对完整 URL 重新计算 hash。
- 下载前会比较 Excel 中去重后的有效图片 URL 与本地对应文件；若全部已存在，脚本不创建下载线程、不发起网络请求，直接写入全量 `skipped` 报告并退出。部分缺失时仍进入现有逐图下载/跳过逻辑。

## OCR 辅助筛选品牌候选图片

OCR 用来先筛选可能包含目标品牌字样的图片，减少后续自动预标注和人工复核的处理量。当前本地 PoC 默认使用 **RapidOCR ONNX**，它基于 PP-OCR 思路、CPU 推理快、无需额外下载 EasyOCR 检测模型；脚本也保留 `--engine easyocr` 作为备选。如果后续要做生产化服务，建议优先评估 **PaddleOCR / PP-OCR**。常规 OCR 已支持 `OCR_WORKERS` 多线程并行处理；另新增 Ollama 本地视觉大模型 OCR 分支，可用 `gemma3:12b`、`qwen3.6:latest` 或 `minicpm-v:latest` 从图片中提取品牌文字。

品牌标识库位于：

```text
config/brand_keywords.json
```

当前包含 `KLEESOFT`、`SOFTCARE`、`DOFFI`、`LAVITA`、`NICEDAY`、`MOSSE`、`MAYA`、`CLINCLEER`、`VEESPER`、`CUETTIE`、`T-GUARD`、`ATHENA`、`MCGEL`、`FASKIT`、`DR.X`、`Avril`、`DIAMOND`、`JIEBAI`、`MEDIPOWER`、`KINPOWER` 等品牌。脚本会自动忽略纯数字序号、重复项和 `★` 这类纯符号；如果品牌有空格、连字符或 OCR 常见写法，可以放到 `aliases` 中。`KLEESOFT` 已加入 `Keeson`、`Kleeson`、`Keesoft`、`KEESOTE`、`NEESOTE` 等 OCR 常见误识别别名。

修改 `config/brand_keywords.json` 后，下一次 `make` 命令会重新读取品牌库，自动同步 OCR 关键词、YOLO-World 提示词、Label Studio 标签、`BRAND` 可选值和生成的 YAML 类别。使用 `make brand-list` 查看可用品牌；使用 `BRAND=<品牌>` 时，结果会输出到 `datasets/<品牌>/`，单类别标签会从 `0` 重新编号。全品牌模式为默认的 `BRAND=all`。

OCR 匹配规则已做防误召回处理：长度小于 4 的 OCR 文本不参与品牌匹配，不再使用 `partial_ratio * confidence` 的简单加权，而是组合 `ratio` / `WRatio` / 降权后的 `partial_ratio`；同时要求 OCR 文本覆盖品牌长度的一定比例，避免 `Viva` 误命中 `LAVITA`、单字母 `K` 误命中 `KLEESOFT`。低置信度但高度相似的商标 Logo 文本仍可保留为候选。

先小批量试跑常规并行 OCR：

```bash
make step-2-ocr OCR_LIMIT=20 OCR_WORKERS=4
```

等价脚本命令：

```bash
uv run python scripts/ocr/filter_brand_candidates.py \
  --raw-dir datasets/multibrand/raw/images \
  --brand-library config/brand_keywords.json \
  --limit 20 \
  --engine rapidocr \
  --workers 4 \
  --fuzzy-threshold 60 \
  --min-confidence 0.2
```

如果希望用 Ollama 本地视觉大模型做 OCR，可先确认本机 Ollama 已启动，并使用默认 `gemma3:12b` 小批量试跑：

```bash
make step-2-ocr-llm OCR_LIMIT=5 LLM_OCR_MODEL=gemma3:12b
```

本机已验证的可选视觉模型包括：`gemma3:12b`（默认、样例英文品牌识别稳定）、`qwen3.6:latest`（更大更慢，可作为高精度备选）、`minicpm-v:latest`（可作为备选）。LLM OCR 输出同样写入 `ocr_candidates.txt`，因此后续预标注和 Label Studio 流程不变。

全量筛选：

```bash
make step-2-ocr
# 或使用本地大模型 OCR
make step-2-ocr-llm
```

输出：

- `datasets/<当前品牌>/ocr/metadata/ocr_softcare_report.csv`：每张图片的 OCR 命中情况。
- `datasets/<当前品牌>/ocr/metadata/ocr_softcare_report.json`：完整 OCR 文本、置信度和坐标。
- `datasets/<当前品牌>/ocr/metadata/ocr_candidates.txt`：命中当前品牌关键词的候选图片清单。

OCR 每完成一张图片，会立即追加 CSV、候选清单，并以原子替换方式更新可直接读取的 JSON；因此运行中断时已处理结果仍可保留。默认全品牌目录是 `datasets/multibrand/ocr/`，单品牌目录由 `BRAND` 决定。

如 OCR 被中断，重新执行相同品牌与输出参数并启用恢复模式，脚本会以 JSON 报告为准跳过已完成图片，并先重建 CSV 和候选清单以保持三份报告一致：

```bash
make step-2-ocr-llm BRAND=SOFTCARE OCR_RESUME=1
# 常规 OCR 同样支持
make step-2-ocr BRAND=SOFTCARE OCR_RESUME=1
```

恢复前必须停止旧 OCR 进程，避免两个进程同时写入同一输出目录。若 JSON 报告无效，恢复会拒绝执行而不会静默丢失处理记录。

注意：OCR 命中只代表“可能有目标品牌”，不能直接得到商品框；OCR 未命中也不代表图片一定没有目标品牌。

## 自动/半自动标注

可以用自动工具减少人工画框工作，但不要直接相信自动结果。

### 方案 A：CVAT 自动标注（推荐）

在 CVAT 中导入 `datasets/multibrand/raw/images/`，使用 Grounding DINO / SAM / Segment Anything 插件做预标注，然后人工删除误检、补漏检，最后导出 YOLO Detection 格式。

优点：有可视化审核界面，适合真实项目；缺点是需要部署或配置模型。

### 方案 B：本项目 YOLO-World 预标注脚本

脚本会根据品牌库生成开放词汇提示词，并按品牌映射到不同 YOLO 类别 ID，不再把所有框统一写成 `softcare_diaper`。OCR 和预标注默认使用品牌库中全部启用品牌；单品牌训练使用 `BRAND=SOFTCARE` 等参数，OCR、预标注、Label Studio 和正式训练集会统一筛选该品牌并隔离输出。预标注每完成一张图片会立即写入图片、标签、JSON 和 CSV 元数据，运行中断时已完成记录仍可读取。

脚本会对同一品牌类别内的 YOLO-World 输出做跨提示词去重和大框过滤：
- `--nms-iou`：重复框 IoU 去重阈值。
- `--containment-threshold`：大框覆盖已保留小框超过该比例时丢弃大框。
- `--max-area-ratio`：丢弃占整图面积过大的候选框。
- `--cross-brand-dedup`：跨品牌去重，减少同一商品被多个品牌提示词重复框选。
- `--cross-brand-iou` / `--cross-brand-containment`：控制跨品牌重叠框过滤严格程度。

默认 Make 参数会使用全品牌库、`--include-brand-package-prompts`、同类别去重和跨品牌去重：`--nms-iou 0.45`、`--containment-threshold 0.85`、`--max-area-ratio 0.45`、`--cross-brand-dedup`、`--cross-brand-iou 0.35`、`--cross-brand-containment 0.80`：

```bash
make step-3-pseudo-label
```

等价脚本命令：

```bash
uv run python scripts/pseudo_label/generate_yolo_world.py \
  --raw-dir datasets/multibrand/raw/images \
  --output-root datasets/multibrand/pseudo \
  --candidates-file datasets/multibrand/ocr/metadata/ocr_candidates.txt \
  --brand-library config/brand_keywords.json \
  --include-brand-package-prompts \
  --nms-iou 0.45 \
  --containment-threshold 0.85 \
  --max-area-ratio 0.45 \
  --cross-brand-dedup \
  --cross-brand-iou 0.35 \
  --cross-brand-containment 0.80 \
  --conf 0.03 \
  --imgsz 960
```

说明：

- `--candidates-file` 可接入 OCR 命中的候选清单，只优先处理疑似品牌图片；如果想全量处理，可执行 `make step-3-pseudo-label PSEUDO_USE_OCR_CANDIDATES=0`。
- `BRAND=all` 是全品牌默认模式；执行 `make step-3-pseudo-label BRAND=SOFTCARE` 时只处理该品牌，输出隔离到 `datasets/softcare/`，单类 ID 固定为 `0`。
- 多品牌模式下额外 `PSEUDO_PROMPT_ARGS` 建议使用 `{brand}` 占位符，例如 `--prompt '{brand} package on shelf'`，否则泛化 prompt 无法安全映射到某个类别。
- 品牌包装提示词会提高召回，但误检会增加；现在配合同类别 NMS、覆盖过滤、最大面积过滤和跨品牌去重减少“大框盖小框”和重复框。
- 如果确认同一位置确实可能有多个品牌框，可临时关闭跨品牌去重：`make step-3-pseudo-label PSEUDO_CROSS_BRAND_DEDUP=0`。
- 该脚本更适合“先找候选框，再人工审核”，不适合直接生成最终训练集。
- 可以先用 `PSEUDO_LIMIT=20` 试跑，看候选框质量后再全量处理。

复核完成后，把确认后的图片和标签导出/复制到正式目录：

```text
datasets/multibrand/images/train|val|test
datasets/multibrand/labels/train|val|test
```

### 方案 C：Label Studio 人工复核

当前本地 Label Studio 使用 **9001 端口 + 本地 PostgreSQL + 本地文件服务**：

```text
http://localhost:9001
```

本项目提供 Makefile 封装端到端流程，所有参数都有默认值，并可在命令行覆盖，例如 `make step-6-train TRAIN_EPOCHS=50 TRAIN_DEVICE=cpu`。Makefile 不再切换到 `/tmp`，Label Studio shell/start 统一使用项目内临时目录 `.tmp/label-studio/`，运行日志写入 `logs/`。

### 本地 Make 可视化控制台

如果不想手写复杂 Make 命令，可以启动一个本地 Node 页面：

```bash
npm start
# 或
make web-console
```

默认访问地址：

```text
http://localhost:3000
```

页面使用左侧多级菜单展示功能大类，包括类别管理、图片来源/标注准备、Label Studio、本地 Mac 训练/推理、EC2 训练/评估/下载、维护工具和图片浏览。命令类功能可展开到二级或三级菜单；再次点击同一分组可折叠/展开，点击某个命令子菜单后，右侧只展示该命令的单独页面，包括说明、常用参数、命令预览、复制和执行按钮。未填写的参数继续使用 Makefile 默认值；点击“执行”后会在页面下方显示实时日志，也可以复制生成的命令到终端手动执行。

“类别管理”页会读取和保存 `config/label_categories.json`。这里可以维护多个类别列表，例如 `brands`、`general`，命令中通过：

| 参数 | 作用 |
| --- | --- |
| `LABEL_SET` | 类别列表名称，例如 `brands` 或 `general`。 |
| `LABELS` | 当前类别列表中的多选类别，逗号分隔；`all` 表示全部启用类别。 |
| `COUNTRY` | 国家/市场参数，参与默认目录命名。 |
| `DATA_VERSION` | 数据版本，参与默认目录命名。 |
| `LABEL_DATASET_NAME` | 数据集短名称；留空时按类别选择自动生成。 |

通用目录默认遵循：

```text
datasets/<COUNTRY>/<DATA_VERSION>/<LABEL_DATASET_NAME>/
```

例如 `datasets/GH/v2026-09-18/allround_purple/`。Excel、本地目录、S3 只表示导入/访问方式，不再作为一级目录拆分同一数据集；S3 清单统一写在数据集内的 `s3/metadata/`。所有目录参数仍可手动覆盖。

参数输入会自动缓存到浏览器 `localStorage`，缓存 key 为 `yoloConsole:paramValues:v1`。缓存按 Make 参数名共享，例如在一个命令中填写过 `EC2_HOST`、`S3_DATASET_NAME` 后，切换到其它包含同名参数的命令会自动带出；清空某个输入框会删除该参数缓存并恢复使用 Makefile 默认值，页面也提供“清空参数缓存”按钮。非敏感参数会同步保存到 `web-console/state.json`，该文件可提交 Git；私钥路径等敏感参数不会写入该文件。

数据浏览页会扫描项目内白名单目录，例如 `datasets/`、`outputs/predict/`、`models/train/`、`artifacts/diaper_category/`、`data/samples/`，展示图片数量、训练集拆分统计、报告摘要和图片缩略图。点击缩略图可以查看大图。页面只面向本机使用，不提供登录和公网访问能力；EC2 命令默认仍为 dry-run，只有显式填写 `EC2_EXECUTE=1` 才会真实连接远端机器。
### 本地目录图片导入 Label Studio

如果图片已经在本机某个目录中，不需要通过 Excel 下载，可以直接把该目录导入 Label Studio 做单类别矩形框标注。

新项目推荐使用通用类别命令，不再为“纸尿裤”或某个品牌单独复制命令。下面示例从 `general` 类别列表中选择 `allround_purple` 一个类别：

```bash
make 1-label-local-workflow-to-ls \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=allround_purple \
  LABEL_LOCAL_IMAGES_DIR=/Users/guobiao/Downloads/allround_images

make 2-label-workflow-after-ls \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-18 \
  LABEL_SET=general \
  LABELS=allround_purple \
  LS_PROJECT_ID=<项目ID> \
  LABEL_LS_TO_YOLO_CLEAR=1
```

如果需要一次标注多个自定义类别，只需在控制台“类别管理”中把类别加入同一 `LABEL_SET`，再执行：

```bash
make 1-label-local-workflow-to-ls LABEL_SET=general LABELS=diaper,allround_purple
```

通用本地目录流程会先把 `LABEL_LOCAL_IMAGES_DIR` 中的源图片复制/沉淀到标准 `raw/images/`，后续 Label Studio 导入、S3 上传和 YOLO 转换都围绕同一个 `datasets/<COUNTRY>/<DATA_VERSION>/<LABEL_DATASET_NAME>/` 工作。

如果已经执行“通用本地 LS 转 YOLO”并生成了 `images/{train,val,test}`，且 `raw/images` 中还有大量未标注图片，则不要上传 `raw/images` 全量图片。推荐只上传训练图片目录：

```bash
make label-s3-upload-images \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-20 \
  LABEL_SET=general \
  LABELS=kleesoft_purple,allround_purple \
  LABEL_LOCAL_IMAGES_DIR=datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/images \
  LABEL_RECURSIVE=1 \
  S3_BUCKET=<bucket> \
  S3_DRY_RUN=0
```

上传完成后，执行 `label-yolo-s3-to-ec2-manifest`，由已有 YOLO `images/labels` 和 S3 上传清单生成 EC2 下载清单：

```bash
make label-yolo-s3-to-ec2-manifest \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-20 \
  LABEL_SET=general \
  LABELS=kleesoft_purple,allround_purple \
  LABEL_LS_TO_YOLO_SKIP_EMPTY=1
```

随后可继续执行 `3-label-s3-workflow-ec2-train`。

训练完成后，可以直接在 EC2 上读取 S3/Excel/JSON/TXT 图片清单做批量推理，并把结果上传到指定 S3 目录：

```bash
make label-s3-ec2-predict-manifest \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-20 \
  LABEL_SET=general \
  LABELS=kleesoft_purple,allround_purple \
  EC2_HOST=<EC2地址> \
  EC2_KEY=/path/key.pem \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_PREDICT_LOCAL_MANIFEST=/Users/guobiao/Downloads/predict_images.xlsx \
  EC2_PREDICT_INPUT_COLUMN=整改后图片URL \
  EC2_PREDICT_OUTPUT_S3_URI=s3://<bucket>/predict-results/GH/v2026-09-20/run1 \
  EC2_PREDICT_LIMIT=20 \
  EC2_EXECUTE=1
```

推理输出会包含 `summary.json`、`summary.csv`、`source_image_uris.txt`、`uploaded_s3_uris.txt`、`json/` 单图检测结果和 `annotated/` 带框图片，并统一上传到 `EC2_PREDICT_OUTPUT_S3_URI`。

如果推理已经完成但 S3 上传因凭证或网络失败，修复 EC2 凭证后可以只补传已有结果，不重新推理：

```bash
make label-s3-ec2-upload-existing-predict-results \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-20 \
  LABEL_SET=general \
  LABELS=kleesoft_purple,allround_purple \
  EC2_HOST=<EC2地址> \
  EC2_KEY=/path/key.pem \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_PREDICT_OUTPUT_S3_URI=s3://<bucket>/predict-results/GH/v2026-09-20/run1 \
  EC2_EXECUTE=1
```

如需把推理结果和原始推理图片下载回本地标准目录，执行：

```bash
make label-s3-ec2-download-predict-results \
  COUNTRY=GH \
  DATA_VERSION=v2026-09-20 \
  LABEL_SET=general \
  LABELS=kleesoft_purple,allround_purple \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_PREDICT_OUTPUT_S3_URI=s3://<bucket>/predict-results/GH/v2026-09-20/run1 \
  EC2_PREDICT_DOWNLOAD_SOURCE_IMAGES=1 \
  EC2_PREDICT_DOWNLOAD_WORKERS=16 \
  EC2_PREDICT_SOURCE_DOWNLOAD_TIMEOUT=30 \
  S3_PUBLIC_BASE_URL=https://uat-smdp4cust-bak.s3.af-south-1.amazonaws.com \
  S3_PROFILE=smdp-yolo
```

下载时会实时打印 `download uri list`、`start/done result file n/N` 和 `start/done source image n/N` 进度；结果文件和原始图片默认并发数为 8，可通过 `EC2_PREDICT_DOWNLOAD_WORKERS` 调整；已下载且非空的文件会自动跳过，支持断点续传；HTTP(S) 原始图片默认 30 秒超时，可通过 `EC2_PREDICT_SOURCE_DOWNLOAD_TIMEOUT` 调整；如果设置 `S3_PUBLIC_BASE_URL`，S3 结果文件和 S3 原图会优先用 public URL 下载，失败后回退 boto3。下载后的结果默认进入 `outputs/ec2_predict/<COUNTRY>/<DATA_VERSION>/<LABEL_DATASET_NAME>/<EC2_RUN_NAME>/`，原始推理图进入 `datasets/<COUNTRY>/<DATA_VERSION>/<LABEL_DATASET_NAME>/predict/images/<EC2_RUN_NAME>/`，S3 结果记录文本和下载报告进入 `datasets/<COUNTRY>/<DATA_VERSION>/<LABEL_DATASET_NAME>/s3/metadata/`。

EC2 端上传/下载 S3 依赖 AWS 凭证。推荐给 EC2 绑定 IAM Role/Instance Profile，并授予输入图片和清单的 `s3:GetObject`、输出结果目录的 `s3:PutObject`；这样 `boto3` 会自动使用角色凭证。可在 EC2 上用 `aws sts get-caller-identity` 和 `aws s3 ls s3://<bucket>/<prefix>/` 验证。短期也可在 EC2 上执行 `aws configure` 写入 `~/.aws/credentials`，但不要把 Access Key 写进 Makefile、Git 或控制台 state。

历史 `1-local-dir-workflow-to-ls` / `2-local-dir-workflow-after-ls` 仍保留兼容，但推荐逐步切换到 `label-*` 通用命令。

1. 启动 Label Studio：

```bash
make ls-start
```

2. 扫描本地目录并创建 Label Studio 项目：

```bash
make 1-local-dir-workflow-to-ls \
  LOCAL_IMAGES_DIR=/Users/guobiao/Downloads/my_images \
  LOCAL_DATASET_NAME=my_images_v1 \
  LOCAL_DATASET_ROOT=/Users/guobiao/PRO/me/yoloExample/datasets/GH/v2026-09-18/my_images_v1 \
  LOCAL_LABEL_NAME=纸尿裤
```

常用参数：

| 参数 | 作用 |
| --- | --- |
| `LOCAL_IMAGES_DIR` | 要导入的源图片目录，可以是绝对路径或相对路径。 |
| `LOCAL_DATASET_NAME` | 数据集短名称，只能填 `my_images_v1` 这类名字，不能填路径。 |
| `LOCAL_DATASET_ROOT` | 导出数据集目录；留空默认是 `datasets/<COUNTRY>/<DATA_VERSION>/<LOCAL_DATASET_NAME>/`，如需指定目录请改这个参数。 |
| `LOCAL_LABEL_NAME` | Label Studio 和 YOLO 单类别名称。 |
| `LOCAL_RECURSIVE` | 是否递归扫描子目录，默认 `1`；设为 `0` 只扫描当前层。 |
| `LOCAL_LIMIT` | 最多导入多少张图片，留空表示全量。 |

该流程会生成：

```text
datasets/<COUNTRY>/<DATA_VERSION>/<LOCAL_DATASET_NAME>/label_studio/local_dir_label_studio_import.json
datasets/<COUNTRY>/<DATA_VERSION>/<LOCAL_DATASET_NAME>/label_studio/label_config.xml
```

并创建一个 Label Studio 项目。命令输出里的 `project_id` 用于后续导出。

3. 人工标注完成后导出并转换为 YOLO 训练集：

```bash
make 2-local-dir-workflow-after-ls \
  LOCAL_DATASET_NAME=my_images_v1 \
  LOCAL_DATASET_ROOT=/Users/guobiao/PRO/me/yoloExample/datasets/GH/v2026-09-18/my_images_v1 \
  LOCAL_LABEL_NAME=纸尿裤 \
  LS_PROJECT_ID=<项目ID>
```

输出训练集：

```text
datasets/<COUNTRY>/<DATA_VERSION>/<LOCAL_DATASET_NAME>/images/train|val|test
datasets/<COUNTRY>/<DATA_VERSION>/<LOCAL_DATASET_NAME>/labels/train|val|test
config/generated/<COUNTRY>_<DATA_VERSION>_<LOCAL_DATASET_NAME>.yaml
```

如果只想分步执行，可使用：

```bash
make local-dir-ls-import-json LOCAL_IMAGES_DIR=/path/to/images LOCAL_DATASET_NAME=my_images_v1 LOCAL_DATASET_ROOT=/path/to/output LOCAL_LABEL_NAME=纸尿裤
make local-dir-ls-apply LOCAL_IMAGES_DIR=/path/to/images LOCAL_DATASET_NAME=my_images_v1 LOCAL_DATASET_ROOT=/path/to/output LOCAL_LABEL_NAME=纸尿裤
make local-dir-ls-export LOCAL_DATASET_NAME=my_images_v1 LOCAL_DATASET_ROOT=/path/to/output LS_PROJECT_ID=<项目ID>
make local-dir-ls-to-yolo LOCAL_DATASET_NAME=my_images_v1 LOCAL_DATASET_ROOT=/path/to/output LOCAL_LABEL_NAME=纸尿裤
```

注意：`LOCAL_DATASET_NAME` 只用于命名，不能写成本地目录路径；如果要指定导出位置，请使用 `LOCAL_DATASET_ROOT`。

### 本地目录数据衔接 EC2 训练

本地目录标注转换完成后，可以直接上传到 EC2 并训练。默认远端目录为：

```text
/home/<EC2_USER>/yoloExample/datasets/<COUNTRY>/<DATA_VERSION>/<LOCAL_DATASET_NAME>/
/home/<EC2_USER>/yoloExample/config/generated/<COUNTRY>_<DATA_VERSION>_<LOCAL_DATASET_NAME>.yaml
/home/<EC2_USER>/yoloExample/models/ec2/<COUNTRY>/<DATA_VERSION>/<LOCAL_DATASET_NAME>/<EC2_RUN_NAME>/best.pt
/home/<EC2_USER>/yoloExample/artifacts/<COUNTRY>/<DATA_VERSION>/<LOCAL_DATASET_NAME>/<EC2_RUN_NAME>/
```

推荐顺序：

```bash
# 1. 上传本地目录 YOLO 数据集和 YAML；默认 dry-run，确认后加 EC2_EXECUTE=1
make local-dir-ec2-upload-data \
  LOCAL_DATASET_NAME=my_images_v1 \
  LOCAL_DATASET_ROOT=/Users/guobiao/PRO/me/yoloExample/datasets/GH/v2026-09-18/my_images_v1 \
  LOCAL_LABEL_NAME=纸尿裤 \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem

# 2. 训练；默认 dry-run，确认后加 EC2_EXECUTE=1
make local-dir-ec2-train \
  LOCAL_DATASET_NAME=my_images_v1 \
  LOCAL_DATASET_ROOT=/Users/guobiao/PRO/me/yoloExample/datasets/GH/v2026-09-18/my_images_v1 \
  LOCAL_LABEL_NAME=纸尿裤 \
  EC2_BASE_MODEL=yolo26m.pt \
  EC2_TRAIN_EPOCHS=100 \
  EC2_TRAIN_IMGSZ=960 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem

# 3. 评估归档并下载产物
make local-dir-ec2-evaluate \
  LOCAL_DATASET_NAME=my_images_v1 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem
make local-dir-ec2-download-artifacts \
  LOCAL_DATASET_NAME=my_images_v1 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem
make local-dir-ec2-download-model \
  LOCAL_DATASET_NAME=my_images_v1 \
  EC2_RUN_NAME=yolo26m_img960_e100 \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem
```

如需调整远端目录，可以覆盖：

```bash
LOCAL_EC2_REMOTE_DATASET_ROOT=datasets/GH/v2026-09-18/my_images_v1
LOCAL_EC2_REMOTE_DATA_YAML=config/generated/GH_v2026-09-18_my_images_v1.yaml
LOCAL_EC2_TRAIN_NAME=GH_v2026-09-18_my_images_v1
LOCAL_EC2_REMOTE_FINAL_MODEL=models/ec2/GH/v2026-09-18/my_images_v1/yolo26m_img960_e100/best.pt
LOCAL_EC2_ARTIFACT_ROOT=artifacts/GH/v2026-09-18/my_images_v1/yolo26m_img960_e100
```

Web 控制台中也可以在左侧选择“图片来源 / 标注准备 → 本地目录 → LS”或“EC2 训练 / 推理 / 下载 → 本地目录数据集 → EC2”，填写同样参数后执行。


| 顺序 | 命令 | 作用 |
| --- | --- | --- |
| 1 | `make step-1-import-excel` | 从 Excel 的 `整改后图片URL` 列下载共享原图池 `datasets/multibrand/raw/images/`。 |
| 2 | `make step-2-ocr [BRAND=<品牌>]` | OCR 输出到 `datasets/<当前品牌>/ocr/`；逐图增量写入报告。 |
| 3 | `make step-3-pseudo-label [BRAND=<品牌>]` | YOLO-World 输出到 `datasets/<当前品牌>/pseudo/`；逐图增量写入图片、标签和报告。 |
| 4 | `make step-4-import-ls [BRAND=<品牌>]` | 生成当前品牌 Label Studio 导入 JSON，并导入本地 Label Studio。 |
| 5 | `make step-5-export-ls-to-train BRAND=<品牌> LS_PROJECT_ID=<项目ID>` | 从 Label Studio 导出并转换为当前品牌正式训练集。 |
| 6 | `make step-6-train [BRAND=<品牌>]` | 校验并训练当前品牌模型，默认导出 `models/<品牌>-best.pt`。 |
| 7 | `make step-7-validate` | 校验正式数据集，并使用训练模型对 `PREDICT_SOURCE` 做推理验证。 |

常用组合命令：

| 命令 | 作用 |
| --- | --- |
| `make workflow-to-ls` | 执行步骤 1–4，到 Label Studio 人工复核前/导入完成。 |
| `make workflow-to-ls-llm` | 使用 Ollama 本地大模型 OCR 后执行步骤 1–4，到 Label Studio 导入完成。 |
| `make workflow-after-ls LS_PROJECT_ID=<项目ID>` | 人工复核完成后执行步骤 5–7：导出、转训练集、训练、验证。 |
| `make ls-setup` | 首次初始化 PostgreSQL 数据库并执行 Label Studio 迁移。 |
| `make ls-start` | 后台启动 Label Studio（端口 9001，PostgreSQL，本地文件服务），日志写入 `logs/label-studio.log`。 |
| `make ls-stop` | 停止占用 9001 端口的 Label Studio 进程，并清理 `logs/label-studio.pid`。 |
| `make help` | 查看全部 Make 命令，并输出常用参数默认值、可选值和调参效果。 |
| `make help-params` | 只查看参数说明。 |
| `make datasets-clean-preview` | 预览 `datasets/` 下会被 `.gitignore` 忽略且会被清理的文件。 |
| `make datasets-clean-ignored` | 删除 `datasets/` 下所有被 `.gitignore` 忽略的文件；执行前务必先预览。 |

首次使用流程：

```bash
# 0. 创建数据库并执行迁移
make ls-setup

# 1-4. 从 Excel 到 Label Studio 导入
make workflow-to-ls

# 后台启动 Label Studio，打开输出项目地址做人工复核
make ls-start
tail -f logs/label-studio.log

# 人工复核完成后，使用项目 ID 导出、转训练集、训练和验证
make workflow-after-ls LS_PROJECT_ID=<项目ID>
```

常用参数覆盖示例：

```bash
# 查看所有参数默认值、可选值和效果说明
make help-params

# 小样本调试 OCR / 预标注
make step-2-ocr OCR_LIMIT=20 OCR_WORKERS=4
make step-2-ocr-llm OCR_LIMIT=5 LLM_OCR_MODEL=gemma3:12b
make step-3-pseudo-label PSEUDO_LIMIT=20 PSEUDO_CONF=0.03

# 不使用 OCR 候选清单，直接全量预标注
make step-3-pseudo-label PSEUDO_USE_OCR_CANDIDATES=0

# 大框/重复框仍多时，调低最大面积和 NMS 阈值
make step-3-pseudo-label PSEUDO_MAX_AREA_RATIO=0.30 PSEUDO_NMS_IOU=0.35

# 单品牌流程：结果隔离在 datasets/softcare，类别 ID 自动重编号为 0
make workflow-to-ls BRAND=SOFTCARE
# 人工复核后导出并训练该品牌
make workflow-after-ls BRAND=SOFTCARE LS_PROJECT_ID=<项目ID>

# 训练参数覆盖
make step-6-train TRAIN_EPOCHS=50 TRAIN_IMGSZ=640 TRAIN_DEVICE=cpu

# 指定 Label Studio 导出文件和清空旧训练集后转换
make ls-to-yolo LS_EXPORT_PATH=datasets/multibrand/label_studio/exports/label_studio_export.json LS_TO_YOLO_CLEAR=1
```

核心可配置参数包括：`EXCEL`、`EXCEL_COLUMN`、`RAW_DIR`、`OCR_ENGINE`、`OCR_MIN_CONFIDENCE`、`OCR_FUZZY_THRESHOLD`、`OCR_LIMIT`、`PSEUDO_MODEL`、`PSEUDO_BRAND_FILTER_ARGS`、`PSEUDO_CONF`、`PSEUDO_NMS_IOU`、`PSEUDO_CONTAINMENT`、`PSEUDO_MAX_AREA_RATIO`、`PSEUDO_LIMIT`、`LS_PROJECT_ID`、`LS_EXPORT_PATH`、`TRAIN_EPOCHS`、`TRAIN_IMGSZ`、`TRAIN_DEVICE`、`PREDICT_SOURCE`。完整说明以 `make help-params` 为准。

Label Studio 启停和导入仍可单独执行：

```bash
make ls-start
make ls-import-json
make ls-apply
make ls-stop
```

清理 `datasets/` 下被 git 忽略的生成文件：

```bash
# 先预览会删除哪些文件
make datasets-clean-preview

# 确认无误后再删除
make datasets-clean-ignored
```

该命令只作用于 `datasets/`，底层使用 `git clean -fdX -- datasets/`，会删除 `.gitignore` 忽略的原图、伪标注图片、正式训练图片等大文件，不会删除已被 git 跟踪的文件。

本项目提供两个导入脚本：

| 脚本 | 作用 |
| --- | --- |
| `scripts/label_studio/generate_import.py` | 生成 Label Studio 标准任务 JSON；图片使用本地文件服务路径，避免远程 CDN CORS 问题；YOLO 伪标注作为 `predictions`。 |
| `scripts/label_studio/apply_import.py` | 通过本地 `label-studio shell` 创建项目、任务、prediction，并创建 Local Files storage 权限记录。 |

当前导入 JSON 结果：

```text
任务数：361
带预标注任务数：153
候选框数：1102
```

历史已导入项目如下；如果按新脚本重新执行 `make ls-apply`，请以命令输出的新项目地址为准：

```text
项目：Softcare Diaper Review - 2026-08-05
地址：http://localhost:9001/projects/2/data
任务数：361
带预标注任务数：153
候选框数：1102
```

说明：Label Studio 1.23 默认使用 Personal Access Token 的 `Authorization: Bearer <token>`；当前本地实例没有提供 PAT，且 legacy token 已禁用，因此这里采用本地 `label-studio shell` 导入方式。Label Studio 的 `/data/local-files/` 端点还要求项目有对应 Local Files storage 权限，所以必须用 `make ls-apply` 或等价脚本注册 `datasets/multibrand/raw/images/`。

## 纸尿裤大类正式标注与 EC2 A10 训练流程

这是独立于多品牌识别的新流程，目标是先标注“纸尿裤”这个大类，而不是识别具体品牌。该流程**只导入原始图片到 Label Studio，不做任何预标注**。

### 本地目录规划

```text
datasets/diaper_category/<国家>/<版本>/
├── raw/images/                  # 正式图片原图
├── raw/metadata/download_report.csv
├── label_studio/diaper_category_label_studio_import.json
├── label_studio/label_config.xml
├── label_studio/exports/
├── images/{train,val,test}/     # 人工标注导出的训练图片
└── labels/{train,val,test}/     # YOLO 标签，class_id 固定为 0
```

配置文件生成到：

```text
config/generated/diaper_category_<国家>_<版本>.yaml
```

类别固定为：

```yaml
names:
  0: 纸尿裤
```

### 下载并导入 Label Studio

```bash
make diaper-workflow-to-ls \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  DIAPER_EXCEL=/path/to/images.xlsx \
  DIAPER_EXCEL_COLUMN=整改后图片URL
```

它会执行：

1. `diaper-import-excel`：下载图片到 `datasets/diaper_category/ghana/v20260812/raw/images/`。
2. `diaper-yaml`：生成单类别 YAML。
3. `diaper-ls-import-json`：生成无预标注的 Label Studio JSON。
4. `diaper-ls-apply`：导入 Label Studio，标签只有 `纸尿裤`。

人工标注完成后：

```bash
make diaper-workflow-after-ls \
  DIAPER_COUNTRY=ghana \
  DIAPER_VERSION=v20260812 \
  LS_PROJECT_ID=<项目ID>
```

该命令会导出 Label Studio JSON，并转换成 `images/` + `labels/` YOLO 训练集。

如果同一批数据分散在多个 Label Studio 项目中，可以先导出并合并“有有效框”的任务，再统一转换训练集。例如把项目 21 和 20 合并到 GH 的 `v2026-09-15`：

```bash
make diaper-merge-ls-projects \
  DIAPER_COUNTRY=GH \
  DIAPER_VERSION=v2026-09-15 \
  DIAPER_LABEL_NAME=diaper \
  LS_PROJECT_IDS=21,20
```

该命令会按 `LS_PROJECT_IDS` 顺序逐个导出项目，输出到：

```text
datasets/diaper_category/GH/v2026-09-15/label_studio/exports/projects/project_21.json
datasets/diaper_category/GH/v2026-09-15/label_studio/exports/projects/project_20.json
```

并只保留有有效矩形框的任务，按图片路径去重后生成：

```text
datasets/diaper_category/GH/v2026-09-15/label_studio/exports/merged_label_studio_export.json
datasets/diaper_category/GH/v2026-09-15/label_studio/exports/merged_label_studio_export_report.json
```

如果希望合并后直接生成 YOLO 训练集，可以使用一键命令：

```bash
make diaper-merge-ls-projects-to-yolo \
  DIAPER_COUNTRY=GH \
  DIAPER_VERSION=v2026-09-15 \
  DIAPER_LABEL_NAME=diaper \
  LS_PROJECT_IDS=21,20 \
  LS_TO_YOLO_CLEAR=1 \
  LS_TO_YOLO_SKIP_EMPTY=1
```

它等价于先执行 `diaper-merge-ls-projects`，再用合并后的 JSON 执行 `diaper-ls-to-yolo`。

如果只想分步处理，也可以再转换为 YOLO：

```bash
make diaper-ls-to-yolo \
  DIAPER_COUNTRY=GH \
  DIAPER_VERSION=v2026-09-15 \
  DIAPER_LABEL_NAME=diaper \
  DIAPER_LS_EXPORT_PATH=datasets/diaper_category/GH/v2026-09-15/label_studio/exports/merged_label_studio_export.json \
  LS_TO_YOLO_CLEAR=1 \
  LS_TO_YOLO_SKIP_EMPTY=1
```

注意：如果 Label Studio 项目里的标签实际是 `纸尿裤`，请把 `DIAPER_LABEL_NAME=diaper` 改为 `DIAPER_LABEL_NAME=纸尿裤`，否则合并时会把标签不匹配的框过滤掉。

### EC2 A10 目录规划

建议 EC2 上使用：

```text
/home/ubuntu/yoloExample/
├── scripts/
├── config/generated/diaper_category_ghana_v20260812.yaml
├── datasets/diaper_category/ghana/v20260812/
├── models/train/diaper_category_ghana_v20260812/weights/best.pt
└── models/ec2/diaper_category/ghana/v20260812/best.pt
```

### 上传、训练、推理、下载模型

默认命令只 dry-run 打印将执行的 `rsync` / `ssh` 命令；确认无误后加 `EC2_EXECUTE=1` 才会实际连接 EC2。

```bash
# 上传代码
make diaper-ec2-upload-project EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem

# 上传当前国家/版本数据和 YAML
# Web 控制台入口：纸尿裤大类 / EC2 -> 02. 上传纸尿裤数据到 EC2
make 02-diaper-ec2-upload-data \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812

# 如果要明确指定本地数据集目录和 YAML，可覆盖：
make 02-diaper-ec2-upload-data \
  DIAPER_COUNTRY=GH \
  DIAPER_VERSION=v2026-09-15 \
  DIAPER_LABEL_NAME=diaper \
  DIAPER_DATASET_ROOT=/Users/guobiao/PRO/me/yoloExample/datasets/diaper_category/GH/v2026-09-15 \
  DIAPER_DATA_YAML=/Users/guobiao/PRO/me/yoloExample/config/generated/diaper_category_GH_v2026-09-15.yaml \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem

# 在 A10 GPU 上训练，默认 device=0
make diaper-ec2-train \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812 \
  EC2_EXECUTE=1

# 在 EC2 上推理验证
make diaper-ec2-predict \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812 \
  EC2_PREDICT_SOURCE=/path/on/ec2/test.jpg \
  EC2_EXECUTE=1

# 下载训练好的 best.pt
make diaper-ec2-download-model \
  EC2_HOST=<EC2地址> EC2_KEY=/path/key.pem \
  DIAPER_COUNTRY=ghana DIAPER_VERSION=v20260812 \
  EC2_EXECUTE=1
```

常用 EC2 参数：`EC2_USER`、`EC2_KEY`、`EC2_PORT`、`EC2_PROJECT_ROOT`、`EC2_BASE_MODEL`、`EC2_TRAIN_EPOCHS`、`EC2_TRAIN_BATCH`、`EC2_TRAIN_DEVICE`。

## 数据集校验

训练前先校验图片、标签是否一一对应，以及标签坐标和类别是否合法：

```bash
uv run python scripts/training/validate_dataset.py
```

## 下载单张示例图片

```bash
uv run python scripts/data_import/download_sample.py
```

该命令会下载给定图片到 `data/samples/multibrand-shelf.webp`。此图片只可用于**训练后推理验证**；单张图片不足以训练出可用模型。

## 训练

完成标注并通过数据集校验后执行：

```bash
make step-6-train
```

训练中断后，可从同一品牌的 `models/train/<品牌>/weights/last.pt` 恢复：

```bash
make train BRAND=SOFTCARE TRAIN_RESUME=1
```

恢复时 Ultralytics 会读取检查点中的训练参数和状态；如果 `last.pt` 不存在，脚本会明确报错而不会重新开始训练。

等价脚本命令：

```bash
uv run python scripts/training/train.py \
  --data config/generated/multibrand.yaml \
  --base-model models/yolo26s.pt \
  --epochs 100 \
  --imgsz 960 \
  --batch -1 \
  --device mps \
  --name multibrand \
  --export-model models/multibrand-best.pt
```

- Apple Silicon 使用 `--device mps`；没有 GPU 时设置 `TRAIN_DEVICE=cpu` 或置空。
- 训练结果默认在 `models/train/multibrand/`，原始最佳权重为 `models/train/multibrand/weights/best.pt`；Makefile 默认复制一份到 `models/multibrand-best.pt` 作为默认推理模型。
- 商品包装在原图中较小，建议从 `--imgsz 960` 开始；如果速度太慢，可临时降到 `640`。

## 推理与计数

训练结束后默认使用 `models/multibrand-best.pt` 推理。每个品牌检测框算作一包，并按 `brand_counts` 汇总：

```bash
uv run python scripts/inference/predict.py \
  data/samples/multibrand-shelf.webp \
  --conf 0.35
```

也可以直接传入 HTTP(S) 图片 URL：

```bash
uv run python scripts/inference/predict.py \
  'https://uat-smdp4cust-cdn.globaltradecoo.com/CustomerComponent/67cfc8156160c2fd227aef004b771854.webp'
```

输出包含：

- `outputs/predict/<图片名>.json`：`brand_counts`、`total_count`、置信度和像素级检测框坐标。
- `outputs/predict/<图片名>-annotated.jpg`：画有检测框的结果图，用于人工复核。

示例 JSON：

```json
{
  "brand_counts": {
    "softcare": 3,
    "kleesoft": 1
  },
  "total_count": 4,
  "detections": [
    {
      "class_id": 0,
      "class_name": "softcare",
      "confidence": 0.9214,
      "xyxy": [125.2, 80.1, 340.8, 488.5]
    }
  ]
}
```

## 验收与迭代

保留一批从未参与训练的门店照片作为测试集；逐张人工核对各品牌真实包数与 `brand_counts`，并评估各类别 precision、recall、F1 及计数绝对误差。将漏检、误检、反光、遮挡和远距离小包装等失败样本回流标注后重新训练。

当前 Demo 仅实现 Python 模型训练与推理。后续集成时，Python 模型服务应返回本脚本的 JSON；Spring Boot 负责鉴权、图片业务记录与调用模型服务，Vue 3 负责上传、显示带框图片、`brand_counts` 和 `total_count`。这与既有的“YOLO 识别 → 规则引擎 → 审核结果”架构一致。
