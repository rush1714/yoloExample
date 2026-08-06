# 项目根目录：默认等于当前执行 make 的目录；通常不需要修改。
PROJECT_ROOT := $(shell pwd)
# Python 虚拟环境 bin 目录：所有 Python/Label Studio 命令都从这里执行。
VENV_BIN     := $(PROJECT_ROOT)/.venv/bin
# 项目内临时目录：替代 /tmp，避免命令在系统临时目录中产生不可追踪状态。
TMP_DIR      := $(PROJECT_ROOT)/.tmp
# Label Studio shell/start 的工作目录：用于避开当前目录导入安全问题，同时仍在项目内。
LS_WORK_DIR  := $(TMP_DIR)/label-studio
# Label Studio 应用数据目录：保存本地配置、上传文件等运行数据；数据库本体使用 PostgreSQL。
LS_DATA_DIR  := $(PROJECT_ROOT)/.label-studio-data
# 日志目录：Label Studio 后台启动日志、PID 文件等写入这里。
LOG_DIR      := $(PROJECT_ROOT)/logs

# ── 1. Excel 数据导入参数 ────────────────────────────────────
# Excel 文件路径；可改成任意包含图片 URL 列的本地 xlsx 文件。
# 示例：make step-1-import-excel EXCEL=/path/to/file.xlsx
EXCEL              ?= /Users/guobiao/Downloads/8e96894159cc584f0c7a27faaa4acc45.xlsx
# Excel 中存放图片 URL 的列名；改错会导致脚本提示找不到列。
# 示例：make step-1-import-excel EXCEL_COLUMN=整改后图片URL
EXCEL_COLUMN       ?= 整改后图片URL
# 并发下载线程数；调大可加快下载，但可能被远端限流；网络不稳定时可降到 2/4。
EXCEL_WORKERS      ?= 8
# 单张图片下载超时时间（秒）；远端慢时可调大，例如 60。
EXCEL_TIMEOUT      ?= 30

# ── 数据目录参数 ─────────────────────────────────────────────
# 多品牌数据集根目录；如要复制一套实验数据，可整体改到其它目录。
DATASET_ROOT       ?= $(PROJECT_ROOT)/datasets/multibrand
# Excel 下载后的原始图片目录；OCR 和预标注默认从这里读取图片。
RAW_DIR            ?= $(DATASET_ROOT)/raw/images
# Excel 下载报告目录；ls-import-json 默认读取其中的 download_report.csv。
RAW_METADATA_DIR   ?= $(DATASET_ROOT)/raw/metadata
# OCR 输出目录；包含 candidates 和 metadata。
OCR_OUTPUT_DIR     ?= $(DATASET_ROOT)/ocr
# OCR 候选图片清单；预标注默认只处理这个清单中的图片。
OCR_CANDIDATES_FILE ?= $(OCR_OUTPUT_DIR)/metadata/ocr_candidates.txt
# YOLO-World 预标注输出目录；生成 pseudo/images 和 pseudo/labels。
PSEUDO_ROOT        ?= $(DATASET_ROOT)/pseudo
# 正式 YOLO 数据集配置；训练和数据集校验都读取该 yaml。
TRAIN_DATA_YAML    ?= $(PROJECT_ROOT)/data/multibrand.yaml
# 品牌标识库；OCR、预标注、Label Studio 多标签和 YOLO names 都以它为类别来源。
BRAND_LIBRARY      ?= $(PROJECT_ROOT)/data/brand_keywords.json
# 正式训练数据 YAML；brand-yaml 会根据 BRAND_LIBRARY 自动写入多品牌 names。
BRAND_DATA_YAML    ?= $(PROJECT_ROOT)/data/multibrand.yaml
# 伪标注数据 YAML；brand-yaml 会根据 BRAND_LIBRARY 自动写入多品牌 names。
BRAND_PSEUDO_YAML  ?= $(PROJECT_ROOT)/data/multibrand_pseudo.yaml
# 可选：导出当前品牌库生成的 Label Studio XML 标签配置，便于排查。
LS_LABEL_CONFIG_XML ?= $(DATASET_ROOT)/label_studio/label_config.xml

# ── 2. OCR 识别参数 ──────────────────────────────────────────
# OCR 引擎：rapidocr（默认，CPU 快、易跑通）或 easyocr（备选，首次可能下载模型）。
# 示例：make step-2-ocr OCR_ENGINE=easyocr
OCR_ENGINE          ?= rapidocr
# 额外 OCR 关键词参数，会与 BRAND_LIBRARY 合并；格式必须是脚本参数形式。
# 示例：make step-2-ocr OCR_KEYWORD_ARGS="--keyword SOFTCARE --keyword KLEESOFT"
OCR_KEYWORD_ARGS    ?=
# EasyOCR 语言列表，仅 OCR_ENGINE=easyocr 时主要生效；多个语言可写成 "en ch_sim"。
OCR_LANGUAGES       ?= en
# OCR 文本最低置信度，范围 0-1；调高会减少误识别但可能漏掉模糊品牌字。
OCR_MIN_CONFIDENCE  ?= 0.2
# 品牌关键词模糊匹配阈值，范围 0-100；调高减少误召回，调低增加召回。
OCR_FUZZY_THRESHOLD ?= 60
# OCR 处理图片数量上限；空表示全量。调试建议 20。
# 示例：make step-2-ocr OCR_LIMIT=20
OCR_LIMIT           ?=
# 是否复制命中图片到 datasets/multibrand/ocr/candidates；1/true/yes 开启，默认只写候选清单不复制。
OCR_COPY_CANDIDATES ?= 0
# 派生参数：有 OCR_LIMIT 时才传 --limit。
OCR_LIMIT_ARG       := $(if $(OCR_LIMIT),--limit $(OCR_LIMIT),)
# 派生参数：OCR_COPY_CANDIDATES 为 1/true/yes 时才传 --copy-candidates。
OCR_COPY_ARG        := $(if $(filter 1 true yes,$(OCR_COPY_CANDIDATES)),--copy-candidates,)

# ── 3. YOLO-World 预标注参数 ─────────────────────────────────
# YOLO-World 权重路径；可换成更大/更小的 world 模型，但本地速度和显存会变化。
PSEUDO_MODEL      ?= $(PROJECT_ROOT)/models/yolov8s-world.pt
# 额外开放词汇提示词模板；多品牌模式建议使用 {brand} 占位符，否则无法安全映射到类别。
# 示例：PSEUDO_PROMPT_ARGS="--prompt '{brand} package on shelf'"；默认留空，避免泛化 package 无类别归属。
PSEUDO_PROMPT_ARGS ?=
# 预标注品牌过滤；多品牌多类别默认留空=使用品牌库全部启用品牌。
# 如果只想临时预标 Softcare：PSEUDO_BRAND_FILTER_ARGS="--brand-filter SOFTCARE"。
PSEUDO_BRAND_FILTER_ARGS ?=
# 是否为每个品牌额外生成 "<brand> diaper package" 和 "<brand> package" 提示词；1/true/yes 开启。
PSEUDO_INCLUDE_BRAND_PACKAGE_PROMPTS ?= 1
# 跨提示词重复框 NMS IoU 阈值；调低会删除更多重复框，调高会保留更多相近框。
PSEUDO_NMS_IOU     ?= 0.45
# 大框覆盖小框的过滤阈值；候选大框覆盖已保留小框超过该比例时丢弃大框。
# 调低（如 0.75）会更积极删除大框；调高会保留更多大框。
PSEUDO_CONTAINMENT ?= 0.85
# 单个框最大面积占整图比例；超过则丢弃，防止整图框/整排货架框。
# 如果仍有大框，试 0.30；如果漏掉近景大包装，可调到 0.60。
PSEUDO_MAX_AREA_RATIO ?= 0.45
# YOLO-World 候选框置信度；调低增加召回但误检多，调高减少误检但漏检多。
PSEUDO_CONF       ?= 0.03
# YOLO-World 推理图片尺寸；大图小目标建议 960，速度慢可降到 640。
PSEUDO_IMGSZ      ?= 960
# 预标注处理图片数量上限；空表示全量。调试建议 20。
PSEUDO_LIMIT      ?=
# 是否使用 OCR 候选清单；1 默认只处理 OCR 命中图片，0 表示全量 raw/images。
# 示例：make step-3-pseudo-label PSEUDO_USE_OCR_CANDIDATES=0
PSEUDO_USE_OCR_CANDIDATES ?= 1
# 派生参数：有 PSEUDO_LIMIT 时才传 --limit。
PSEUDO_LIMIT_ARG  := $(if $(PSEUDO_LIMIT),--limit $(PSEUDO_LIMIT),)
# 派生参数：PSEUDO_USE_OCR_CANDIDATES 为 1/true/yes 时才传 --candidates-file。
PSEUDO_CANDIDATES_ARG := $(if $(filter 1 true yes,$(PSEUDO_USE_OCR_CANDIDATES)),--candidates-file $(OCR_CANDIDATES_FILE),)
# 派生参数：PSEUDO_INCLUDE_BRAND_PACKAGE_PROMPTS 为 1/true/yes 时才传扩展品牌包装提示词开关。
PSEUDO_BRAND_PACKAGE_ARG := $(if $(filter 1 true yes,$(PSEUDO_INCLUDE_BRAND_PACKAGE_PROMPTS)),--include-brand-package-prompts,)

# ── 4/5. Label Studio 参数 ───────────────────────────────────
# PostgreSQL 用户；默认使用本机用户 guobiao。
POSTGRE_USER     ?= guobiao
# PostgreSQL 密码；本机 trust/peer 认证可为空。如果需要密码，可命令行传 POSTGRE_PASSWORD=xxx。
POSTGRE_PASSWORD ?=
# Label Studio 使用的 PostgreSQL 数据库名。
POSTGRE_NAME     ?= labelstudio
# PostgreSQL 主机。
POSTGRE_HOST     ?= localhost
# PostgreSQL 端口。
POSTGRE_PORT     ?= 5432
# Label Studio Web 端口；默认 http://localhost:9001。
LS_PORT          ?= 9001
# Label Studio 导入 JSON 输出路径；step-4 会生成并导入它。
LS_IMPORT_JSON   ?= $(DATASET_ROOT)/label_studio/multibrand_label_studio_import.json
# Label Studio Local Files storage 根目录；必须覆盖所有任务图片路径。
LS_LOCAL_FILES_PATH ?= $(RAW_DIR)
# Label Studio 后台日志文件。
LS_LOG_FILE      ?= $(LOG_DIR)/label-studio.log
# Label Studio 后台 PID 文件；ls-stop 会清理它。
LS_PID_FILE      ?= $(LOG_DIR)/label-studio.pid
# Label Studio 项目 ID；导出时必填。
# 示例：make step-5-export-ls-to-train LS_PROJECT_ID=2
LS_PROJECT_ID    ?=
# Label Studio 导出格式；当前转换脚本需要 JSON。其它格式如 CSV 不适合 ls-to-yolo。
LS_EXPORT_FORMAT ?= JSON
# Label Studio 导出目录。
LS_EXPORT_DIR    ?= $(DATASET_ROOT)/label_studio/exports
# Label Studio 导出 JSON 路径。
LS_EXPORT_PATH   ?= $(LS_EXPORT_DIR)/label_studio_export.json
# Label Studio 转 YOLO 的转换报告路径。
LS_TO_YOLO_REPORT ?= $(LS_EXPORT_DIR)/label_studio_to_yolo_report.json
# 转正式训练集前是否清空旧 images/labels；1/true/yes 开启。谨慎使用，会删除旧训练文件（保留 .gitkeep）。
LS_TO_YOLO_CLEAR ?= 0
# 是否跳过“已完成但无目标框”的空标注；0 表示保留为空标签负样本，1 表示跳过。
LS_TO_YOLO_SKIP_EMPTY ?= 0
# 派生参数：LS_TO_YOLO_CLEAR 为 1/true/yes 时传 --clear-output。
LS_TO_YOLO_CLEAR_ARG := $(if $(filter 1 true yes,$(LS_TO_YOLO_CLEAR)),--clear-output,)
# 派生参数：LS_TO_YOLO_SKIP_EMPTY 为 1/true/yes 时传 --skip-empty-annotations。
LS_TO_YOLO_SKIP_EMPTY_ARG := $(if $(filter 1 true yes,$(LS_TO_YOLO_SKIP_EMPTY)),--skip-empty-annotations,)

# ── 6. 训练参数 ──────────────────────────────────────────────
# 训练基座模型；默认 yolo26s，速度和精度相对平衡。可改 yolo26n 更快，yolo26m 更慢但可能更准。
TRAIN_BASE_MODEL ?= $(PROJECT_ROOT)/models/yolo26s.pt
# 训练 epoch 数；数据少时可先 30/50 快速验证，正式 baseline 可 100。
TRAIN_EPOCHS     ?= 100
# 训练图片尺寸；小目标建议 960，速度慢或内存压力大可 640。
TRAIN_IMGSZ      ?= 960
# batch 大小；-1 表示 Ultralytics 自动选择。显存/内存不稳时可改 4/8。
TRAIN_BATCH      ?= -1
# 训练设备；Apple Silicon 推荐 mps；也可 cpu、0（CUDA 环境）。空值表示不传 --device。
TRAIN_DEVICE     ?= mps
# 训练输出根目录。
TRAIN_PROJECT    ?= $(PROJECT_ROOT)/models/train
# 本次训练名称；输出目录为 $(TRAIN_PROJECT)/$(TRAIN_NAME)。多品牌默认使用 multibrand。
TRAIN_NAME       ?= multibrand
# 训练完成后复制 best.pt 到这里，供 predict 默认使用。多品牌默认模型为 multibrand-best.pt。
FINAL_MODEL      ?= $(PROJECT_ROOT)/models/multibrand-best.pt
# 派生参数：TRAIN_DEVICE 非空才传 --device。
TRAIN_DEVICE_ARG := $(if $(TRAIN_DEVICE),--device $(TRAIN_DEVICE),)

# ── 7. 推理验证参数 ──────────────────────────────────────────
# 推理验证输入图片；可改为任意本地图片路径或 HTTP(S) URL。
PREDICT_SOURCE   ?= $(PROJECT_ROOT)/data/samples/multibrand-shelf.webp
# 推理模型路径；默认使用训练导出的 FINAL_MODEL。
PREDICT_MODEL    ?= $(FINAL_MODEL)
# 推理置信度；调高减少误检，调低增加召回。
PREDICT_CONF     ?= 0.35
# 推理图片尺寸；通常与训练/预标注保持 960。
PREDICT_IMGSZ    ?= 960
# 推理输出目录；会写 JSON 和带框图片。
PREDICT_OUTPUT_DIR ?= $(PROJECT_ROOT)/outputs/predict

# 启用本地文件服务，让 Label Studio 通过 /data/local-files/ 访问本地图片。
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED := true
# 文档根目录设为 /，这样 /data/local-files/?d=<absolute_path> 可以访问本机图片。
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT := /
# 跳过浏览器自动打开（终端启动时不弹浏览器）。
export LABEL_STUDIO_BROWSER_OPEN := false
# 关闭 NLTK 安全检查，避免 nltk 3.10.1 误报导致启动失败。
export NLTK_DISABLE_IMPORT_SECURITY := 1

# PostgreSQL 连接环境变量（Label Studio Django settings 读取）。
export DJANGO_DB := postgresql
export POSTGRE_USER
export POSTGRE_PASSWORD
export POSTGRE_NAME
export POSTGRE_HOST
export POSTGRE_PORT
export LS_IMPORT_JSON
export LS_LOCAL_FILES_PATH
export BRAND_LIBRARY

.PHONY: help help-params prepare-dirs brand-yaml \
	step-1-import-excel step-2-ocr step-3-pseudo-label step-4-import-ls step-5-export-ls-to-train step-6-train step-7-validate \
	workflow-to-ls workflow-after-ls \
	excel-import ocr pseudo-label ls-setup ls-start ls-migrate ls-shell ls-stop ls-import-json ls-apply ls-export ls-to-yolo \
	data-validate train predict ls-db-create ls-db-check

help: ## 显示命令帮助和常用参数说明
	@printf "\033[1m可用命令\033[0m\n"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'
	@$(MAKE) --no-print-directory help-params

help-params: ## 显示 Make 参数默认值、可选值和调参效果
	@printf "\n\033[1m常用参数说明（命令行覆盖示例：make step-3-pseudo-label PSEUDO_LIMIT=20）\033[0m\n"
	@printf "\n[1. Excel 导入]\n"
	@printf "  EXCEL=%s\n    Excel 文件路径；改为其它 xlsx 可导入新业务数据。\n" "$(EXCEL)"
	@printf "  EXCEL_COLUMN=%s\n    图片 URL 列名；列名不匹配会导致导入失败。\n" "$(EXCEL_COLUMN)"
	@printf "  EXCEL_WORKERS=%s\n    并发下载线程数；调大更快但可能被限流，调小更稳。\n" "$(EXCEL_WORKERS)"
	@printf "  EXCEL_TIMEOUT=%s\n    单图下载超时秒数；网络慢可调大。\n" "$(EXCEL_TIMEOUT)"
	@printf "\n[2. 数据目录]\n"
	@printf "  RAW_DIR=%s\n    原始图片目录，OCR/预标注默认从这里读取。\n" "$(RAW_DIR)"
	@printf "  OCR_CANDIDATES_FILE=%s\n    OCR 候选清单，预标注默认只处理该清单。\n" "$(OCR_CANDIDATES_FILE)"
	@printf "  BRAND_LIBRARY=%s\n    品牌标识库；OCR、预标注、Label Studio 标签和 YOLO names 都以它为类别来源。\n" "$(BRAND_LIBRARY)"
	@printf "\n[3. OCR]\n"
	@printf "  OCR_ENGINE=%s\n    rapidocr/easyocr；rapidocr 快且默认推荐，easyocr 可作为备选。\n" "$(OCR_ENGINE)"
	@printf "  OCR_MIN_CONFIDENCE=%s\n    OCR 文本最低置信度 0-1；调高少误检但可能漏检。\n" "$(OCR_MIN_CONFIDENCE)"
	@printf "  OCR_FUZZY_THRESHOLD=%s\n    品牌模糊匹配阈值 0-100；调高更严格，调低召回更多。\n" "$(OCR_FUZZY_THRESHOLD)"
	@printf "  OCR_LIMIT=%s\n    OCR 处理数量上限；空=全量，调试建议 20。\n" "$(OCR_LIMIT)"
	@printf "  OCR_COPY_CANDIDATES=%s\n    1/true/yes 时复制命中图片到 ocr/candidates；默认只写清单。\n" "$(OCR_COPY_CANDIDATES)"
	@printf "\n[4. 预标注]\n"
	@printf "  PSEUDO_USE_OCR_CANDIDATES=%s\n    1=只处理 OCR 候选图；0=全量 raw/images。\n" "$(PSEUDO_USE_OCR_CANDIDATES)"
	@printf "  PSEUDO_BRAND_FILTER_ARGS=%s\n    多品牌默认留空=预标全部启用品牌；如只调试某品牌可传 --brand-filter SOFTCARE。\n" "$(PSEUDO_BRAND_FILTER_ARGS)"
	@printf "  PSEUDO_PROMPT_ARGS=%s\n    额外提示词模板；多类别建议用 {brand} 占位符，避免无法映射类别。\n" "$(PSEUDO_PROMPT_ARGS)"
	@printf "  PSEUDO_CONF=%s\n    YOLO-World 置信度；调高减少误检，调低增加召回。\n" "$(PSEUDO_CONF)"
	@printf "  PSEUDO_NMS_IOU=%s\n    重复框去重 IoU；调低删除更多重叠框。\n" "$(PSEUDO_NMS_IOU)"
	@printf "  PSEUDO_CONTAINMENT=%s\n    大框覆盖小框过滤阈值；调低更积极删除大框。\n" "$(PSEUDO_CONTAINMENT)"
	@printf "  PSEUDO_MAX_AREA_RATIO=%s\n    最大框面积占比；调低可删除整图/货架大框。\n" "$(PSEUDO_MAX_AREA_RATIO)"
	@printf "  PSEUDO_LIMIT=%s\n    预标注处理数量上限；空=全量，调试建议 20。\n" "$(PSEUDO_LIMIT)"
	@printf "\n[5. Label Studio]\n"
	@printf "  LS_PORT=%s\n    Label Studio 端口。\n" "$(LS_PORT)"
	@printf "  LS_PROJECT_ID=%s\n    LS 导出必填项目 ID；示例 make step-5-export-ls-to-train LS_PROJECT_ID=2。\n" "$(LS_PROJECT_ID)"
	@printf "  LS_EXPORT_PATH=%s\n    LS JSON 导出文件路径，ls-to-yolo 从这里读取。\n" "$(LS_EXPORT_PATH)"
	@printf "  LS_TO_YOLO_CLEAR=%s\n    1/true/yes 时转换前清空旧正式训练集，谨慎使用。\n" "$(LS_TO_YOLO_CLEAR)"
	@printf "  LS_TO_YOLO_SKIP_EMPTY=%s\n    1=跳过空标注；0=保留为空标签负样本。\n" "$(LS_TO_YOLO_SKIP_EMPTY)"
	@printf "\n[6. 训练]\n"
	@printf "  TRAIN_BASE_MODEL=%s\n    基座模型；yolo26n 更快，yolo26s 默认平衡，yolo26m 更慢可能更准。\n" "$(TRAIN_BASE_MODEL)"
	@printf "  TRAIN_NAME=%s\n    训练运行名称；输出目录为 models/train/<name>，多品牌默认 multibrand。\n" "$(TRAIN_NAME)"
	@printf "  FINAL_MODEL=%s\n    best.pt 复制目标；predict 默认使用该多品牌模型。\n" "$(FINAL_MODEL)"
	@printf "  TRAIN_EPOCHS=%s\n    训练轮数；快速验证可 30/50，baseline 默认 100。\n" "$(TRAIN_EPOCHS)"
	@printf "  TRAIN_IMGSZ=%s\n    训练尺寸；小目标建议 960，速度慢可 640。\n" "$(TRAIN_IMGSZ)"
	@printf "  TRAIN_BATCH=%s\n    batch；-1 自动，内存不稳可设 4/8。\n" "$(TRAIN_BATCH)"
	@printf "  TRAIN_DEVICE=%s\n    mps/cpu/0/空；M 系 Mac 默认 mps，空表示不传 device。\n" "$(TRAIN_DEVICE)"
	@printf "\n[7. 推理验证]\n"
	@printf "  PREDICT_SOURCE=%s\n    推理输入，可改本地图片或 HTTP(S) URL。\n" "$(PREDICT_SOURCE)"
	@printf "  PREDICT_CONF=%s\n    推理置信度；调高少误检，调低多召回。\n" "$(PREDICT_CONF)"
	@printf "\n常用示例：\n"
	@printf "  make step-2-ocr OCR_LIMIT=20\n"
	@printf "  make step-3-pseudo-label PSEUDO_USE_OCR_CANDIDATES=0 PSEUDO_LIMIT=20\n"
	@printf "  make step-3-pseudo-label PSEUDO_BRAND_FILTER_ARGS='--brand-filter SOFTCARE' PSEUDO_LIMIT=20\n"
	@printf "  make step-3-pseudo-label PSEUDO_MAX_AREA_RATIO=0.30 PSEUDO_NMS_IOU=0.35\n"
	@printf "  make workflow-after-ls LS_PROJECT_ID=2 TRAIN_EPOCHS=50\n"

prepare-dirs: ## 创建项目内临时目录和日志目录
	@mkdir -p $(TMP_DIR) $(LS_WORK_DIR) $(LOG_DIR) $(LS_EXPORT_DIR)

brand-yaml: ## 根据品牌库生成多品牌 YOLO 数据集 YAML
	$(VENV_BIN)/python scripts/config/write_brand_yolo_yaml.py \
		--brand-library $(BRAND_LIBRARY) \
		--data-yaml $(BRAND_DATA_YAML) \
		--pseudo-yaml $(BRAND_PSEUDO_YAML)

# ── 按业务顺序排列的主流程 ───────────────────────────────────

step-1-import-excel: excel-import ## 1. 从 Excel 导入/下载原始图片

step-2-ocr: ocr ## 2. OCR 识别品牌库关键词并生成候选图片清单

step-3-pseudo-label: brand-yaml pseudo-label ## 3. 使用 YOLO-World 和品牌库提示词生成多品牌预标注

step-4-import-ls: ls-import-json ls-apply ## 4. 生成任务 JSON 并导入 Label Studio

step-5-export-ls-to-train: ls-export ls-to-yolo ## 5. 导出 Label Studio 结果并转换为正式训练集

step-6-train: train ## 6. 训练多品牌 YOLO 模型

step-7-validate: data-validate predict ## 7. 校验正式数据集并用训练模型推理验证

workflow-to-ls: step-1-import-excel step-2-ocr step-3-pseudo-label step-4-import-ls ## 执行到 Label Studio 人工复核前/导入阶段

workflow-after-ls: step-5-export-ls-to-train step-6-train step-7-validate ## Label Studio 人工复核完成后导出、训练并验证

# ── 1. Excel 数据导入 ────────────────────────────────────────

excel-import: ## 从 Excel 指定列下载原始图片到 RAW_DIR
	$(VENV_BIN)/python scripts/data_import/import_images_from_excel.py \
		--excel '$(EXCEL)' \
		--column '$(EXCEL_COLUMN)' \
		--output-dir $(RAW_DIR) \
		--metadata-dir $(RAW_METADATA_DIR) \
		--workers $(EXCEL_WORKERS) \
		--timeout $(EXCEL_TIMEOUT)

# ── 2. OCR 识别 ─────────────────────────────────────────────

ocr: ## OCR 识别品牌标识库候选图片，输出 OCR_CANDIDATES_FILE
	$(VENV_BIN)/python scripts/ocr/filter_brand_candidates.py \
		--raw-dir $(RAW_DIR) \
		--output-dir $(OCR_OUTPUT_DIR) \
		--engine $(OCR_ENGINE) \
		--brand-library $(BRAND_LIBRARY) \
		$(OCR_KEYWORD_ARGS) \
		--languages $(OCR_LANGUAGES) \
		--min-confidence $(OCR_MIN_CONFIDENCE) \
		--fuzzy-threshold $(OCR_FUZZY_THRESHOLD) \
		$(OCR_LIMIT_ARG) \
		$(OCR_COPY_ARG)

# ── 3. YOLO-World 预标注 ────────────────────────────────────

pseudo-label: ## 生成 YOLO-World 预标注，默认使用 OCR 候选清单和品牌库提示词
	$(VENV_BIN)/python scripts/pseudo_label/generate_yolo_world.py \
		--raw-dir $(RAW_DIR) \
		--output-root $(PSEUDO_ROOT) \
		--model $(PSEUDO_MODEL) \
		--brand-library $(BRAND_LIBRARY) \
		$(PSEUDO_BRAND_FILTER_ARGS) \
		$(PSEUDO_BRAND_PACKAGE_ARG) \
		$(PSEUDO_PROMPT_ARGS) \
		--nms-iou $(PSEUDO_NMS_IOU) \
		--containment-threshold $(PSEUDO_CONTAINMENT) \
		--max-area-ratio $(PSEUDO_MAX_AREA_RATIO) \
		--conf $(PSEUDO_CONF) \
		--imgsz $(PSEUDO_IMGSZ) \
		$(PSEUDO_LIMIT_ARG) \
		$(PSEUDO_CANDIDATES_ARG)

# ── 4. Label Studio 启动 / 导入 ─────────────────────────────

ls-setup: ls-db-create ls-migrate ## 首次初始化 PostgreSQL 数据库并执行迁移

ls-start: ls-db-check prepare-dirs ## 后台启动 Label Studio（端口 9001，日志写入 logs/label-studio.log）
	@if [ -n "$$(lsof -ti :$(LS_PORT) 2>/dev/null)" ]; then \
		echo "Label Studio 已在端口 $(LS_PORT) 运行，PID: $$(lsof -ti :$(LS_PORT) 2>/dev/null | tr '\n' ' ')"; \
		echo "日志文件：$(LS_LOG_FILE)"; \
	else \
		echo "===== $$(date '+%Y-%m-%d %H:%M:%S') start Label Studio port $(LS_PORT) =====" >> $(LS_LOG_FILE); \
		( cd $(LS_WORK_DIR) && exec env PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio start \
			--data-dir $(LS_DATA_DIR) \
			--port $(LS_PORT) \
			--host 0.0.0.0 \
			--no-browser ) >> $(LS_LOG_FILE) 2>&1 & \
		pid=$$!; \
		echo $$pid > $(LS_PID_FILE); \
		sleep 2; \
		if kill -0 $$pid 2>/dev/null; then \
			echo "Label Studio 已后台启动，PID: $$pid"; \
			echo "访问地址：http://localhost:$(LS_PORT)"; \
			echo "日志文件：$(LS_LOG_FILE)"; \
			echo "PID 文件：$(LS_PID_FILE)"; \
		else \
			echo "Label Studio 启动失败，请查看日志：$(LS_LOG_FILE)"; \
			rm -f $(LS_PID_FILE); \
			exit 1; \
		fi; \
	fi

ls-migrate: ls-db-create prepare-dirs ## 执行 Django 数据库迁移（首次使用或升级后需要）
	cd $(LS_WORK_DIR) && printf 'from django.core.management import call_command\ncall_command("migrate", "--no-color")\nexit()\n' | \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

ls-shell: ls-db-check prepare-dirs ## 进入 Label Studio Django shell（用于排查或手动执行脚本）
	cd $(LS_WORK_DIR) && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

ls-stop: ## 停止 Label Studio（查找并终止占用 9001 端口的进程）
	@pids="$$(lsof -ti :$(LS_PORT) 2>/dev/null | sort -u | tr '\n' ' ')"; \
	if [ -n "$$pids" ]; then \
		kill $$pids && rm -f $(LS_PID_FILE) && echo "已停止 PID $$pids"; \
	else \
		rm -f $(LS_PID_FILE); \
		echo "端口 $(LS_PORT) 没有运行中的进程"; \
	fi

ls-import-json: ## 生成 Label Studio 导入 JSON（使用本地图片路径和预标注 predictions）
	$(VENV_BIN)/python scripts/label_studio/generate_import.py \
		--raw-report $(RAW_METADATA_DIR)/download_report.csv \
		--pseudo-root $(PSEUDO_ROOT) \
		--output $(LS_IMPORT_JSON) \
		--brand-library $(BRAND_LIBRARY) \
		--label-config-output $(LS_LABEL_CONFIG_XML)

ls-apply: ls-db-check prepare-dirs ## 通过 Django shell 导入任务到 Label Studio，并注册本地图片目录
	cd $(LS_WORK_DIR) && printf 'exec(open("$(PROJECT_ROOT)/scripts/label_studio/apply_import.py", encoding="utf-8").read())\nexit()\n' | \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

# ── 5. Label Studio 导出并转换为正式训练集 ───────────────────

ls-export: ls-db-check prepare-dirs ## 从 Label Studio 导出 JSON；需传 LS_PROJECT_ID=<项目ID>
	@[ -n "$(LS_PROJECT_ID)" ] || (echo "错误：请传入 LS_PROJECT_ID，例如：make ls-export LS_PROJECT_ID=2" && exit 1)
	cd $(LS_WORK_DIR) && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio export \
		--data-dir $(LS_DATA_DIR) \
		--export-path $(LS_EXPORT_PATH) \
		$(LS_PROJECT_ID) $(LS_EXPORT_FORMAT)

ls-to-yolo: ## 将 Label Studio JSON 导出转换为 datasets/multibrand/images 和 labels
	$(VENV_BIN)/python scripts/label_studio/export_to_yolo.py \
		--input $(LS_EXPORT_PATH) \
		--output-root $(DATASET_ROOT) \
		--pseudo-root $(PSEUDO_ROOT) \
		--brand-library $(BRAND_LIBRARY) \
		--report $(LS_TO_YOLO_REPORT) \
		$(LS_TO_YOLO_CLEAR_ARG) \
		$(LS_TO_YOLO_SKIP_EMPTY_ARG)

# ── 6. 训练 ─────────────────────────────────────────────────

train: data-validate ## 训练多品牌 YOLO 模型
	$(VENV_BIN)/python scripts/training/train.py \
		--data $(TRAIN_DATA_YAML) \
		--base-model $(TRAIN_BASE_MODEL) \
		--epochs $(TRAIN_EPOCHS) \
		--imgsz $(TRAIN_IMGSZ) \
		--batch $(TRAIN_BATCH) \
		$(TRAIN_DEVICE_ARG) \
		--project $(TRAIN_PROJECT) \
		--name $(TRAIN_NAME) \
		--export-model $(FINAL_MODEL)

# ── 7. 验证 / 推理 ──────────────────────────────────────────

data-validate: ## 校验正式 YOLO 数据集结构、标签和类别
	$(VENV_BIN)/python scripts/training/validate_dataset.py --data $(TRAIN_DATA_YAML)

predict: ## 使用训练后的模型对 PREDICT_SOURCE 做推理验证
	$(VENV_BIN)/python scripts/inference/predict.py '$(PREDICT_SOURCE)' \
		--model $(PREDICT_MODEL) \
		--conf $(PREDICT_CONF) \
		--imgsz $(PREDICT_IMGSZ) \
		--output-dir $(PREDICT_OUTPUT_DIR)

# ── 检查 ────────────────────────────────────────────────────

ls-db-create: ## 如果 PostgreSQL 数据库不存在则创建
	@if PGPASSWORD="$(POSTGRE_PASSWORD)" psql -U $(POSTGRE_USER) -h $(POSTGRE_HOST) -p $(POSTGRE_PORT) -d $(POSTGRE_NAME) -c 'SELECT 1' >/dev/null 2>&1; then \
		echo "PostgreSQL 数据库 $(POSTGRE_NAME) 已存在"; \
	else \
		echo "创建 PostgreSQL 数据库 $(POSTGRE_NAME)"; \
		PGPASSWORD="$(POSTGRE_PASSWORD)" createdb -U $(POSTGRE_USER) -h $(POSTGRE_HOST) -p $(POSTGRE_PORT) $(POSTGRE_NAME); \
	fi

ls-db-check: ## 检查 PostgreSQL 数据库是否可用
	@PGPASSWORD="$(POSTGRE_PASSWORD)" psql -U $(POSTGRE_USER) -h $(POSTGRE_HOST) -p $(POSTGRE_PORT) -d $(POSTGRE_NAME) -c 'SELECT 1' >/dev/null 2>&1 \
		|| (echo "错误：数据库 $(POSTGRE_NAME) 不可用，请先执行: make ls-db-create" && exit 1)
	@echo "PostgreSQL 数据库 $(POSTGRE_NAME) 连接正常"
