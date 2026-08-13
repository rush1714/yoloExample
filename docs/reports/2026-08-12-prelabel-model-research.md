# 预标注模型替代方案调研

日期：2026-08-12

## 背景

当前项目默认使用 `models/yolov8s-world.pt` 做 YOLO-World 开放词汇预标注。用户反馈预标注效果不准确，需要研究是否有更好的模型或流程。

当前预标注链路保持为：

```text
OCR 候选图片 -> YOLO-World/开放词汇模型生成候选框 -> Label Studio 人工复核 -> 导出正式 YOLO 训练集
```

## 本地现状核对

- 本地 Ultralytics 版本：`8.4.115`。
- 本地已可导入 `YOLOE` 类，说明当前环境具备尝试 YOLOE 的基础能力。
- 当前本地权重：
  - `models/yolov8s-world.pt`
  - `models/yolo26s.pt`
  - `models/yolo26m.pt`
  - `models/multibrand-best.pt`
- 历史 Softcare 预标注报告位置：`datasets/backup/softcare-2026-08-12-111600/pseudo/metadata/pseudo_label_report.json`。

历史 Softcare 预标注粗略统计：

| 指标 | 数值 |
|---|---:|
| 处理图片数 | 1344 |
| 有候选框图片数 | 1072 |
| 候选框总数 | 4833 |
| 置信度中位数 | 0.0495 |
| 置信度 75 分位 | 0.0747 |
| 置信度 90 分位 | 0.1203 |
| 最高置信度 | 0.7047 |

结论：现有 `yolov8s-world.pt` 更像“低阈值高召回的候选框生成器”，并不适合直接作为高可信预标注结果。多数候选框置信度很低，后续必须依赖人工复核。

## 官方资料结论

### 1. YOLO-World 可先升级到 v2 或更大模型

Ultralytics 官方 YOLO-World 文档说明，YOLO-World 是开放词汇检测模型，可通过自定义词表做零样本检测；官方模型包含 `yolov8s/m/l/x-world.pt` 以及 v2 系列。官方资料显示，v2 版本通常比旧版性能更好，且 `x` 规模模型能力高于 `s` 规模模型。

可优先试验：

1. `yolov8s-worldv2.pt`：最小改动，对比当前 `yolov8s-world.pt`。
2. `yolov8m-worldv2.pt`：平衡速度和效果。
3. `yolov8x-worldv2.pt`：优先验证上限，速度慢但更适合判断“模型能力是否是瓶颈”。

### 2. YOLOE 是更值得重点验证的新方案

Ultralytics 官方 YOLOE 文档说明，YOLOE 是面向开放词汇检测和分割的 promptable 模型，支持文本提示、视觉提示和 prompt-free 工作方式。对本项目这种“品牌包装外观固定、文字可能模糊、品牌名不一定是通用公开类别”的场景，YOLOE 的视觉提示能力比单纯文本 prompt 更值得验证。

可优先试验：

1. `yoloe-26s-seg.pt`：先验证流程可跑通。
2. `yoloe-26m-seg.pt`：作为主力候选。
3. `yoloe-26l-seg.pt`：用于验证效果上限。

YOLOE 输出的是分割/检测结果，若继续使用当前 Label Studio 矩形框复核流程，可以先把 mask 外接矩形转为 bbox；后续如果要提升边界质量，再扩展 Label Studio 分割标注。

### 3. SAM/auto_annotate 更适合“框或 mask 更准”，不解决品牌分类本身

Ultralytics 官方 `auto_annotate` 能用检测模型加 SAM 自动生成分割标签。这个方案的价值是提升目标边界质量，适合在已有较可靠检测模型时自动生成 mask；但它不会自动解决“哪个品牌”的分类问题。因此本项目若使用 SAM，建议放在“YOLOE/自训练检测器找出包装后，精修边界”的位置，而不是替代品牌识别模型。

## 为什么当前 YOLOv8s-world 不准

结合本项目数据和模型原理，主要原因不是单一权重文件问题：

1. **品牌包装不是通用开放词汇类别**：`SOFTCARE`、`KLEESOFT` 等品牌对开放词汇模型未必有稳定语义。
2. **提示词依赖文字和别名**：包装文字模糊、遮挡、斜拍时，文本 prompt 对模型帮助有限。
3. **小模型容量有限**：`s` 规模模型速度快，但复杂货架、小目标、多品牌混杂时能力不足。
4. **低阈值策略导致误检多**：当前 `PSEUDO_CONF=0.03` 是为了提高召回，会自然带来大量低置信度误框。
5. **品牌分类和包装定位耦合过紧**：当前每个品牌 prompt 直接生成品牌类别框，容易出现同一包装被多个品牌 prompt 命中，或品牌互相混淆。

## 推荐路线

### 路线 A：最小改动，先换 YOLO-World v2/大模型

目标：快速确认“更大/新版 YOLO-World 是否明显改善”。

建议顺序：

```text
yolov8s-worldv2.pt -> yolov8m-worldv2.pt -> yolov8x-worldv2.pt
```

评估方式：抽取同一批 50-100 张图片，在 Label Studio 中盲审同一批候选框，统计：

- 每图有效框数量。
- 明显误框数量。
- 漏标目标数量。
- 候选框是否覆盖真实包装。
- 人工修框耗时。

如果 `x-worldv2` 仍然不明显改善，说明开放词汇文本 prompt 不是最佳方向。

### 路线 B：重点推荐，试验 YOLOE 视觉提示

目标：用少量高质量参考包装图/框，引导模型识别同款或同品牌包装。

建议做法：

1. 每个重点品牌准备 3-10 个清晰参考 crop 或参考框。
2. 先选 3 个主要品牌验证：例如 `softcare`、`maya`、`clincleer`。
3. 使用 YOLOE visual prompt 对同一批图片做预标注。
4. 将输出 mask 外接矩形转成当前 Label Studio 兼容的 rectangle prediction。
5. 与 YOLO-World v2 在同一批样本上比较人工修正成本。

预期：对固定包装外观，YOLOE visual prompt 可能比纯文本 prompt 更稳定。

### 路线 C：中期最佳，训练“包装定位模型 + 品牌分类/规则”两阶段预标注

目标：降低开放词汇模型对品牌名的依赖。

建议结构：

```text
第一阶段：检测所有疑似商品包装/纸尿裤包装
第二阶段：对每个 crop 做品牌分类
  - OCR 命中品牌文字
  - CLIP/视觉相似度
  - 本地多模态模型辅助
  - 必要时人工复核
```

这样做的好处：

- 框的位置由“包装检测”解决，品牌类别由 OCR/分类解决。
- 对新品牌更容易扩展，只需补参考图和关键词。
- 减少 YOLO-World 多品牌 prompt 相互混淆。

### 路线 D：继续用已复核数据训练自有 YOLO，并反哺下一轮预标注

项目已有 `models/multibrand-best.pt`，虽然当前评估指标还不适合生产，但可以作为主动学习工具：

1. 用自训练模型找高置信候选框。
2. 用 YOLO-World/YOLOE 找漏检候选框。
3. 合并候选，人工复核。
4. 下一轮训练只纳入人工复核后的干净标签。

中长期看，真正稳定的预标注器应当是“本项目自己的模型”，开放词汇模型主要用于冷启动和补漏。

## 下一步实验建议

建议按成本从低到高执行：

1. **试 YOLO-World v2**：先跑 `yolov8m-worldv2.pt` 和 `yolov8x-worldv2.pt`，只抽样 50 张。
2. **试 YOLOE 视觉提示**：选 3 个主品牌，每个品牌 5 个参考 crop。
3. **建立人工评估表**：不要只看模型置信度，统计人工修正时间、有效框率、漏检数。
4. **如果 YOLOE 明显更好**：改造 `scripts/pseudo_label/`，新增 YOLOE 分支，不替换原 YOLO-World 分支。
5. **如果 YOLOE 也一般**：转向“两阶段：包装检测 + 品牌分类/OCR”。

## 参考资料

- Ultralytics YOLO-World 官方文档：https://docs.ultralytics.com/models/yolo-world/
- Ultralytics YOLOE 官方文档：https://docs.ultralytics.com/models/yoloe/
- Ultralytics auto_annotate/SAM 官方说明：https://docs.ultralytics.com/usage/simple-utilities/

## 2026-08-12 实现补充：YOLO-World v2 A/B 测试脚本

已新增脚本：`scripts/pseudo_label/ab_test_yolo_world.py`。

脚本能力：

- 默认对比 `models/yolov8s-world.pt`、`yolov8m-worldv2.pt`、`yolov8x-worldv2.pt`。
- 使用同一批图片、同一组品牌提示词、同一组 NMS/覆盖过滤/跨品牌去重参数。
- 每个模型单独输出：
  - `metadata/prediction_rows.json`：逐图完整候选框明细。
  - `metadata/prediction_rows.csv`：逐图候选框数量表。
  - `metadata/summary.json`：单模型汇总。
  - `labels/<split>/*.txt`：YOLO 格式候选标签。
  - `previews/*.jpg`：带框预览图，用于快速肉眼检查。
- 总报告输出：`yolo_world_ab_report.md` 和 `metadata/model_summary.json`。

Makefile 已新增命令：

```bash
make yolo-world-ab-test AB_LIMIT=50
```

常用调参示例：

```bash
# 不使用 OCR 候选清单，直接从 raw/images 抽 30 张对比
make yolo-world-ab-test AB_USE_OCR_CANDIDATES=0 AB_LIMIT=30

# 只对 Softcare 做 A/B，输出目录随 BRAND 隔离
make yolo-world-ab-test BRAND=SOFTCARE AB_LIMIT=50

# 只对 Softcare 做 A/B，不使用 OCR 候选清单,输出目录随 BRAND 隔离
make yolo-world-ab-test AB_USE_OCR_CANDIDATES=0 BRAND=SOFTCARE AB_LIMIT=50

# 自定义对比模型
make yolo-world-ab-test AB_MODELS=models/yolov8s-world.pt,yolov8m-worldv2.pt AB_LIMIT=20

# 自定义对比模型 只对 Softcare 做 A/B，不使用 OCR 候选清单,输出目录随 BRAND 隔离
make yolo-world-ab-test AB_USE_OCR_CANDIDATES=0 AB_MODELS=models/yolov8s-world.pt,yolov8m-worldv2.pt AB_LIMIT=20
```

注意：A/B 报告里的候选框数和置信度只能做初筛，最终仍需人工抽检有效框率、漏检数、重复框、品牌混淆和修框耗时。

## 2026-08-12 实现补充：YOLOE visual prompt 预标注分支

已新增独立脚本：`scripts/pseudo_label/generate_yoloe_visual.py`。

实现方式：

- 使用 Ultralytics YOLOE 的 visual prompt 能力：参考图 bbox 描述的是参考图片里的目标包装，再用该参考外观去目标图片中找相似目标。
- 默认参考图目录：`datasets/multibrand/visual_prompts/`。
- 目录约定：

```text
datasets/multibrand/visual_prompts/
├── SOFTCARE/
│   ├── ref1.jpg
│   └── ref2.webp
├── MAYA/
│   └── ref1.png
└── MEDIPOWER/
    └── ref1.jpg
```

- 品牌目录名可使用品牌显示名、`class_name` 或品牌别名；脚本会按 `config/brand_keywords.json` 做规范化匹配。
- 默认假设参考图就是裁好的包装图，整张参考图作为 visual prompt bbox。
- 如果参考图不是裁好的包装图，可放同名 JSON sidecar，例如 `ref.jpg` + `ref.json`：

```json
{"bbox": [x1, y1, x2, y2]}
```

- 输出仍复用既有伪标注结构：`pseudo/images/<split>/`、`pseudo/labels/<split>/`、`pseudo/metadata/`，因此后续 `ls-import-json` 和 `ls-apply` 不需要改造。
- 每张参考图会单独跑一次 YOLOE visual prompt；同一目标图上多参考图结果会合并，并复用既有 NMS、大框过滤、跨品牌去重逻辑。

推荐验证顺序：

1. `models/yoloe-26s-seg.pt`：先跑通完整流程。
2. `models/yoloe-26m-seg.pt`：作为主力候选。
3. `models/yoloe-26l-seg.pt`：用于验证效果上限。

Makefile 已新增命令：

```bash
# 端到端：Excel 导入 -> OCR -> YOLOE visual prompt 预标注 -> 导入 Label Studio
make workflow-to-ls-visual BRAND=SOFTCARE PSEUDO_LIMIT=20

# 只跑 YOLOE visual prompt 预标注；不使用 OCR 候选清单，便于先抽样全量 raw 图片
make pseudo-label-visual BRAND=SOFTCARE PSEUDO_USE_OCR_CANDIDATES=0 PSEUDO_LIMIT=5

# 切换到 m 模型验证主力候选
make pseudo-label-visual PSEUDO_VISUAL_MODEL=models/yoloe-26m-seg.pt PSEUDO_LIMIT=30

# 每个品牌只取 1 张参考图做快速烟测
make pseudo-label-visual BRAND=SOFTCARE PSEUDO_VISUAL_REFERENCE_LIMIT=1 PSEUDO_LIMIT=5
```

注意事项：

- 真实效果高度依赖参考图质量。优先放清晰、正面、只包含单个目标包装的 crop。
- 多品牌运行时，每个品牌都必须在 `visual_prompts/<品牌名>/` 下至少有一张参考图，否则脚本会拒绝继续，避免某些品牌被静默漏标。
- 当前只把 YOLOE 输出转换为矩形框，保持 Label Studio 复核流程不变；后续如要利用分割 mask，可再扩展为分割标注流程。
- 该分支仍然是“候选框生成器”，不能直接把结果当最终训练标签；必须人工抽检有效框率、漏检数、重复框和品牌混淆情况。

本地验证结果：

- `generate_yoloe_visual.py --help` 可正常展示参数，已包含 `--reference-root`、`--reference-limit`、`--dry-run`、`--cross-brand-dedup/--no-cross-brand-dedup`。
- `tests/test_yoloe_visual.py` 通过 7 个用例，覆盖权重路径解析、品牌参考目录匹配、参考框 JSON sidecar、缺参考图中文错误和 YOLO 标签写出。
- `python -m unittest discover -s tests -p 'test_*.py'` 通过 19 个用例；旧测试仍会打印一次 Matplotlib 缓存目录提示，但不影响退出结果。
- `pylint scripts/pseudo_label/generate_yoloe_visual.py tests/test_yoloe_visual.py` 评分为 `10.00/10`。
- 使用临时参考图目录对 `data/samples/multibrand-shelf.webp` 做 dry-run，确认单品牌参考图能被识别；再使用 `models/yoloe-26s-seg.pt` 跑 1 张样例图，流程成功产出 `pseudo/images`、`pseudo/labels`、`pseudo/metadata`。该烟测只验证链路，不代表真实品牌效果，因为临时参考图并非真实裁剪包装图。

## 2026-08-12 实现补充：品牌参考图 Excel 导入到 YOLOE visual prompts

已新增独立脚本：`scripts/data_import/import_visual_prompts_from_excel.py`。

用途：把品牌图片 Excel 中的参考包装图自动下载到 YOLOE visual prompt 目录，避免手工逐张保存参考图。

默认输入与输出：

- Excel：`/Users/guobiao/Downloads/品牌图片_1786521889720.xlsx`
- 品牌列：`brand`
- 图片 URL 列：`attach_file`
- 参考图目录：`datasets/multibrand/visual_prompts/<品牌>/`
- 下载报告：
  - `datasets/multibrand/visual_prompts/metadata/download_report.csv`
  - `datasets/multibrand/visual_prompts/metadata/download_report.json`

实现细节：

- 支持同一个单元格中用换行、逗号、中文逗号或分号分隔多个 URL。
- 对完整 URL 做全局去重，避免同一张参考图重复下载。
- 品牌名会清洗为安全目录名，例如 `SOFT CARE/2026` 会落到 `SOFT_CARE_2026/`。
- 文件命名格式为 `row<Excel行号>_<URL序号>_<原附件名>.<后缀>`，例如 `row00002_01_Z-1.png`。
- 下载完成后使用 PIL 校验图片完整性；如果远端返回空内容或非图片内容，会记录为 `failed` 并删除异常文件。
- 当 Excel 中所有待下载 URL 都已有对应本地图片时，会直接写 `skipped` 报告，不再发起网络请求。
- 新增 Make 命令：

```bash
# 小批量烟测，只导入 3 张
make visual-prompts-import VISUAL_PROMPTS_LIMIT=3

# 全量导入
make visual-prompts-import
```

本地验证结果：

- 已新增 `tests/test_visual_prompts_import.py`，覆盖品牌目录名清洗、Excel 读取、多 URL 拆分、URL 去重、目标路径生成、已下载跳过判断、JSON/CSV 报告输出。
- `PYTHONPATH=scripts .venv/bin/python tests/test_visual_prompts_import.py` 通过 7 个用例。
- `PYTHONPATH=scripts .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` 通过 26 个用例；旧测试仍会打印一次 Matplotlib 缓存目录提示，但不影响退出结果。
- `PYLINTHOME=.tmp/pylint PYTHONPATH=scripts .venv/bin/pylint scripts/data_import/import_visual_prompts_from_excel.py tests/test_visual_prompts_import.py` 评分为 `10.00/10`。
- `make -n visual-prompts-import VISUAL_PROMPTS_LIMIT=3` 已确认 Make 命令参数展开正确。
- 沙箱内首次下载因 DNS 受限失败，联网权限放开后执行 `make visual-prompts-import VISUAL_PROMPTS_LIMIT=3` 成功下载 3 张 `softcare` 参考图，结果为 `downloaded=3, skipped=0, failed=0`。

注意事项：

- 真实参考图和 `visual_prompts/metadata/` 下载报告属于本地数据资产，默认被 `.gitignore` 忽略，不提交到 Git。
- 该导入脚本只负责收集参考图，不判断参考图是否是高质量包装 crop；后续运行 YOLOE visual prompt 前仍建议人工抽查参考图是否清晰、正面、主体单一。
