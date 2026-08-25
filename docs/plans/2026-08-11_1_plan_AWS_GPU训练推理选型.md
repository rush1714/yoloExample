# AWS GPU 训练与推理资源选型建议

日期：2026-08-11

## 背景

项目目标是进行纸尿裤、洗衣粉、香皂、湿巾纸等门店陈列识别。每个国家可能有数万张图片需要训练和推理，模型主线暂定为 YOLO26m Detect。

## 结论

生产训练和生产推理建议分开选型：

- 训练：优先使用 NVIDIA GPU 实例，首选 G6e / G5 / P5，不建议第一阶段使用 Trainium。
- 批量推理：优先使用 G6，也可用 G5；吞吐压力大时横向扩展多台 G6。
- 在线推理：优先使用 G6 小规格或 SageMaker Async Inference。
- 离线全量跑数：优先使用 SageMaker Batch Transform、AWS Batch 或 ECS GPU 任务，不建议长期常驻大 GPU。

## 推荐配置

### 训练

第一阶段推荐：

- g6e.2xlarge / g6e.4xlarge：单卡 L40S，适合 YOLO26m 训练和调参。
- g5.4xlarge：单卡 A10G，成本相对可控，适合作为兼容备选。

数据量增大或需要更快迭代时：

- g6e.12xlarge / g6e.24xlarge：多卡 L40S，用于多实验或分布式训练。
- p5.4xlarge / p5.48xlarge：H100，高性能训练，但成本高，建议只在训练瓶颈明显时使用。

不建议第一阶段使用：

- Trn / Trainium：虽然适合大规模深度学习训练，但 YOLO + Ultralytics + PyTorch/CUDA/TensorRT 生态在 NVIDIA GPU 上更直接，迁移成本更低。

### 推理

批量推理推荐：

- g6.xlarge / g6.2xlarge / g6.4xlarge：L4 GPU，适合大批量图片检测。
- g5.xlarge / g5.2xlarge：A10G 备选。

在线或准实时推理推荐：

- SageMaker Async Inference + g6.xlarge 起步。
- 如果接口需要低延迟且请求稳定，再使用 SageMaker Real-time Endpoint 或 ECS/Kubernetes 常驻服务。

不建议第一阶段使用：

- Inf2 / Inferentia：适合成本优化后的大规模推理，但 YOLO 模型需要适配 Neuron 编译链路。第一阶段应先用 NVIDIA + TensorRT 跑通生产闭环。

## 模型格式建议

训练产物保留：

- best.pt：训练、验证、回滚、继续训练使用。
- ONNX：跨平台推理和兼容层。
- TensorRT engine：NVIDIA GPU 生产推理使用。

推理部署优先级：

1. PyTorch `.pt`：验证最方便。
2. ONNX：作为通用导出格式。
3. TensorRT FP16：生产 GPU 推理首选。
4. TensorRT INT8：有代表性校准集后再测试，只有 mAP 损失可接受时使用。

## 建议架构

```text
S3 原始图片
  -> 数据清洗 / 标注 / 数据集版本
  -> SageMaker 或 EC2 GPU 训练
  -> best.pt / ONNX / TensorRT 模型入库
  -> 批量推理任务读取 S3 图片
  -> JSON 识别结果 / 带框图片 / 统计结果写回 S3 或数据库
  -> 人工复核与错误样本回流
```

## 第一阶段最小可落地组合

训练：

- EC2 g6e.4xlarge 或 SageMaker Training Job 对应 G6e/G5 GPU 实例。
- 训练 `yolo26m.pt`，`imgsz=960`，`epochs=100`。

批量推理：

- EC2 g6.4xlarge 或 SageMaker Batch Transform。
- 使用 TensorRT FP16 模型。
- 按国家、日期、门店或批次切分任务并行运行。

在线推理：

- 如果只是后台审核，不需要在线 endpoint。
- 如果业务 APP 上传后需要几秒到几十秒返回，使用 SageMaker Async Inference。
- 如果必须秒级返回且请求稳定，使用常驻实时 endpoint。
