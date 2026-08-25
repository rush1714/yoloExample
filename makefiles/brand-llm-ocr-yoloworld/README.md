# Ollama 本地视觉大模型 OCR + YOLO-World 流程

流程：Excel 下载原图 → Ollama 视觉模型 OCR 筛品牌候选 → YOLO-World 预标注 → Label Studio 人工复核 → 导出 YOLO → 训练与推理验证。

> 注意：本模块是真正执行 Ollama 视觉 OCR 的模块；`brand-local-visual-llm` 当前只是它的语义化别名入口。

## 一键导入到 Label Studio

```bash
make workflow-to-ls-llm \
  BRAND=SOFTCARE \
  LLM_OCR_MODEL=gemma3:12b \
  LLM_OCR_WORKERS=1 \
  OCR_RESUME=1 \
  PSEUDO_LIMIT=20
```

## 中断恢复

Ollama 单图可能较慢，若中断后继续：

```bash
make step-2-ocr-llm \
  BRAND=SOFTCARE \
  OCR_RESUME=1 \
  LLM_OCR_MODEL=gemma3:12b
```

恢复时会读取：

```text
datasets/<brand>/ocr/metadata/ocr_softcare_report.json
```

并跳过已完成图片。

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
| `LLM_OCR_MODEL` | `gemma3:12b` | Ollama 视觉模型名称。 | `LLM_OCR_MODEL=qwen3.6:latest` |
| `LLM_OCR_URL` | `http://127.0.0.1:11434` | Ollama HTTP API 地址。 | `LLM_OCR_URL=http://localhost:11434` |
| `LLM_OCR_TIMEOUT` | `180` | 单图请求超时秒数。 | `LLM_OCR_TIMEOUT=300` |
| `LLM_OCR_WORKERS` | `1` | 并发请求数，本地模型建议 1。 | `LLM_OCR_WORKERS=2` |
| `LLM_OCR_MAX_IMAGE_SIDE` | `1280` | 送入视觉模型前最长边。 | `LLM_OCR_MAX_IMAGE_SIDE=960` |
| `LLM_OCR_JPEG_QUALITY` | `90` | 转 JPEG 的质量。 | `LLM_OCR_JPEG_QUALITY=85` |
| `OCR_RESUME` | `0` | 从已有 OCR JSON 恢复。 | `OCR_RESUME=1` |
| `OCR_LIMIT` | 空 | OCR 处理数量上限。 | `OCR_LIMIT=20` |
| `OCR_FUZZY_THRESHOLD` | `60` | 品牌模糊匹配阈值。 | `OCR_FUZZY_THRESHOLD=70` |
| `PSEUDO_LIMIT` | 空 | 后续 YOLO-World 预标注数量上限。 | `PSEUDO_LIMIT=20` |

## 完整示例

```bash
# 先少量试跑，确认模型和候选清单正常
make workflow-to-ls-llm \
  BRAND=SOFTCARE \
  OCR_LIMIT=10 \
  PSEUDO_LIMIT=10 \
  LLM_OCR_MODEL=gemma3:12b

# 中断后恢复 OCR，并继续后续预标注和导入
make workflow-to-ls-llm \
  BRAND=SOFTCARE \
  OCR_RESUME=1 \
  LLM_OCR_MODEL=gemma3:12b
```
