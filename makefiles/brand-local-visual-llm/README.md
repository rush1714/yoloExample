# 本地视觉大模型流程

当前本地视觉大模型能力主要用于 OCR 阶段：用 Ollama 视觉模型识别图片中的品牌文字，然后复用 YOLO-World 做预标注。

**和 `brand-llm-ocr-yoloworld` 的关系：**

- `brand-llm-ocr-yoloworld` 是实际实现目录。
- 本目录提供语义化别名，方便你按“本地视觉大模型流程”理解和调用。
- 当前两者调用链路一致；后续如果新增“本地视觉大模型直接预标注”的脚本，会放到本目录，不再只是别名。

## 导入到 Label Studio

```bash
make workflow-to-ls-local-visual-llm \
  BRAND=SOFTCARE \
  LLM_OCR_MODEL=gemma3:12b \
  OCR_RESUME=1 \
  PSEUDO_LIMIT=20
```

## 人工复核后训练

```bash
make local-visual-llm-workflow-after-ls \
  BRAND=SOFTCARE \
  LS_PROJECT_ID=<项目ID> \
  TRAIN_EPOCHS=50
```

## 单步 OCR

```bash
make local-visual-llm-ocr \
  BRAND=SOFTCARE \
  OCR_LIMIT=5 \
  LLM_OCR_MODEL=gemma3:12b
```

## 常用变量

这些变量来自 `brand-llm-ocr-yoloworld/Makefile.mk`，因为当前实现复用它：

| 变量 | 说明 | 示例 |
|---|---|---|
| `LLM_OCR_MODEL` | Ollama 视觉模型名。 | `LLM_OCR_MODEL=gemma3:12b` |
| `LLM_OCR_URL` | Ollama API 地址。 | `LLM_OCR_URL=http://127.0.0.1:11434` |
| `LLM_OCR_WORKERS` | 并发数，本地建议 1。 | `LLM_OCR_WORKERS=1` |
| `OCR_RESUME` | 从已有 OCR JSON 恢复。 | `OCR_RESUME=1` |
| `PSEUDO_LIMIT` | 后续预标注图片数上限。 | `PSEUDO_LIMIT=20` |
