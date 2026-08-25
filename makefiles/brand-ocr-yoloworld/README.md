# 常规 OCR + YOLO-World 品牌预标注流程

流程：Excel 下载原图 → 常规 OCR 筛品牌候选 → YOLO-World 预标注 → Label Studio 人工复核 → 导出 YOLO → 训练与推理验证。

## 一键导入到 Label Studio

```bash
make workflow-to-ls \
  BRAND=SOFTCARE \
  OCR_WORKERS=4 \
  OCR_RESUME=1 \
  PSEUDO_LIMIT=20 \
  PSEUDO_CONF=0.03 \
  PSEUDO_IMGSZ=960
```

## 人工复核后训练和验证

```bash
make workflow-after-ls \
  BRAND=SOFTCARE \
  LS_PROJECT_ID=<项目ID> \
  TRAIN_EPOCHS=50 \
  TRAIN_DEVICE=mps
```

## 单步命令

```bash
# 1. 下载原始图片到 datasets/multibrand/raw/images
make step-1-import-excel EXCEL=/path/images.xlsx EXCEL_COLUMN=整改后图片URL

# 2. OCR 识别当前品牌候选图
make step-2-ocr BRAND=SOFTCARE OCR_WORKERS=4 OCR_RESUME=1

# 3. YOLO-World 预标注
make step-3-pseudo-label BRAND=SOFTCARE PSEUDO_LIMIT=20 PSEUDO_CONF=0.03

# 4. 导入 Label Studio
make step-4-import-ls BRAND=SOFTCARE

# 5. 人工复核后导出并转换 YOLO 数据
make step-5-export-ls-to-train BRAND=SOFTCARE LS_PROJECT_ID=<项目ID> LS_TO_YOLO_CLEAR=1

# 6/7. 训练和推理验证
make step-6-train BRAND=SOFTCARE TRAIN_EPOCHS=50
make step-7-validate BRAND=SOFTCARE
```

## 参数说明

| 变量 | 默认值 | 说明 | 示例 |
|---|---|---|---|
| `BRAND_DATA_YAML` | `$(TRAIN_DATA_YAML)` | 当前品牌正式训练 YAML 输出路径。 | 通常无需覆盖 |
| `BRAND_PSEUDO_YAML` | `config/generated/<brand>_pseudo.yaml` | 当前品牌伪标注 YAML 输出路径。 | 通常无需覆盖 |
| `OCR_ENGINE` | `rapidocr` | OCR 引擎，可选 `rapidocr` / `easyocr`。 | `OCR_ENGINE=easyocr` |
| `OCR_WORKERS` | `10` | 常规 OCR 并发线程数。 | `OCR_WORKERS=4` |
| `OCR_KEYWORD_ARGS` | 空 | 追加 OCR 关键词参数。 | `OCR_KEYWORD_ARGS="--keyword SOFTCARE"` |
| `OCR_LANGUAGES` | `en` | EasyOCR 语言列表。 | `OCR_LANGUAGES="en ch_sim"` |
| `OCR_MIN_CONFIDENCE` | `0.2` | OCR 文本最低置信度。 | `OCR_MIN_CONFIDENCE=0.3` |
| `OCR_FUZZY_THRESHOLD` | `60` | 品牌关键词模糊匹配阈值。 | `OCR_FUZZY_THRESHOLD=70` |
| `OCR_LIMIT` | 空 | OCR 处理图片数量上限。 | `OCR_LIMIT=100` |
| `OCR_COPY_CANDIDATES` | `0` | 是否复制命中图片到 `ocr/candidates`。 | `OCR_COPY_CANDIDATES=1` |
| `OCR_RESUME` | `0` | 是否从已有 OCR JSON 恢复并跳过已完成图片。 | `OCR_RESUME=1` |
| `PSEUDO_MODEL` | `models/yolov8s-world.pt` | YOLO-World 权重。 | `PSEUDO_MODEL=models/yolov8m-world.pt` |
| `PSEUDO_PROMPT_ARGS` | 空 | 额外开放词汇提示词模板，多品牌建议包含 `{brand}`。 | `PSEUDO_PROMPT_ARGS="--prompt '{brand} package on shelf'"` |
| `PSEUDO_INCLUDE_BRAND_PACKAGE_PROMPTS` | `1` | 是否自动加入 `<brand> package` 类提示词。 | `PSEUDO_INCLUDE_BRAND_PACKAGE_PROMPTS=0` |
| `PSEUDO_NMS_IOU` | `0.45` | 同类重复框 NMS IoU 阈值。 | `PSEUDO_NMS_IOU=0.35` |
| `PSEUDO_CONTAINMENT` | `0.85` | 大框覆盖小框过滤阈值。 | `PSEUDO_CONTAINMENT=0.75` |
| `PSEUDO_MAX_AREA_RATIO` | `0.45` | 最大框面积占整图比例。 | `PSEUDO_MAX_AREA_RATIO=0.30` |
| `PSEUDO_CROSS_BRAND_DEDUP` | `1` | 是否启用跨品牌去重。 | `PSEUDO_CROSS_BRAND_DEDUP=0` |
| `PSEUDO_CROSS_BRAND_IOU` | `0.35` | 跨品牌重复框 IoU 阈值。 | `PSEUDO_CROSS_BRAND_IOU=0.25` |
| `PSEUDO_CROSS_BRAND_CONTAINMENT` | `0.80` | 跨品牌覆盖过滤阈值。 | `PSEUDO_CROSS_BRAND_CONTAINMENT=0.70` |
| `PSEUDO_CONF` | `0.03` | YOLO-World 检测置信度。 | `PSEUDO_CONF=0.05` |
| `PSEUDO_IMGSZ` | `960` | 推理图片尺寸。 | `PSEUDO_IMGSZ=1280` |
| `PSEUDO_LIMIT` | 空 | 预标注处理图片数量上限。 | `PSEUDO_LIMIT=20` |
| `PSEUDO_USE_OCR_CANDIDATES` | `1` | 是否只处理 OCR 候选清单。 | `PSEUDO_USE_OCR_CANDIDATES=0` |
| `AB_MODELS` | 多个 world 模型 | A/B 测试模型列表，逗号分隔。 | `AB_MODELS=models/yolov8s-world.pt,models/yolov8m-world.pt` |
| `AB_LIMIT` | `50` | A/B 测试图片数量。 | `AB_LIMIT=20` |
| `AB_PREVIEW_LIMIT` | `30` | 每个模型保存预览图数量。 | `AB_PREVIEW_LIMIT=10` |

## A/B 测试示例

```bash
make yolo-world-ab-test \
  BRAND=SOFTCARE \
  AB_LIMIT=50 \
  AB_MODELS=models/yolov8s-world.pt,models/yolov8m-world.pt,models/yolov8x-worldv2.pt
```
