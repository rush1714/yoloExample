PROJECT_ROOT := $(shell pwd)
VENV_BIN     := $(PROJECT_ROOT)/.venv/bin
LS_DATA_DIR  := $(PROJECT_ROOT)/.label-studio-data
LOG_DIR      := $(PROJECT_ROOT)/logs

# ── PostgreSQL ──────────────────────────────────────────────
POSTGRE_USER     ?= guobiao
POSTGRE_PASSWORD ?=
POSTGRE_NAME     ?= labelstudio
POSTGRE_HOST     ?= localhost
POSTGRE_PORT     ?= 5432

# ── Label Studio ────────────────────────────────────────────
LS_PORT             ?= 9001
LS_IMPORT_JSON      ?= $(PROJECT_ROOT)/datasets/softcare/label_studio/softcare_label_studio_import.json
LS_LOCAL_FILES_PATH ?= $(PROJECT_ROOT)/datasets/softcare/raw/images
LS_LOG_FILE         ?= $(LOG_DIR)/label-studio.log
LS_PID_FILE         ?= $(LOG_DIR)/label-studio.pid

# 启用本地文件服务，让 Label Studio 通过 /data/local-files/ 访问本地图片
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED := true
# 文档根目录设为 /，这样 /data/local-files/?d=<absolute_path> 可以访问本机图片
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT := /
# 跳过浏览器自动打开（终端启动时不弹浏览器）
export LABEL_STUDIO_BROWSER_OPEN := false
# 关闭 NLTK 安全检查，避免 nltk 3.10.1 误报导致启动失败
export NLTK_DISABLE_IMPORT_SECURITY := 1

# ── PostgreSQL 连接环境变量（Label Studio Django settings 读取） ──
export DJANGO_DB := postgresql
export POSTGRE_USER
export POSTGRE_PASSWORD
export POSTGRE_NAME
export POSTGRE_HOST
export POSTGRE_PORT
export LS_IMPORT_JSON
export LS_LOCAL_FILES_PATH

.PHONY: help ls-setup ls-start ls-migrate ls-shell ls-import-json ls-apply ls-stop ls-db-create ls-db-check

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── 启动 / 停止 ────────────────────────────────────────────

ls-setup: ls-db-create ls-migrate ## 首次初始化 PostgreSQL 数据库并执行迁移

ls-start: ls-db-check ## 后台启动 Label Studio（端口 9001，日志写入 logs/label-studio.log）
	@mkdir -p $(LOG_DIR)
	@if [ -n "$$(lsof -ti :$(LS_PORT) 2>/dev/null)" ]; then \
		echo "Label Studio 已在端口 $(LS_PORT) 运行，PID: $$(lsof -ti :$(LS_PORT) 2>/dev/null | tr '\n' ' ')"; \
		echo "日志文件：$(LS_LOG_FILE)"; \
	else \
		echo "===== $$(date '+%Y-%m-%d %H:%M:%S') start Label Studio port $(LS_PORT) =====" >> $(LS_LOG_FILE); \
		( cd /tmp && exec env PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio start \
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

ls-migrate: ls-db-create ## 执行 Django 数据库迁移（首次使用或升级后需要）
	cd /tmp && printf 'from django.core.management import call_command\ncall_command("migrate", "--no-color")\nexit()\n' | \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

ls-shell: ls-db-check ## 进入 Label Studio Django shell（用于执行 apply 脚本）
	cd /tmp && PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

ls-stop: ## 停止 Label Studio（查找并终止占用 9001 端口的进程）
	@pids="$$(lsof -ti :$(LS_PORT) 2>/dev/null | sort -u | tr '\n' ' ')"; \
	if [ -n "$$pids" ]; then \
		kill $$pids && rm -f $(LS_PID_FILE) && echo "已停止 PID $$pids"; \
	else \
		rm -f $(LS_PID_FILE); \
		echo "端口 $(LS_PORT) 没有运行中的进程"; \
	fi

# ── 数据导入 ────────────────────────────────────────────────

ls-import-json: ## 生成 Label Studio 导入 JSON（使用本地图片路径）
	$(VENV_BIN)/python scripts/import_label_studio.py

ls-apply: ls-db-check ## 通过 Django shell 导入任务到 Label Studio，并注册本地图片目录
	cd /tmp && printf 'exec(open("$(PROJECT_ROOT)/scripts/apply_label_studio_import.py", encoding="utf-8").read())\nexit()\n' | \
		PYTHONSAFEPATH=1 $(VENV_BIN)/label-studio shell --data-dir $(LS_DATA_DIR)

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
