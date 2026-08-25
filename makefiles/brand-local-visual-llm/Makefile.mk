# 本地视觉大模型流程别名；当前复用 Ollama 视觉 OCR + YOLO-World 全流程

.PHONY: local-visual-llm-ocr workflow-to-ls-local-visual-llm local-visual-llm-workflow-after-ls

local-visual-llm-ocr: ocr-llm ## 本地视觉大模型 OCR 别名

workflow-to-ls-local-visual-llm: workflow-to-ls-llm ## 本地视觉大模型 OCR + YOLO-World 到 Label Studio

local-visual-llm-workflow-after-ls: workflow-after-ls ## 本地视觉大模型流程人工复核后导出、训练并验证
