# smdp4cust-vision-ai-service 初始化计划

## 目标

在 `/Users/guobiao/PRO/sunda/4cust/smdp4cust-vision-ai-service` 初始化一个独立的 Python 视觉 AI 服务工程，用于承接当前 YOLO 图片检测训练工程化能力。仓库已存在远端：`http://gitlab.sunda.top/crm/cust/smdp4cust-vision-ai-service.git`。本次只在本地创建并使用 `ai_init_version` 分支，不使用 `main` 分支开发。

## 已确认现状

- 新仓库当前在 `main` 分支，远端为 GitLab 地址，已有初始提交。
- 新仓库当前只有 `README.md` 和未跟踪的 `.idea/`。
- 参考 Java 服务位于 `/Users/guobiao/PRO/sunda/4cust/smdp4cust-analysis-component`，Jenkins 部署文件在 `deploy4cust/{dev,uat,prod}/`。
- Java 服务 Jenkins 使用 Jenkinsfile + Dockerfile + Kubernetes deployment.yml；UAT/Prod 使用 AWS ECR + EKS，Dev 使用内网镜像仓库/Rancher。
- 当前 YOLO PoC 项目已有完整流程：图片导入、OCR、YOLO-World/YOLOE 预标注、Label Studio 转 YOLO、训练、推理。

## 实施计划

### 1. 分支与仓库基础处理

1. 在新仓库创建并切换到本地分支：`ai_init_version`。
2. 添加 `.gitignore`，忽略：
   - `.idea/`、`*.iml`；
   - `.venv/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`；
   - 本地数据、模型、训练输出、日志、临时文件；
   - `.env` 和本地密钥文件。
3. 添加 `.editorconfig`，参考 Java 服务风格，并适配 Python / YAML / Markdown。

### 2. Python 工程骨架

初始化 `src` layout：

```text
src/vision_ai/
├── api/
├── common/
├── config/
├── datasets/
├── db/
├── inference/
├── jobs/
├── ocr/
├── pseudo_label/
├── storage/
└── training/
```

首版放入可运行的最小骨架：

- `api/main.py`：FastAPI 应用入口；
- `api/routes_health.py`：健康检查接口；
- `api/routes_training.py`：训练任务接口占位；
- `api/routes_inference.py`：推理任务接口占位；
- `common/settings.py`：环境变量配置；
- `common/logging.py`：日志初始化；
- `storage/s3_client.py`：S3 客户端封装占位；
- `db/session.py`：数据库连接占位；
- `jobs/worker.py`：后台任务 Worker 占位；
- `training/trainer.py`、`inference/predictor.py` 等模块占位。

### 3. 项目配置

新增：

- `pyproject.toml`：使用 Python 3.12+、FastAPI、Uvicorn、Pydantic Settings、SQLAlchemy、PyMySQL、Boto3、Ultralytics、Pillow、OpenCV、PyYAML、Pylint、Pytest 等依赖；
- `Makefile`：封装本地开发命令：
  - `make install`
  - `make lint`
  - `make test`
  - `make run-api`
  - `make run-worker`
  - `make docker-build-api`
  - `make docker-build-gpu`
- `.env.example`：提供 MySQL、S3、服务端口、日志级别等配置样例。

### 4. Docker 与部署目录

参考 Java 服务 `deploy4cust` 结构，但按 Python AI 服务调整：

```text
deploy4cust/
├── dev/
│   ├── Dockerfile.api
│   ├── Dockerfile.gpu
│   └── Jenkinsfile
├── uat/
│   ├── Dockerfile.api
│   ├── Dockerfile.gpu
│   ├── Jenkinsfile
│   └── deployment.yml
└── prod/
    ├── Dockerfile.api
    ├── Dockerfile.gpu
    ├── Jenkinsfile
    └── deployment.yml
```

说明：

- API 镜像用于 FastAPI 服务，不要求 GPU；
- GPU 镜像用于训练/批量推理 Worker，基于 NVIDIA CUDA runtime；
- UAT/Prod deployment 先部署 API 服务，GPU Worker 后续可用单独 Deployment / Job 扩展；
- Jenkinsfile 参考 Java 服务，但改为 Python：安装 uv、执行 pylint/pytest、构建 Docker 镜像、推送到 ECR、应用 K8S deployment。

### 5. 文档初始化

新增文档：

```text
docs/
├── architecture.md
├── api.md
├── deployment-jenkins.md
├── deployment-aws-ec2.md
├── data-contract.md
├── database-design.md
└── migration-from-yolo-example.md
```

重点写清楚：

- 为什么不把 YOLO 训练塞入 Java 微服务；
- Java 服务与 Python AI 服务边界；
- S3 目录约定；
- MySQL 表设计草案；
- 训练任务与推理任务 API 契约；
- Jenkins 部署说明；
- 从当前 `yoloExample` 迁移模块的对应关系。

同时重写根目录 `README.md`，说明：

- 项目定位；
- 本地启动方式；
- 目录结构；
- 环境变量；
- Jenkins/Docker/部署入口；
- 后续迁移路线。

### 6. 测试与校验

新增最小测试：

```text
tests/test_health.py
```

验证 FastAPI health endpoint。

初始化完成后执行：

- `python -m compileall src tests` 或等价语法检查；
- 如本机依赖可用，则执行 `pytest` / `pylint`；
- 若依赖未安装，则说明原因，并保证代码结构和配置文件已完整。

## 本次不做的内容

- 不直接迁移所有 YOLO 训练脚本实现；本次先搭好工程骨架和接口边界。
- 不提交或推送到 GitLab，除非用户后续明确要求。
- 不改动现有 Java 微服务仓库。
- 不删除新仓库中的未跟踪 `.idea/`，只通过 `.gitignore` 忽略。
- 不创建远端分支，除非用户后续明确要求 push。

## 预期交付

完成后，新仓库应具备：

1. 本地 `ai_init_version` 分支；
2. 可维护的 Python AI 服务工程目录；
3. FastAPI 最小可运行入口；
4. API / Worker / 训练 / 推理模块占位；
5. Jenkins + Docker + K8S 部署模板；
6. 完整初始化文档；
7. 可继续迁移当前 `yoloExample` 核心能力的清晰路径。
