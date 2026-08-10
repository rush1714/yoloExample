# OCR 并行化与 Ollama 本地大模型 OCR 方案

## 背景与现状

- 当前 OCR 主流程由 `scripts/ocr/filter_brand_candidates.py` 实现，Make 目标为 `step-2-ocr` / `ocr`。
- 当前脚本逐张图片串行执行 OCR，结果写入：
  - `datasets/multibrand/ocr/metadata/ocr_softcare_report.csv`
  - `datasets/multibrand/ocr/metadata/ocr_softcare_report.json`
  - `datasets/multibrand/ocr/metadata/ocr_candidates.txt`
- 后续 `step-3-pseudo-label` 默认读取同一个 `ocr_candidates.txt`，所以新方案只要保持该输出格式，后续流程无需改变。
- 本机 Ollama 已有可用视觉模型：
  - `gemma3:12b`：支持 vision，样例图 OCR 输出 `Softcare, Colgate, Pepsodent, Longrich`，速度相对较快，推荐作为默认。
  - `qwen3.6:latest`：支持 vision/tools/thinking，样例图 OCR 输出更丰富，但 23GB、速度明显更慢，可作为高精度备选。
  - `minicpm-v:latest`：支持 vision，能识别中文品牌，但英文品牌召回不如 `gemma3:12b` 稳定，可作为备选。

## 实施计划

### 1. 改造现有 OCR 为多线程

修改 `scripts/ocr/filter_brand_candidates.py`：

- 增加 `--workers` 参数，默认值建议为 `4`。
- 使用 `ThreadPoolExecutor + as_completed` 并发处理图片。
- 每个线程用 thread-local 懒加载自己的 OCR reader，避免多个线程共享同一个 RapidOCR/EasyOCR reader 导致线程安全问题。
- 保持输出数据结构 `OcrResult`、CSV/JSON 报告、`ocr_candidates.txt` 不变。
- 结果按原始图片排序写报告，避免并发完成顺序导致报告顺序随机。
- 参数校验：`--workers >= 1`。
- 保留 `--workers 1` 作为完全兼容的串行模式。

同步修改 `Makefile`：

- 新增 `OCR_WORKERS ?= 4`。
- `ocr` 目标向脚本传 `--workers $(OCR_WORKERS)`。
- 帮助文案增加 `OCR_WORKERS` 说明。
- 将 `OCR_ENGINE` 默认值改为 `rapidocr`，与 README/设计文档中“默认 RapidOCR、CPU 快”的说明保持一致；如需 EasyOCR 仍可用 `OCR_ENGINE=easyocr` 覆盖。

### 2. 新增 Ollama 本地大模型 OCR 工具

新增脚本：`scripts/ocr/filter_brand_candidates_llm.py`。

核心行为：

- 使用 Ollama HTTP API：`POST /api/generate`。
- 默认模型：`gemma3:12b`。
- 支持参数：
  - `--raw-dir`
  - `--output-dir`
  - `--brand-library`
  - `--keyword`
  - `--no-brand-library`
  - `--model`
  - `--ollama-url`
  - `--timeout`
  - `--workers`
  - `--limit`
  - `--copy-candidates`
  - `--fuzzy-threshold`
  - `--max-image-side`
  - `--jpeg-quality`
- 为避免 Ollama 视觉模型无法直接读取 WebP，脚本会先用 Pillow 将图片转为 RGB JPEG，再 base64 传给 Ollama。
- 提示词要求模型只输出图片可见品牌/包装文字，优先 JSON 格式；脚本会兼容 JSON 数组、JSON 对象和普通逗号/换行文本。
- 将模型返回文本转成 `OcrText(text=..., confidence=1.0, box=[])`，复用现有 `match_keywords()` 和 `write_reports()`。
- 输出仍写到同一套 OCR metadata 文件和 `ocr_candidates.txt`，保证后续 `step-3-pseudo-label` / Label Studio 流程不变。
- 若 Ollama 未启动、模型不存在或请求失败，给出明确错误并写入该图片的空识别结果或终止（实现时采用明确错误输出，避免静默误判）。

默认并发策略：

- `LLM_OCR_WORKERS ?= 1`，因为 Ollama 本地大模型通常单路推理更稳。
- 支持用户手动提高，例如 `LLM_OCR_WORKERS=2`；如果本机 Ollama 配置允许并行请求，可自行调大。

### 3. 新增 Make workflow-to-ls-llm 命令

修改 `Makefile`：

- 新增参数：
  - `LLM_OCR_MODEL ?= gemma3:12b`
  - `LLM_OCR_URL ?= http://127.0.0.1:11434`
  - `LLM_OCR_TIMEOUT ?= 180`
  - `LLM_OCR_WORKERS ?= 1`
  - `LLM_OCR_MAX_IMAGE_SIDE ?= 1280`
  - `LLM_OCR_JPEG_QUALITY ?= 90`
- 新增目标：
  - `ocr-llm`：运行新脚本生成同一套 OCR 输出。
  - `step-2-ocr-llm: ocr-llm`：作为 LLM OCR 的第二步。
  - `workflow-to-ls-llm: step-1-import-excel step-2-ocr-llm step-3-pseudo-label step-4-import-ls`。
- 后续 `step-3-pseudo-label`、`step-4-import-ls` 不改，继续使用 `OCR_CANDIDATES_FILE`。

### 4. 文档与报告同步

按项目约定同步更新：

- `设计.md`：阶段 1 增加“RapidOCR/EasyOCR 支持多线程”和“Ollama 本地多模态大模型 OCR 分支”的说明；阶段 2 Makefile 流程增加 `workflow-to-ls-llm`。
- `README.md`：增加使用示例：
  - 常规并行 OCR：`make step-2-ocr OCR_WORKERS=4`
  - LLM OCR：`make step-2-ocr-llm LLM_OCR_MODEL=gemma3:12b`
  - 完整流程：`make workflow-to-ls-llm`
- `docs/reports/softcare-yolo-setup-2026-08-05.md`：追加 2026-08-10 的阶段性记录，说明并行 OCR 与 Ollama LLM OCR 的新增能力和本机模型选择结果。

### 5. 验证计划

实施后执行：

1. 语法检查：
   - `.venv/bin/python -m compileall scripts/ocr/filter_brand_candidates.py scripts/ocr/filter_brand_candidates_llm.py`
2. 小批量并行 OCR：
   - `make step-2-ocr OCR_LIMIT=2 OCR_WORKERS=2 OCR_ENGINE=rapidocr`
3. 小批量 LLM OCR：
   - `make step-2-ocr-llm OCR_LIMIT=1 LLM_OCR_MODEL=gemma3:12b`
4. 静态检查：
   - `.venv/bin/pylint scripts/ocr/filter_brand_candidates.py scripts/ocr/filter_brand_candidates_llm.py`

如果 pylint 暂无项目配置或现有风格导致告警，会如实记录输出，并优先修复本次新增/修改代码中的问题。