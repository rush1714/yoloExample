# brand-s3-ec2：S3 训练图片上传、Label Studio 标注衔接与 EC2 下载训练图管理计划

## 背景与目标

本次需求是在现有本地目录导入、Label Studio 标注、EC2 训练链路基础上，新增 `brand-s3-ec2` 流程，支持：

1. 将本地图片目录批量上传到 S3，S3 桶、前缀、区域、访问方式等参数可配置。
2. 上传后生成批量下载地址/对象清单文件。
3. Label Studio 标注阶段不强制把图片下载成本地训练集；导入任务可使用 S3 图片地址，同时通过本地代理绕过无法修改 AWS S3 CORS 配置的问题。
4. 人工标注导出后，把图片地址清单与 YOLO 标签批量传入 EC2。
5. EC2 训练前根据清单从 S3 下载训练图片，再执行现有 YOLO 训练、评估、模型/归档下载流程。
6. 在 `makefiles/brand-s3-ec2/` 内实现完整命令入口，并在 Web 控制台中增加独立菜单。
7. 补充文档、详细注释、单元测试与静态检查。

## 已阅读上下文

- `设计.md`：当前架构包含 Excel/本地目录导入、Label Studio、YOLO 训练、EC2 训练、本地 Web 控制台等模块；新增 S3 流程需要同步更新架构文档。
- `Makefile`：根 Makefile 当前 include common、品牌 OCR/YOLOE、纸尿裤 EC2 等模块，尚未 include `makefiles/brand-s3-ec2/Makefile.mk`。
- `makefiles/brand-s3-ec2/`：目录已存在但为空，适合作为本次新增流程落点。
- `makefiles/common/Makefile.mk`：已有本地目录导入、Label Studio 导入/导出、EC2 训练/归档/下载命令，可复用命名风格和 dry-run 机制。
- `scripts/cloud/ec2_diaper_workflow.py`：已有 EC2 SSH/rsync/dry-run 命令构造模式，可作为 S3-EC2 工作流脚本参考。
- `scripts/label_studio/generate_local_dir_import.py`、`scripts/label_studio/export_single_class_to_yolo.py`：已有单类别 LS 导入和导出转 YOLO 逻辑，可复用标签配置、稳定拆分、报告输出风格。
- `web-console/server.js` / `web-console/public/index.html`：当前 Web 控制台由 Node 单文件后端 + 内嵌前端组成，菜单来自 `COMMAND_GROUPS` 白名单，新增菜单需要补充命令分组和参数定义。
- 当前 Git 状态已有用户未提交变更：`docs/reports/2026-08-12-diaper-category-ec2-workflow.md` 为 staged add + worktree deleted，`docs/plans/2026-09-16_1_plan_Web加入02上传EC2命令.md` 为未跟踪文件。本次实现不会主动覆盖这些文件。

## 关键设计决策

### 1. S3 参数配置

新增一个示例配置文件与本地私有配置约定：

- 提交示例：`config/brand_s3_ec2.example.yaml`
- 本地实际配置：`config/brand_s3_ec2.local.yaml`（加入 `.gitignore`，避免误提交账号、桶名或内部路径）
- Make 入口统一通过 `BRAND_S3_CONFIG` 指向配置文件，同时允许常用参数用 Make 变量覆盖。

建议配置字段：

```yaml
dataset_name: local_dataset
label_name: diaper
local_images_dir: /path/to/images
s3:
  bucket: your-bucket
  prefix: yolo-training/local_dataset
  region: ap-southeast-1
  profile: default
  endpoint_url: null
  public_base_url: null
label_studio:
  image_url_mode: proxy
  proxy_base_url: http://127.0.0.1:3010
  project_title: S3 Images local_dataset
ec2:
  host: 1.2.3.4
  user: ec2-user
  key: ~/.ssh/key.pem
  project_root: /home/ec2-user/yoloExample
```

原则：不把 AWS access key/secret 写进仓库；默认使用本机/EC2 上的 AWS profile、环境变量或实例角色。

### 2. S3 上传与地址清单

新增脚本 `scripts/s3/upload_images_to_s3.py`：

- 扫描 `local_images_dir` 下图片，支持递归和 limit。
- 用稳定相对路径生成 S3 key：`<prefix>/<relative_path>`。
- 上传图片到 `s3://bucket/key`。
- 输出清单到 `datasets/s3/<dataset_name>/metadata/`，至少包含：
  - `s3_images.csv`
  - `s3_images.json`
  - `s3_download_urls.txt`
- 清单字段包括：`dataset_name`、`image_name`、`relative_path`、`s3_bucket`、`s3_key`、`s3_uri`、`https_url`、`proxy_url`、`size_bytes`、`etag/last_modified`（能获取则写入）。
- 支持 dry-run，便于无 AWS 权限时先验证命令和清单结构。

实现优先使用 Python `boto3`。若本地尚未安装，错误信息会提示执行 `uv sync` 或配置环境；测试会通过 mock/纯逻辑避免真实访问 S3。

### 3. Label Studio CORS 规避方案

不要求配置 AWS S3 CORS。默认采用本地只读图片代理：

- 新增 `scripts/s3/s3_image_proxy.py`，读取 `BRAND_S3_CONFIG` / 清单，通过 boto3 从 S3 流式读取对象并返回图片响应。
- 响应头加入 `Access-Control-Allow-Origin`，默认允许本地 Label Studio 地址（如 `http://localhost:9001`）访问。
- Label Studio 导入任务中的 `data.image` 默认写成代理地址，例如：
  - `http://127.0.0.1:3010/image?dataset=<dataset_name>&key=<urlencoded-s3-key>`
- 任务数据同时保留 `s3_uri`、`s3_key`、`source_url`、`image_name`、`relative_path`，保证后续导出可在不下载本地图片的情况下生成 EC2 下载清单。
- 风险提示：标注时本地 S3 proxy 必须保持运行；如果 S3 对象本身是 public 并且后续允许 CORS，可通过配置切换为直连 URL 模式。

### 4. Label Studio 导入与导出转换

新增脚本：

- `scripts/label_studio/generate_s3_import.py`
  - 输入 S3 清单。
  - 输出 LS 导入 JSON 和单类别 label config。
  - 默认无 predictions，只做人工作框标注。
- `scripts/label_studio/export_s3_single_class_to_yolo.py`
  - 输入 LS 导出 JSON。
  - 不复制/下载图片到本地。
  - 按稳定顺序生成：
    - `labels/{train,val,test}/*.txt`
    - `metadata/ec2_image_manifest.csv/json`
    - `metadata/label_studio_to_yolo_report.json/csv`
  - manifest 记录每张图所属 split 与 S3 地址，供 EC2 下载。

### 5. EC2 侧下载与训练

新增 `scripts/cloud/ec2_s3_workflow.py`，复用现有 EC2 dry-run 风格：

- `upload-manifest`：把 labels、manifest、YAML 或配置上传到 EC2，但不上传大图片。
- `download-images`：在 EC2 上根据 manifest 从 S3 下载图片到 `datasets/s3/<dataset_name>/images/{train,val,test}`。
- `train`：下载确认后生成远端绝对路径 YAML，调用现有 `scripts/training/train.py`。
- `evaluate` / `download-artifacts` / `download-model`：复用纸尿裤 EC2 工作流的归档与下载思路。

EC2 下载优先使用 EC2 机器自己的 AWS 权限（profile、环境变量或 IAM Role）；本地不会把密钥同步到 EC2。

### 6. Makefile 模块

新增 `makefiles/brand-s3-ec2/Makefile.mk` 并在根 `Makefile` include。

拟新增命令：

- `brand-s3-check-config`：校验配置和关键参数。
- `brand-s3-upload-images`：上传本地图片目录到 S3 并生成地址清单。
- `brand-s3-ls-import-json`：由 S3 清单生成 LS 导入 JSON/XML。
- `brand-s3-proxy-start`：启动本地 S3 图片代理，解决 LS 图片展示 CORS 问题。
- `brand-s3-ls-apply`：把 S3/proxy 图片任务导入 Label Studio。
- `1-brand-s3-workflow-to-ls`：上传 S3 → 生成 LS JSON/XML → 导入 LS（proxy 需另开进程保持运行）。
- `brand-s3-ls-export`：导出 LS JSON。
- `brand-s3-ls-to-yolo`：LS 导出转 labels + EC2 下载 manifest。
- `2-brand-s3-workflow-after-ls`：导出 LS → 生成 labels + manifest。
- `brand-s3-ec2-upload-manifest`：上传 labels/manifest/YAML 到 EC2。
- `brand-s3-ec2-download-images`：EC2 从 S3 拉取训练图片。
- `brand-s3-ec2-train-smoke` / `brand-s3-ec2-train-baseline` / `brand-s3-ec2-train-improve`。
- `brand-s3-ec2-evaluate`、`brand-s3-ec2-download-artifacts`、`brand-s3-ec2-download-model`。

所有 EC2 命令默认 dry-run，必须 `EC2_EXECUTE=1` 才连接远端执行。

### 7. Web 控制台菜单

在 `web-console/server.js` 中增加单独菜单分组：`S3 图片 / EC2 训练`。

菜单包含：

1. 上传本地图片到 S3。
2. 启动 S3 图片代理。
3. 生成 S3 Label Studio 导入 JSON。
4. 导入 S3 图片任务到 Label Studio。
5. 标注后导出并生成 EC2 manifest。
6. 上传 manifest 到 EC2。
7. EC2 下载 S3 图片。
8. EC2 smoke / baseline / improve 训练。
9. EC2 评估归档、下载归档、下载模型。

同时补充参数定义，例如：`BRAND_S3_CONFIG`、`S3_BUCKET`、`S3_PREFIX`、`S3_REGION`、`S3_PROFILE`、`S3_DATASET_NAME`、`S3_LABEL_NAME`、`S3_PROXY_PORT`、`S3_MANIFEST_PATH` 等。

### 8. 文档更新

- 新增 `makefiles/brand-s3-ec2/README.md`：完整命令、参数、配置模板、从本地目录到 S3/LS/EC2 的顺序说明、CORS 规避说明。
- 更新 `设计.md`：补充 “S3 训练图片管理与 EC2 下载训练” 小节和数据目录约定。
- 必要时更新 `README.md` / `make help` 参数说明。
- 本计划文件后续会追加实现结果、测试结果和注意事项。

### 9. 测试验证

计划新增/更新测试：

- `tests/test_brand_s3_ec2_workflow.py`
  - S3 key 生成与路径归一化。
  - 上传 manifest 输出字段。
  - LS import JSON 使用 proxy URL 且保留 `s3_uri`/`s3_key`。
  - LS export 转 labels + EC2 manifest，不依赖本地图片文件。
  - EC2 dry-run 命令包含 manifest 上传、远端下载和训练命令。
- Web 控制台：`node --check web-console/server.js`。
- Python 单元测试：`uv run python -m unittest tests.test_brand_s3_ec2_workflow tests.test_local_dir_import tests.test_diaper_category_workflow`。
- 静态检查：`uv run pylint scripts/s3 scripts/cloud/ec2_s3_workflow.py scripts/label_studio/generate_s3_import.py scripts/label_studio/export_s3_single_class_to_yolo.py`。

如当前机器没有 AWS 凭证或 EC2 权限，只做 dry-run 和 mock 单元测试；真实上传/下载/训练在你提供 S3 与 EC2 参数后再验证。

## 待确认事项

默认按以下假设执行，若不同请在确认前说明：

1. `@brand-s3-ec2` 指的是在现有空目录 `makefiles/brand-s3-ec2/` 下新增该流程，并接入根 `Makefile`。
2. S3 对象默认按私有桶处理；不要求也不修改 S3 CORS；Label Studio 默认通过本地代理访问图片。
3. AWS 凭证不写入配置文件，不提交仓库；本地/EC2 分别使用 AWS profile、环境变量或 IAM Role。
4. 该流程先按单类别标注实现，默认标签沿用 `diaper`，后续可扩展多类别。
5. EC2 仍沿用当前 dry-run 安全机制，所有远端真实操作必须显式 `EC2_EXECUTE=1`。

## 预计改动文件

- `Makefile`
- `.gitignore`
- `config/brand_s3_ec2.example.yaml`
- `makefiles/brand-s3-ec2/Makefile.mk`
- `makefiles/brand-s3-ec2/README.md`
- `scripts/s3/upload_images_to_s3.py`
- `scripts/s3/s3_image_proxy.py`
- `scripts/label_studio/generate_s3_import.py`
- `scripts/label_studio/export_s3_single_class_to_yolo.py`
- `scripts/cloud/ec2_s3_workflow.py`
- `web-console/server.js`
- `设计.md`
- `tests/test_brand_s3_ec2_workflow.py`
- 可能更新：`pyproject.toml` / `uv.lock`（若确认采用 boto3 作为 S3 SDK）

## 执行顺序

1. 建立 S3 配置加载与 manifest 数据结构，先写纯逻辑测试。
2. 实现本地图片上传 S3 与下载地址清单生成。
3. 实现 S3 proxy 与 LS 导入 JSON 生成。
4. 实现 LS 导出转 labels + EC2 下载 manifest。
5. 实现 EC2 S3 manifest 上传、远端下载、训练、评估和产物下载 dry-run 命令。
6. 接入 Makefile 模块和 Web 控制台菜单。
7. 更新 `设计.md` 与 `makefiles/brand-s3-ec2/README.md`。
8. 运行单元测试、pylint、Node 语法检查，并把结果追加到本计划文件。


## 实施结果（2026-09-16）

已完成：

- 新增 `scripts/s3/brand_s3_config.py`，统一管理 S3 工作流配置、S3 key 生成、HTTPS/proxy URL、图片扫描与 manifest 读取。
- 新增 `scripts/s3/upload_images_to_s3.py`，支持本地图片目录批量上传 S3，并输出 JSON/CSV/URL txt 清单；支持 `S3_DRY_RUN=1`。
- 新增 `scripts/s3/s3_image_proxy.py`，通过本地只读代理从 S3 读取图片并返回 CORS 响应，Label Studio 不需要修改 AWS S3 CORS。
- 新增 `scripts/label_studio/generate_s3_import.py`，把 S3 manifest 转为 Label Studio 单类别导入 JSON，并保留 `s3_uri`、`s3_bucket`、`s3_key`。
- 新增 `scripts/label_studio/export_s3_single_class_to_yolo.py`，标注后只生成 YOLO labels 和 `ec2_image_manifest.json|csv`，不在本地复制/下载训练图片。
- 新增 `scripts/cloud/ec2_s3_workflow.py`，提供 manifest/labels/YAML 上传、EC2 从 S3 下载图片、训练、评估、下载归档和下载模型 dry-run/执行能力。
- 新增 `makefiles/brand-s3-ec2/Makefile.mk` 和 `makefiles/brand-s3-ec2/README.md`，并在根 `Makefile` include。
- 新增 `config/brand_s3_ec2.example.yaml`，同时 `.gitignore` 忽略本地真实配置和 S3 流程生成数据。
- Web 控制台新增 “S3 图片 / EC2 训练” 菜单和相关参数输入。
- 已同步更新 `设计.md` 的 S3 训练图管理架构与命令说明。

验证结果：

- `uv run python -m unittest discover -s tests -p 'test_*.py'`：通过，46 个测试 OK。
- `uv run pylint scripts/s3 scripts/cloud/ec2_s3_workflow.py scripts/label_studio/generate_s3_import.py scripts/label_studio/export_s3_single_class_to_yolo.py tests/test_brand_s3_ec2_workflow.py`：通过，10.00/10。
- `node --check web-console/server.js`：通过。
- 从 `web-console/public/index.html` 提取内嵌 `<script>` 后执行 `node --check -`：通过。
- `make brand-s3-upload-images S3_DRY_RUN=1 S3_DATASET_NAME=smoke_s3_test S3_LOCAL_IMAGES_DIR=data/samples S3_BUCKET=example-bucket S3_PREFIX=yolo-training/smoke_s3_test S3_LIMIT=1`：通过，生成 S3 manifest 和 URL 文件。
- `make brand-s3-ls-import-json S3_DATASET_NAME=smoke_s3_test S3_BUCKET=example-bucket`：通过，生成 Label Studio 导入 JSON 和 XML 标签配置。

注意事项：

- 已新增依赖 `boto3>=1.34.0` 并执行 `uv lock` 更新锁文件。
- 真实 S3 上传和 EC2 下载/训练仍需要用户提供有效 S3 bucket、AWS 凭证或 EC2 IAM Role、EC2 SSH 参数。
- EC2 相关命令仍默认 dry-run，必须显式 `EC2_EXECUTE=1` 才会连接远端。
