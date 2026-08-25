# YOLO 图片检测训练工程化落地方案

日期：2026-08-13

## 一句话结论

**不建议把当前 YOLO 训练工程直接迁移进 `/Users/guobiao/PRO/sunda/4cust/smdp4cust-analysis-component` 这个 Java 微服务里。**

更推荐的落地方式是：

> **新建一个独立的 Python / GPU AI 服务仓库，专门负责图片导入、预标注、标注数据转换、YOLO 训练、模型管理、批量推理；原 Java 微服务继续负责业务系统集成、权限、任务编排、结果入库和对外 API。**

也就是说：

```text
Java 微服务：业务编排层 / 对外服务层
Python YOLO 服务：AI 训练与推理执行层
MySQL：任务、图片、标注、模型、推理结果元数据
S3：原图、标注文件、训练数据集、模型权重、推理结果图
EC2 GPU：训练和批量推理执行环境
GitLab：独立 AI 服务代码仓库 + CI/CD
```

---

## 1. 是否迁移到现有 Java 微服务？

### 不建议直接迁入 Java 微服务

现有 Java 服务是一个 Spring Boot / Maven 多模块微服务：

```text
smdp4cust-analysis-component
├── smdp-analysis-common
├── smdp-analysis-service
├── smdp-analysis-service-api
├── deploy4cust/
└── pom.xml
```

它适合做：

- 业务 API；
- 任务状态管理；
- MySQL 数据读写；
- 权限、租户、客户、门店等业务上下文；
- 调用外部 AI 服务；
- 对前端或其它系统提供统一接口。

但不适合直接塞入 YOLO 训练工程，原因是：

| 维度 | 现有 Java 服务 | YOLO 训练工程 |
|---|---|---|
| 技术栈 | Java 8 / Spring Boot | Python / PyTorch / Ultralytics / CUDA |
| 运行环境 | 普通 CPU 容器即可 | GPU / NVIDIA Driver / CUDA / 大模型权重 |
| 任务模式 | 短请求、业务事务 | 长任务、可中断、可恢复、消耗 GPU |
| 文件规模 | 普通业务数据 | 图片、标签、模型权重、训练日志，体积大 |
| 部署频率 | 跟业务系统一致 | AI 依赖和模型迭代更频繁 |
| 故障影响 | 影响业务 API | 训练任务失败不应拖垮主业务服务 |

如果把 Python YOLO、PyTorch、CUDA、模型权重、图片处理都混进 Java 微服务，会导致：

1. Java 服务镜像变得非常大；
2. 部署链路复杂；
3. GPU 依赖污染业务服务；
4. 训练任务阻塞或拖慢业务 API；
5. 后续模型迭代、训练回滚、推理扩容都不灵活。

---

## 2. 推荐架构：独立 AI 服务 + Java 编排

### 总体架构

```text
                 ┌────────────────────────────┐
                 │  前端 / 管理后台 / 业务系统  │
                 └──────────────┬─────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────┐
│ Java 微服务 smdp4cust-analysis-component              │
│                                                       │
│ - 创建训练任务                                         │
│ - 管理图片、门店、客户、品牌、任务状态                  │
│ - 写 MySQL                                             │
│ - 调用 Python AI 服务                                  │
│ - 对外提供业务 API                                     │
└──────────────┬───────────────────────┬────────────────┘
               │                       │
               │ HTTP / MQ / 内网 API   │ MySQL
               ▼                       ▼
┌────────────────────────────────┐   ┌──────────────────────┐
│ Python YOLO AI Service          │   │ MySQL                 │
│                                │   │                      │
│ - 数据集构建                    │   │ - 图片元数据          │
│ - OCR / 预标注                  │   │ - 标注任务            │
│ - Label Studio / CVAT 对接       │   │ - 训练任务            │
│ - YOLO 训练                     │   │ - 模型版本            │
│ - 批量推理                      │   │ - 推理结果            │
│ - 模型导出                      │   │                      │
└──────────────┬─────────────────┘   └──────────────────────┘
               │
               │ S3 SDK
               ▼
┌────────────────────────────────┐
│ AWS S3                          │
│                                │
│ - raw images                    │
│ - annotation exports            │
│ - yolo datasets                 │
│ - model weights                 │
│ - training logs                 │
│ - inference results             │
└────────────────────────────────┘

训练 / 批量推理执行：

┌────────────────────────────────┐
│ AWS EC2 GPU                     │
│                                │
│ - g5.xlarge / g5.2xlarge        │
│ - g6 / g6e                      │
│ - Docker + NVIDIA runtime       │
│ - 挂载 EBS 缓存数据             │
│ - 从 S3 拉取图片和标注           │
│ - 训练后上传模型到 S3            │
└────────────────────────────────┘
```

---

## 3. 服务边界建议

### 3.1 Java 微服务负责什么？

Java 服务继续做业务主入口，建议负责以下内容。

#### 业务实体管理

- 客户；
- 国家；
- 门店；
- 访销员；
- 品牌；
- SKU；
- 陈列任务；
- 图片记录；
- 审核任务。

#### 训练任务编排

Java 创建训练任务，例如：

```json
{
  "country": "ghana",
  "customerCode": "xxx",
  "brandScope": ["SOFTCARE", "KLEESOFT"],
  "datasetVersion": "ghana-2026-08-v1",
  "baseModel": "yolo26m.pt",
  "epochs": 100,
  "imgsz": 960
}
```

然后调用 Python AI 服务：

```http
POST /api/v1/training-jobs
```

#### 任务状态查询

Java 从 Python 服务同步或回调训练状态：

```text
PENDING
PREPARING_DATASET
PRE_LABELING
WAITING_ANNOTATION
TRAINING
EVALUATING
COMPLETED
FAILED
CANCELLED
```

#### 业务结果落库

推理结果回写 Java 业务侧，例如：

```json
{
  "imageId": 12345,
  "modelVersion": "multibrand-ghana-v3",
  "brandCounts": {
    "softcare": 3,
    "kleesoft": 1
  },
  "totalCount": 4,
  "detections": [
    {
      "className": "softcare",
      "confidence": 0.91,
      "bbox": [125, 80, 340, 488]
    }
  ]
}
```

#### 对前端提供统一 API

前端不需要直接知道 Python AI 服务存在，统一访问 Java 微服务即可。

---

### 3.2 Python YOLO 服务负责什么？

Python 服务专注 AI 训练和推理，建议负责以下内容。

#### 图片导入

当前本地是从 Excel 读取图片 URL：

```text
Excel → 下载图片 → datasets/multibrand/raw/images
```

工程化后应该改成：

```text
业务图片 URL / 图片 ID → S3 raw bucket → MySQL image_asset
```

#### OCR 候选筛选

保留当前能力：

- RapidOCR；
- PaddleOCR；
- 本地 LLM OCR 可作为实验分支；
- 品牌关键词库匹配；
- 候选图片清单生成。

#### 自动预标注

保留当前能力：

- YOLO-World 文本 prompt 预标注；
- YOLOE visual prompt 预标注；
- 品牌参考图；
- 跨品牌去重；
- 大框过滤；
- 输出候选框。

#### 标注平台对接

短期可以继续 Label Studio。

但如果要长期多人协作，建议评估：

| 工具 | 建议 |
|---|---|
| Label Studio | 当前项目已经打通，短期继续用 |
| CVAT | 中长期更推荐，目标检测、多用户审核、数据集管理更成熟 |
| 自研标注后台 | 不建议一开始做，成本高 |

#### YOLO 数据集构建

将标注结果转换成标准 YOLO 格式：

```text
datasets/{dataset_version}/
├── images/
│   ├── train/
│   ├── val/
│   └── test/
├── labels/
│   ├── train/
│   ├── val/
│   └── test/
└── data.yaml
```

#### 训练

当前本地命令：

```bash
uv run python scripts/training/train.py \
  --data config/generated/multibrand.yaml \
  --base-model models/yolo26m.pt \
  --epochs 55 \
  --imgsz 960 \
  --device mps
```

云端应变成：

```bash
python -m yolo_service.jobs.train \
  --job-id train_20260813_001 \
  --dataset-s3-prefix s3://xxx/datasets/ghana-2026-08-v1/ \
  --base-model-s3-uri s3://xxx/base-models/yolo26m.pt \
  --epochs 100 \
  --imgsz 960 \
  --device 0
```

#### 推理

支持两种推理模式：

| 模式 | 用途 |
|---|---|
| 批量推理 | 对大量门店照片离线审核 |
| 在线推理 | 单张图片上传后准实时返回结果 |

第一阶段建议先做 **批量推理**，不要急着做在线 GPU 服务。

---

## 4. GitLab 仓库建议

### 推荐新建独立仓库

建议新建：

```text
smdp4cust-vision-ai-service
```

或者更明确：

```text
smdp4cust-yolo-training-service
```

更推荐第一个，因为未来不只 YOLO，还可能包含：

- OCR；
- 图片质量检测；
- 多模态模型；
- 门店画像；
- 陈列评分；
- 批量推理；
- 模型评估。

所以名字不要太窄。

### 新仓库目录建议

```text
smdp4cust-vision-ai-service/
├── README.md
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── .gitlab-ci.yml
├── configs/
│   ├── dev.yaml
│   ├── sit.yaml
│   ├── uat.yaml
│   └── prod.yaml
├── src/
│   └── vision_ai/
│       ├── api/
│       │   ├── main.py
│       │   ├── routes_training.py
│       │   ├── routes_inference.py
│       │   └── schemas.py
│       ├── db/
│       │   ├── models.py
│       │   ├── session.py
│       │   └── repositories.py
│       ├── storage/
│       │   ├── s3_client.py
│       │   └── paths.py
│       ├── datasets/
│       │   ├── builder.py
│       │   ├── splitter.py
│       │   ├── validator.py
│       │   └── yolo_exporter.py
│       ├── ocr/
│       │   ├── rapidocr_runner.py
│       │   └── brand_matcher.py
│       ├── pseudo_label/
│       │   ├── yolo_world.py
│       │   └── yoloe_visual.py
│       ├── training/
│       │   ├── trainer.py
│       │   ├── evaluator.py
│       │   └── exporter.py
│       ├── inference/
│       │   ├── predictor.py
│       │   └── batch_predictor.py
│       ├── jobs/
│       │   ├── training_job.py
│       │   ├── inference_job.py
│       │   └── worker.py
│       └── common/
│           ├── logging.py
│           ├── config.py
│           └── errors.py
├── scripts/
│   ├── run_training_job.py
│   ├── run_batch_inference.py
│   └── migrate_from_local_yolo_example.py
├── tests/
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── deployment-aws-ec2.md
│   └── data-contract.md
└── Makefile
```

---

## 5. S3 目录设计

建议一个业务独立 bucket，例如：

```text
s3://smdp4cust-vision-ai-prod/
```

里面按环境、国家、客户、数据集版本分层。

```text
s3://smdp4cust-vision-ai-prod/
├── raw-images/
│   └── country=ghana/
│       └── year=2026/
│           └── month=08/
│               └── image_id=xxx.webp
├── visual-prompts/
│   └── brand=SOFTCARE/
│       ├── ref_001.jpg
│       └── ref_002.jpg
├── annotations/
│   └── dataset=ghana-2026-08-v1/
│       ├── label-studio-export.json
│       ├── cvat-export.zip
│       └── normalized_annotations.json
├── datasets/
│   └── dataset=ghana-2026-08-v1/
│       ├── images/
│       │   ├── train/
│       │   ├── val/
│       │   └── test/
│       ├── labels/
│       │   ├── train/
│       │   ├── val/
│       │   └── test/
│       └── data.yaml
├── models/
│   └── model=multibrand/
│       └── version=2026-08-13-v1/
│           ├── best.pt
│           ├── last.pt
│           ├── best.onnx
│           ├── metrics.json
│           ├── confusion_matrix.png
│           └── args.yaml
├── training-runs/
│   └── job_id=train_20260813_001/
│       ├── logs/
│       ├── results.csv
│       ├── results.png
│       └── train_config.json
└── inference-results/
    └── job_id=infer_20260813_001/
        ├── results.jsonl
        ├── annotated/
        └── summary.json
```

核心原则：

1. **MySQL 存元数据，S3 存大文件。**
2. 图片、标签、模型、结果图都不要直接放 MySQL。
3. MySQL 里只存 S3 URI、状态、版本、指标、业务 ID 关联。

---

## 6. MySQL 表设计建议

### 6.1 图片资产表

```sql
CREATE TABLE vision_image_asset (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    biz_image_id VARCHAR(128) NULL COMMENT '业务系统图片ID',
    country_code VARCHAR(32) NOT NULL,
    customer_code VARCHAR(64) NULL,
    store_code VARCHAR(64) NULL,
    source_url TEXT NULL,
    s3_uri TEXT NOT NULL,
    image_format VARCHAR(16) NULL,
    width INT NULL,
    height INT NULL,
    file_size BIGINT NULL,
    md5 VARCHAR(64) NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

### 6.2 品牌类别表

```sql
CREATE TABLE vision_brand_class (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    brand_code VARCHAR(64) NOT NULL,
    brand_name VARCHAR(128) NOT NULL,
    class_id INT NOT NULL,
    enabled TINYINT NOT NULL DEFAULT 1,
    aliases JSON NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_brand_code (brand_code)
);
```

对应当前项目里的：

```text
config/brand_keywords.json
```

工程化后可以变成：

```text
MySQL 为主，JSON 配置导出为训练用快照
```

不要训练时直接读一个会变的品牌表，应该生成数据集版本时固化一份：

```text
dataset_version_classes.json
```

否则模型版本和 class_id 会对不上。

### 6.3 标注数据集表

```sql
CREATE TABLE vision_dataset (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    dataset_code VARCHAR(128) NOT NULL,
    country_code VARCHAR(32) NOT NULL,
    brand_scope JSON NOT NULL,
    class_snapshot_s3_uri TEXT NOT NULL,
    dataset_s3_prefix TEXT NOT NULL,
    train_count INT DEFAULT 0,
    val_count INT DEFAULT 0,
    test_count INT DEFAULT 0,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_dataset_code (dataset_code)
);
```

### 6.4 训练任务表

```sql
CREATE TABLE vision_training_job (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    job_code VARCHAR(128) NOT NULL,
    dataset_code VARCHAR(128) NOT NULL,
    base_model VARCHAR(128) NOT NULL,
    epochs INT NOT NULL,
    imgsz INT NOT NULL,
    batch_size VARCHAR(32) NULL,
    device VARCHAR(32) NULL,
    status VARCHAR(32) NOT NULL,
    progress DECIMAL(5,2) DEFAULT 0,
    error_message TEXT NULL,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_job_code (job_code)
);
```

### 6.5 模型版本表

```sql
CREATE TABLE vision_model_version (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    model_code VARCHAR(128) NOT NULL,
    model_version VARCHAR(128) NOT NULL,
    dataset_code VARCHAR(128) NOT NULL,
    training_job_code VARCHAR(128) NOT NULL,
    class_snapshot_s3_uri TEXT NOT NULL,
    pt_s3_uri TEXT NOT NULL,
    onnx_s3_uri TEXT NULL,
    metrics_s3_uri TEXT NULL,
    map50 DECIMAL(8,5) NULL,
    map50_95 DECIMAL(8,5) NULL,
    precision_score DECIMAL(8,5) NULL,
    recall_score DECIMAL(8,5) NULL,
    status VARCHAR(32) NOT NULL,
    is_active TINYINT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_model_version (model_code, model_version)
);
```

### 6.6 推理任务表

```sql
CREATE TABLE vision_inference_job (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    job_code VARCHAR(128) NOT NULL,
    model_code VARCHAR(128) NOT NULL,
    model_version VARCHAR(128) NOT NULL,
    input_scope JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_images INT DEFAULT 0,
    processed_images INT DEFAULT 0,
    result_s3_uri TEXT NULL,
    error_message TEXT NULL,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_job_code (job_code)
);
```

### 6.7 单图推理结果表

```sql
CREATE TABLE vision_inference_result (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    job_code VARCHAR(128) NOT NULL,
    image_asset_id BIGINT NOT NULL,
    model_code VARCHAR(128) NOT NULL,
    model_version VARCHAR(128) NOT NULL,
    brand_counts JSON NOT NULL,
    total_count INT NOT NULL,
    detections JSON NOT NULL,
    annotated_s3_uri TEXT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    KEY idx_job_code (job_code),
    KEY idx_image_asset_id (image_asset_id)
);
```

---

## 7. API 设计建议

### 7.1 创建训练任务

```http
POST /api/v1/training-jobs
```

请求：

```json
{
  "datasetCode": "ghana-2026-08-v1",
  "brandScope": ["SOFTCARE", "KLEESOFT"],
  "baseModel": "yolo26m.pt",
  "epochs": 100,
  "imgsz": 960,
  "batchSize": "-1",
  "device": "0"
}
```

响应：

```json
{
  "jobCode": "train_20260813_001",
  "status": "PENDING"
}
```

### 7.2 查询训练任务

```http
GET /api/v1/training-jobs/{jobCode}
```

响应：

```json
{
  "jobCode": "train_20260813_001",
  "status": "TRAINING",
  "progress": 42.5,
  "currentEpoch": 43,
  "totalEpochs": 100,
  "latestMetrics": {
    "precision": 0.82,
    "recall": 0.76,
    "map50": 0.81
  }
}
```

### 7.3 创建批量推理任务

```http
POST /api/v1/inference-jobs
```

请求：

```json
{
  "modelCode": "multibrand",
  "modelVersion": "2026-08-13-v1",
  "imageIds": [1001, 1002, 1003],
  "conf": 0.35,
  "imgsz": 960,
  "saveAnnotatedImage": true
}
```

响应：

```json
{
  "jobCode": "infer_20260813_001",
  "status": "PENDING"
}
```

### 7.4 单图推理

```http
POST /api/v1/predict
```

请求：

```json
{
  "modelCode": "multibrand",
  "modelVersion": "2026-08-13-v1",
  "imageS3Uri": "s3://smdp4cust-vision-ai-prod/raw-images/country=ghana/xxx.webp",
  "conf": 0.35
}
```

响应：

```json
{
  "brandCounts": {
    "softcare": 3,
    "kleesoft": 1
  },
  "totalCount": 4,
  "detections": [
    {
      "classId": 0,
      "className": "softcare",
      "confidence": 0.9214,
      "bbox": [125.2, 80.1, 340.8, 488.5]
    }
  ],
  "annotatedS3Uri": "s3://xxx/inference-results/xxx-annotated.jpg"
}
```

---

## 8. 任务执行方式建议

### 第一阶段：简单可落地

先不要引入太复杂的调度系统。

```text
Java 服务创建任务
        ↓
Python API 写 MySQL 任务状态
        ↓
Python Worker 轮询 PENDING 任务
        ↓
EC2 GPU 上执行训练
        ↓
结果上传 S3
        ↓
更新 MySQL
        ↓
Java 服务读取任务结果
```

也就是：

```text
FastAPI + MySQL + Background Worker
```

Python Worker 可以先用：

- APScheduler；
- Celery；
- RQ；
- 简单的 while loop job runner。

第一阶段建议：

```text
FastAPI + MySQL + Python Worker
```

不要一开始上 Kubernetes、SageMaker、复杂 MQ。

### 第二阶段：引入消息队列

任务量起来之后，再加：

```text
Java → SQS / RabbitMQ / Redis Queue → Python Worker
```

如果主要在 AWS 上，推荐：

```text
AWS SQS
```

### 第三阶段：训练任务容器化调度

成熟后可以升级为：

| 方案 | 适用情况 |
|---|---|
| EC2 常驻 GPU Worker | 初期最简单 |
| AWS Batch GPU Job | 批量训练、批量推理任务多 |
| ECS GPU Service | 有容器平台基础 |
| SageMaker Training Job | 需要更标准的 ML 平台化能力 |
| EKS GPU | 规模很大时再考虑 |

第一阶段建议：

```text
EC2 GPU + Docker + systemd / supervisor 运行 worker
```

---

## 9. AWS EC2 训练环境建议

### 初期实例选择

| 阶段 | 实例 | 说明 |
|---|---|---|
| 冒烟测试 | g5.xlarge | 1 张 A10G，成本相对低 |
| 正式训练 baseline | g5.2xlarge / g5.4xlarge | 更稳 |
| 更大模型或更大数据 | g6 / g6e | L4 / L40S，根据区域可用性 |
| 大规模训练 | p4 / p5 | 暂时不建议第一阶段用 |

当前模型方向是：

```text
yolo26s / yolo26m
imgsz=960
多品牌小目标检测
```

第一阶段建议：

```text
g5.2xlarge + yolo26m + imgsz 960
```

### EC2 目录建议

EC2 本地只做缓存，不作为最终存储。

```text
/opt/smdp-vision-ai/
├── app/
├── cache/
│   ├── datasets/
│   ├── models/
│   └── raw-images/
├── runs/
│   ├── train/
│   └── predict/
└── logs/
```

流程：

```text
从 S3 下载数据集到 /opt/.../cache
训练
输出到 /opt/.../runs
上传模型、日志、指标到 S3
本地缓存可清理
```

---

## 10. Docker 镜像建议

建议拆两个镜像。

### CPU API 镜像

用于：

- 接收 API；
- 管理任务；
- 访问 MySQL；
- 访问 S3；
- 不跑训练。

```text
smdp4cust-vision-ai-api:latest
```

### GPU Worker 镜像

用于：

- YOLO 训练；
- YOLO 推理；
- OCR；
- 预标注；
- 依赖 PyTorch CUDA。

```text
smdp4cust-vision-ai-gpu:latest
```

Dockerfile 基础镜像建议：

```dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
```

Python 包管理继续用 `uv`，这和当前项目一致。

---

## 11. GitLab CI/CD 建议

### 分支策略

```text
main        生产稳定分支
develop     集成测试分支
feature/*   功能分支
release/*   发布分支
```

### CI 阶段

```yaml
stages:
  - lint
  - test
  - build
  - docker
  - deploy-dev
  - deploy-prod
```

### 必做检查

当前项目要求 `pylint`，工程化后建议 CI 中固定执行：

```bash
uv run pylint src tests
uv run pytest
uv run python -m vision_ai.datasets.validator --sample
```

还可以增加：

```bash
ruff check src tests
mypy src
```

如果希望保持简单，第一阶段最低要求：

```text
pylint + pytest + Docker build
```

---

## 12. 标注系统建议

### 短期：继续 Label Studio

当前项目已经打通：

```text
Excel 图片导入
OCR
YOLO-World / YOLOE 预标注
Label Studio 导入
Label Studio 导出
YOLO 训练
```

短期可以把 Label Studio 服务也部署到 EC2 或内网服务器。

但需要把当前的本地文件模式：

```text
/data/local-files/?d=<absolute_path>
```

改成 S3 / HTTP 可访问模式。

推荐：

```text
Label Studio Task image 字段使用预签名 S3 URL
```

或者通过 Java 图片中心代理。

### 中长期：评估 CVAT

如果未来多人长期标注，建议中长期迁到 CVAT，原因：

- 目标检测标注体验更好；
- 多人任务分配更成熟；
- review / issue / job 管理更强；
- 支持导出 YOLO；
- 更适合规模化数据集建设。

但现在不要立刻切，先把 AI 训练服务工程化。

---

## 13. 当前 yoloExample 如何迁移？

当前项目不要推倒重写，应该迁移核心能力。

| 当前本地项目 | 工程化后 |
|---|---|
| `scripts/data_import/import_images_from_excel.py` | `vision_ai.datasets.importer`，支持 Excel / MySQL / S3 |
| `scripts/ocr/filter_brand_candidates.py` | `vision_ai.ocr.rapidocr_runner` |
| `scripts/pseudo_label/generate_yolo_world.py` | `vision_ai.pseudo_label.yolo_world` |
| `scripts/pseudo_label/generate_yoloe_visual.py` | `vision_ai.pseudo_label.yoloe_visual` |
| `scripts/label_studio/export_to_yolo.py` | `vision_ai.datasets.yolo_exporter` |
| `scripts/training/train.py` | `vision_ai.training.trainer` |
| `scripts/inference/predict.py` | `vision_ai.inference.predictor` |
| `config/brand_keywords.json` | MySQL 品牌表 + 数据集快照 JSON |
| `datasets/` | S3 datasets 前缀 |
| `models/` | S3 models 前缀 |
| `outputs/predict/` | S3 inference-results 前缀 |

---

## 14. 推荐落地路线

### Phase 0：保留本地 PoC，冻结当前能力

目标：

- 当前 `yoloExample` 继续作为实验项目；
- 不直接污染 Java 微服务；
- 整理当前训练流程、模型、指标、失败样本。

产出：

```text
本地 PoC 流程稳定
明确输入、输出、模型版本、评估指标
```

### Phase 1：新建 GitLab AI 服务仓库

仓库：

```text
smdp4cust-vision-ai-service
```

完成：

1. 初始化 Python 工程；
2. 迁移当前训练、推理、数据集转换核心脚本；
3. 保留 CLI 入口；
4. 增加 FastAPI；
5. 增加 MySQL 连接；
6. 增加 S3 上传下载；
7. 增加 Dockerfile；
8. 增加 GitLab CI。

此阶段先不追求全自动训练平台，先做到：

```text
可以通过 API 创建训练任务
可以在 EC2 GPU 上执行训练
可以上传模型到 S3
可以查询训练状态
```

### Phase 2：Java 微服务集成

在 Java 微服务中新增：

```text
VisionTrainingController
VisionInferenceController
VisionModelController
```

Java 不跑模型，只负责调用 Python 服务。

例如：

```text
POST /analysis/vision/training-jobs
GET  /analysis/vision/training-jobs/{jobCode}
POST /analysis/vision/inference-jobs
GET  /analysis/vision/inference-results
```

Java 侧可以保存业务任务和 AI 任务映射。

### Phase 3：S3 数据闭环

完成：

```text
业务图片 → S3 raw-images
标注结果 → S3 annotations
训练数据集 → S3 datasets
模型权重 → S3 models
推理结果 → S3 inference-results
```

同时 MySQL 中保存所有 S3 URI。

### Phase 4：生产训练任务

在 EC2 GPU 上部署：

```text
vision-ai-gpu-worker
```

支持：

- 训练任务恢复；
- 训练失败记录；
- 日志上传；
- 指标上传；
- 模型版本注册；
- best.pt / last.pt 保存；
- ONNX 导出。

### Phase 5：批量推理

先做离线批量推理，不急着在线实时。

流程：

```text
Java 创建批量推理任务
Python Worker 拉取图片
YOLO 推理
结果 JSONL 上传 S3
明细结果写 MySQL
Java 查询并展示
```

### Phase 6：模型上线管理

增加模型发布概念：

```text
候选模型 candidate
验收模型 validated
线上模型 active
废弃模型 archived
```

只有 `active` 模型可被生产推理任务使用。

---

## 15. 第一版 MVP 范围建议

### MVP 必须有

1. 独立 Python AI 服务仓库；
2. Docker 镜像；
3. MySQL 任务表；
4. S3 图片和模型存储；
5. EC2 GPU 手动或半自动训练；
6. 训练任务状态管理；
7. 批量推理任务；
8. Java 微服务通过 HTTP 调用 AI 服务；
9. 模型指标记录；
10. 推理结果回写 MySQL。

### MVP 暂时不做

1. 不做 Kubernetes；
2. 不做 SageMaker；
3. 不做复杂在线高并发推理；
4. 不做自研标注平台；
5. 不做自动扩缩容；
6. 不做多模型 A/B 在线分流；
7. 不做复杂 MLOps 平台。

---

## 16. 推荐技术选型

| 模块 | 推荐 |
|---|---|
| AI 服务框架 | FastAPI |
| Python 包管理 | uv |
| ORM | SQLAlchemy / SQLModel |
| 数据库 | MySQL |
| 大文件存储 | AWS S3 |
| 训练框架 | Ultralytics YOLO |
| OCR | RapidOCR 起步，生产评估 PaddleOCR |
| 标注 | 短期 Label Studio，中长期 CVAT |
| 异步任务 | 第一阶段 Python Worker，后续 SQS / Celery |
| 部署 | EC2 GPU + Docker |
| 镜像仓库 | GitLab Container Registry |
| CI | GitLab CI |
| 日志 | CloudWatch 或本地日志 + S3 |
| 监控 | CloudWatch + 任务表状态 |
| 模型格式 | 训练保留 `.pt`，推理逐步导出 ONNX / TensorRT |

---

## 17. 最终建议

### 不建议

```text
把 YOLO 训练工程直接塞进 smdp4cust-analysis-component Java 服务
```

### 建议

```text
新建 GitLab 仓库 smdp4cust-vision-ai-service
```

并采用：

```text
Java 业务微服务 + Python AI 服务 + MySQL 元数据 + S3 文件存储 + EC2 GPU Worker
```

### 迁移策略

不是重写，而是：

```text
把当前 yoloExample 中已经验证过的脚本能力，重构成 Python AI 服务的核心模块。
```

当前项目继续作为 PoC 和实验仓库，新仓库作为工程化生产仓库。

---

## 18. 推荐下一步

建议下一步按这个顺序做：

1. **新建 GitLab 仓库：`smdp4cust-vision-ai-service`**；
2. 把当前 `yoloExample` 的核心脚本迁移为 Python package；
3. 增加 `FastAPI` 服务骨架；
4. 增加 MySQL 表结构；
5. 增加 S3 读写封装；
6. 在本地先跑通：

```text
创建训练任务 → 读取 S3 数据集 → 训练 → 上传模型 → 查询状态
```

7. 再部署到 AWS EC2 GPU；
8. 最后让 Java 微服务调用 Python AI 服务。

---

## 19. 备注

本文档是工程化落地方案建议，不代表当前 `yoloExample` 已经完成架构迁移。若后续正式开始迁移或调整训练、推理、数据流架构，需要同步更新项目根目录下的 `设计.md`，确保架构文档与实现保持一致。
