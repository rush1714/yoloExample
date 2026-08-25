# YOLOE Visual Prompt 品牌参考图预标注流程

流程：导入品牌参考图 → Excel 下载原图 → 常规 OCR 筛候选 → YOLOE visual prompt 预标注 → Label Studio 人工复核 → 导出 YOLO → 训练验证。

## 参考图要求

参考图目录：

```text
datasets/multibrand/visual_prompts/<品牌名>/
```

建议：

- 每张参考图最好是单个完整包装 crop。
- 避免整张货架图、多商品图、背景复杂图。
- 如果参考图质量差，YOLOE visual prompt 很容易召回很低或只产生整图大框。

## 导入品牌参考图

```bash
make visual-prompts-import \
  VISUAL_PROMPTS_EXCEL=/path/brand-images.xlsx \
  VISUAL_PROMPTS_BRAND_COLUMN=brand \
  VISUAL_PROMPTS_ATTACH_COLUMN=attach_file \
  VISUAL_PROMPTS_LIMIT=3
```

## 一键导入到 Label Studio

```bash
make workflow-to-ls-visual \
  BRAND=SOFTCARE \
  PSEUDO_LIMIT=20 \
  PSEUDO_VISUAL_DEVICE=mps \
  PSEUDO_VISUAL_REFERENCE_LIMIT=1
```

## 单步预标注

```bash
make pseudo-label-visual \
  BRAND=SOFTCARE \
  PSEUDO_USE_OCR_CANDIDATES=0 \
  PSEUDO_LIMIT=5 \
  PSEUDO_VISUAL_DEVICE=mps
```

## 人工复核后训练

```bash
make workflow-after-ls \
  BRAND=SOFTCARE \
  LS_PROJECT_ID=<项目ID> \
  TRAIN_EPOCHS=50
```

## 参数说明

| 变量 | 默认值 | 说明 | 示例 |
|---|---|---|---|
| `VISUAL_PROMPTS_EXCEL` | 本机品牌图片 Excel | 品牌参考图 Excel。 | `VISUAL_PROMPTS_EXCEL=/path/brand.xlsx` |
| `VISUAL_PROMPTS_BRAND_COLUMN` | `brand` | 品牌列名。 | `VISUAL_PROMPTS_BRAND_COLUMN=brand` |
| `VISUAL_PROMPTS_ATTACH_COLUMN` | `attach_file` | 图片 URL 列名。 | `VISUAL_PROMPTS_ATTACH_COLUMN=attach_file` |
| `VISUAL_PROMPTS_OUTPUT_ROOT` | `datasets/multibrand/visual_prompts` | 参考图保存根目录。 | 通常不改 |
| `VISUAL_PROMPTS_WORKERS` | `8` | 参考图下载并发数。 | `VISUAL_PROMPTS_WORKERS=4` |
| `VISUAL_PROMPTS_TIMEOUT` | `30` | 单图下载超时秒数。 | `VISUAL_PROMPTS_TIMEOUT=60` |
| `VISUAL_PROMPTS_LIMIT` | 空 | 导入 URL 数量上限。 | `VISUAL_PROMPTS_LIMIT=3` |
| `PSEUDO_VISUAL_MODEL` | `models/yoloe-26m-seg.pt` | YOLOE visual prompt 权重。 | `PSEUDO_VISUAL_MODEL=models/yoloe-26s-seg.pt` |
| `PSEUDO_VISUAL_REFERENCE_ROOT` | `datasets/multibrand/visual_prompts` | 参考图根目录。 | 通常不改 |
| `PSEUDO_VISUAL_REFERENCE_LIMIT` | 空 | 每个品牌最多使用多少张参考图。 | `PSEUDO_VISUAL_REFERENCE_LIMIT=1` |
| `PSEUDO_VISUAL_DEVICE` | `mps` | 推理设备。 | `PSEUDO_VISUAL_DEVICE=cpu` 或 `0` |
| `PSEUDO_LIMIT` | 空 | 处理图片数量上限。 | `PSEUDO_LIMIT=20` |
| `PSEUDO_CONF` | `0.03` | 候选框置信度。 | `PSEUDO_CONF=0.01` |
| `PSEUDO_MAX_AREA_RATIO` | `0.45` | 过滤整图大框。 | `PSEUDO_MAX_AREA_RATIO=0.30` |
| `PSEUDO_USE_OCR_CANDIDATES` | `1` | 是否只处理 OCR 候选清单。 | `PSEUDO_USE_OCR_CANDIDATES=0` |
