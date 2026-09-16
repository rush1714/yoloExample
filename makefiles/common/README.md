# 公共 Make 目标与变量

本目录只定义所有流程共用的变量和基础命令，由根目录 `Makefile` 自动 `include`。业务流程专属变量放在对应目录的 `Makefile.mk`，例如本地目录流程在 `makefiles/local-dir/`，EC2 公共参数在 `makefiles/ec2/`。

## 常用公共命令

```bash
# 查看所有 include 进来的目标
make help

# 查看公共参数摘要；流程专属参数请看各目录 README
make help-params

# 查看品牌库中可用于 BRAND 的品牌名
make brand-list

# 启动 / 停止 Label Studio
make ls-start
make ls-stop

# 通用本地训练与推理；训练数据 YAML 由具体流程生成
make train BRAND=SOFTCARE TRAIN_EPOCHS=50 TRAIN_DEVICE=mps
make predict BRAND=SOFTCARE PREDICT_SOURCE=data/samples/multibrand-shelf.webp

# 预览清理 datasets 下未跟踪内容，但保留 raw 目录
make datasets-clean-untracked-except-raw-preview
```

## 公共变量说明

| 变量 | 默认值 | 说明 | 示例 |
|---|---|---|---|
| `PROJECT_ROOT` | 当前执行目录 | 项目根目录，通常不需要覆盖。 | - |
| `VENV_BIN` | `$(PROJECT_ROOT)/.venv/bin` | Python 虚拟环境 bin 目录。 | - |
| `EXCEL` | 本机默认业务 Excel | 通用 Excel 图片 URL 来源。 | `EXCEL=/path/images.xlsx` |
| `EXCEL_COLUMN` | `生动化照片链接` | 通用图片 URL 列名。 | `EXCEL_COLUMN=整改后图片URL` |
| `EXCEL_WORKERS` | `10` | 下载并发数。 | `EXCEL_WORKERS=4` |
| `EXCEL_TIMEOUT` | `30` | 单图下载超时秒数。 | `EXCEL_TIMEOUT=60` |
| `BRAND` | `all` | 品牌流程选择；`all` 为全部启用品牌。 | `BRAND=SOFTCARE` |
| `BRAND_LIBRARY` | `config/brand_keywords.json` | 品牌库路径。 | `BRAND_LIBRARY=config/brand_keywords.json` |
| `DATASET_ROOT` | `datasets/<brand>` | 当前品牌流程输出根目录。 | 自动派生 |
| `LS_PROJECT_ID` | 空 | Label Studio 导出时必填。 | `LS_PROJECT_ID=2` |
| `TRAIN_BASE_MODEL` | `models/yolo26m.pt` | 本地训练基座模型。 | `TRAIN_BASE_MODEL=models/yolo26s.pt` |
| `TRAIN_EPOCHS` | `55` | 本地训练轮数。 | `TRAIN_EPOCHS=100` |
| `TRAIN_DEVICE` | `mps` | 本地训练设备。 | `TRAIN_DEVICE=cpu` |
| `TRAIN_RESUME` | `0` | 是否从 `last.pt` 恢复训练。 | `TRAIN_RESUME=1` |
| `PREDICT_SOURCE` | 样例图片 | 推理输入图片或 URL。 | `PREDICT_SOURCE=/tmp/test.jpg` |

## 模块边界

- `common`：公共变量、Label Studio 基础目标、通用本地训练/推理、数据清理和模型备份。
- `ec2`：EC2 连接、训练参数和 dry-run 开关。
- `local-dir`：本地图片目录导入、标注导出和本地目录数据集上 EC2 训练。
- `brand-ocr-yoloworld` / `brand-llm-ocr-yoloworld` / `brand-yoloe-visual`：品牌识别不同前置处理与预标注路径。
- `brand-s3-ec2`：本地图片上传 S3、S3 图片标注、EC2 从 S3 下载训练。
- `diaper-category-ec2`：纸尿裤大类 Excel 导入、标注和 EC2 训练。

## 本地 Mac 训练示例

```bash
python3 scripts/training/train.py \
  --data config/generated/diaper_category_GH_v2026-09-15.yaml \
  --base-model yolo26m.pt \
  --epochs 10 \
  --imgsz 960 \
  --batch -1 \
  --device mps \
  --project models/train \
  --name diaper_category_GH_v2026-09-15 \
  --export-model models/ec2/diaper_category/GH/v2026-09-15/yolo26m_img960_e10/best.pt \
  --run-dir-output artifacts/diaper_category/GH/v2026-09-15/yolo26m_img960_e10/latest-run.txt
```

## 命令示例索引

| 命令 | 作用 | 示例 |
|---|---|---|
| `help` | 显示命令帮助和常用参数说明 | `make help` |
| `help-params` | 显示公共 Make 参数默认值；流程专属参数详见 makefiles/*/README.md | `make help-params` |
| `web-console` | 启动本地 Make 命令与数据可视化页面 | `make web-console` |
| `prepare-dirs` | 创建项目内临时目录和日志目录 | `make prepare-dirs` |
| `datasets-clean-preview` | 预览 datasets/ 下会被 git clean 删除的 ignored 文件 | `make datasets-clean-preview` |
| `datasets-clean-ignored` | 删除 datasets/ 下所有被 .gitignore 忽略的文件；先执行 datasets-clean-preview 确认 | `make datasets-clean-ignored` |
| `datasets-clean-untracked-except-raw-preview` | 预览删除 datasets/ 下除 raw 目录外的所有未跟踪内容 | `make datasets-clean-untracked-except-raw-preview` |
| `datasets-clean-untracked-except-raw` | 删除 datasets/ 下除 raw 目录外的所有未跟踪内容；先执行预览命令确认 | `make datasets-clean-untracked-except-raw` |
| `bak-data` | 备份 models/ 下的 .pt 权重，并按日期时间和原文件名重命名 | `make bak-data` |
| `brand-check` | 验证 BRAND 是否存在于当前品牌库 | `make brand-check BRAND=SOFTCARE` |
| `brand-list` | 显示当前品牌库支持的 BRAND 参数 | `make brand-list` |
| `ls-setup` | 首次初始化 PostgreSQL 数据库并执行迁移 | `make ls-setup` |
| `ls-start` | 后台启动 Label Studio | `make ls-start LS_PORT=9001` |
| `ls-migrate` | 执行 Django 数据库迁移 | `make ls-migrate` |
| `ls-shell` | 进入 Label Studio Django shell | `make ls-shell` |
| `ls-stop` | 停止 Label Studio | `make ls-stop LS_PORT=9001` |
| `ls-apply` | 通过 Django shell 导入任务到 Label Studio | `make ls-apply BRAND=SOFTCARE` |
| `ls-export` | 从 Label Studio 导出 JSON；需传 LS_PROJECT_ID=<项目ID> | `make ls-export BRAND=SOFTCARE LS_PROJECT_ID=<项目ID>` |
| `train` | 训练 YOLO 模型 | `make train BRAND=SOFTCARE TRAIN_BASE_MODEL=models/yolo26m.pt TRAIN_EPOCHS=50 TRAIN_IMGSZ=960 TRAIN_DEVICE=mps` |
| `data-validate` | 校验正式 YOLO 数据集结构、标签和类别 | `make data-validate BRAND=SOFTCARE` |
| `predict` | 使用训练后的模型对 PREDICT_SOURCE 做推理验证 | `make predict PREDICT_SOURCE=data/samples/multibrand-shelf.webp PREDICT_MODEL=models/multibrand-best.pt` |
| `ls-db-create` | 如果 PostgreSQL 数据库不存在则创建 | `make ls-db-create` |
| `ls-db-check` | 检查 PostgreSQL 数据库是否可用 | `make ls-db-check` |
