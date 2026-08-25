# Ollama 本地视觉大模型 OCR + YOLO-World 预标注完整流程

# ── Ollama 视觉 OCR 参数 ─────────────────────────────────────
# 该模块复用 OCR 候选清单路径和恢复语义，因此这里显式定义所需 OCR 变量，避免依赖其它模块。
OCR_KEYWORD_ARGS    ?=
OCR_FUZZY_THRESHOLD ?= 60
OCR_LIMIT           ?=
OCR_COPY_CANDIDATES ?= 0
OCR_RESUME          ?= 0
OCR_LIMIT_ARG       := $(if $(OCR_LIMIT),--limit $(OCR_LIMIT),)
OCR_COPY_ARG        := $(if $(filter 1 true yes,$(OCR_COPY_CANDIDATES)),--copy-candidates,)
OCR_RESUME_ARG      := $(if $(filter 1 true yes,$(OCR_RESUME)),--resume,)
LLM_OCR_MODEL       ?= gemma3:12b
LLM_OCR_URL         ?= http://127.0.0.1:11434
LLM_OCR_TIMEOUT     ?= 180
LLM_OCR_WORKERS     ?= 1
LLM_OCR_MAX_IMAGE_SIDE ?= 1280
LLM_OCR_JPEG_QUALITY ?= 90

.PHONY: step-2-ocr-llm workflow-to-ls-llm ocr-llm

step-2-ocr-llm: ocr-llm ## 2. 使用 Ollama 本地视觉大模型 OCR 生成候选图片清单

workflow-to-ls-llm: step-1-import-excel step-2-ocr-llm step-3-pseudo-label step-4-import-ls ## Ollama OCR + YOLO-World 到 Label Studio

ocr-llm: ## 使用 Ollama 本地视觉大模型 OCR 生成品牌候选图片清单
	$(VENV_BIN)/python scripts/ocr/filter_brand_candidates_llm.py \
		--raw-dir $(RAW_DIR) \
		--output-dir $(OCR_OUTPUT_DIR) \
		--brand-library $(BRAND_LIBRARY) \
		$(BRAND_FILTER_ARG) \
		$(OCR_KEYWORD_ARGS) \
		--model $(LLM_OCR_MODEL) \
		--ollama-url $(LLM_OCR_URL) \
		--timeout $(LLM_OCR_TIMEOUT) \
		--workers $(LLM_OCR_WORKERS) \
		--fuzzy-threshold $(OCR_FUZZY_THRESHOLD) \
		--max-image-side $(LLM_OCR_MAX_IMAGE_SIDE) \
		--jpeg-quality $(LLM_OCR_JPEG_QUALITY) \
		$(OCR_LIMIT_ARG) \
		$(OCR_COPY_ARG) \
		$(OCR_RESUME_ARG)
