# 公共 Make 目标与变量

本目录定义所有流程共用的变量和基础命令，由根目录 `Makefile` 自动 `include`。业务流程专属变量已经放回对应目录的 `Makefile.mk`。

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

# 通用训练与推理；训练数据 YAML 由具体流程生成
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
| `EXCEL_COLUMN` | `整改后图片URL` | 通用图片 URL 列名。 | `EXCEL_COLUMN=整改后图片URL` |
| `EXCEL_WORKERS` | `10` | 下载并发数。 | `EXCEL_WORKERS=4` |
| `EXCEL_TIMEOUT` | `30` | 单图下载超时秒数。 | `EXCEL_TIMEOUT=60` |
| `BRAND` | `all` | 品牌流程选择；`all` 为全部启用品牌。 | `BRAND=SOFTCARE` |
| `BRAND_LIBRARY` | `config/brand_keywords.json` | 品牌库路径。 | `BRAND_LIBRARY=config/brand_keywords.json` |
| `DATASET_ROOT` | `datasets/<brand>` | 当前品牌流程输出根目录。 | 自动派生 |
| `LS_PROJECT_ID` | 空 | Label Studio 导出时必填。 | `LS_PROJECT_ID=2` |
| `TRAIN_BASE_MODEL` | `models/yolo26m.pt` | 训练基座模型。 | `TRAIN_BASE_MODEL=models/yolo26s.pt` |
| `TRAIN_EPOCHS` | `55` | 训练轮数。 | `TRAIN_EPOCHS=100` |
| `TRAIN_DEVICE` | `mps` | 本地训练设备。 | `TRAIN_DEVICE=cpu` |
| `TRAIN_RESUME` | `0` | 是否从 `last.pt` 恢复训练。 | `TRAIN_RESUME=1` |
| `PREDICT_SOURCE` | 样例图片 | 推理输入图片或 URL。 | `PREDICT_SOURCE=/tmp/test.jpg` |

## 注意

- 公共 `train` 依赖具体流程提供的 `brand-yaml` 或等价 YAML 目标。
- 若你只做纸尿裤大类流程，请优先看 `makefiles/diaper-category-ec2/README.md`。
- 若你做品牌识别，请根据 OCR/LLM/YOLOE 路径选择对应 README。
