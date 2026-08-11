# MacBook 多机联合训练 YOLO26m 可行性判断

日期：2026-08-11

## 结论

不建议将 5 台不同型号的 MacBook 组成分布式训练集群来联合训练 `yolo26m.pt`。

更可落地的方案是：

1. 使用 M1 Max 32G 作为主训练机，训练 `yolo26m.pt`。
2. 3 台 M4 16G 分别承担并行实验、数据清洗、OCR、伪标注、验证集评估、不同超参数对照等任务。
3. 如果训练耗时成为瓶颈，优先使用单台 NVIDIA GPU 云主机或工作站，而不是尝试异构 Mac 多机 DDP。

## 判断依据

- Ultralytics YOLO 支持 Apple Silicon MPS 单机训练，也支持多 GPU DDP 训练。
- 但 Ultralytics 的多 GPU 训练主要面向同一机器内的多 GPU，或标准 CUDA/NVIDIA 分布式训练环境。
- 多台 MacBook 之间的异构 MPS 分布式训练不是 YOLO 的常规落地路径，需要自行处理 PyTorch Distributed、网络同步、数据一致性、checkpoint、容错等问题。
- 训练是同步任务，异构机器会被最慢节点拖慢；MacBook 之间通过局域网同步梯度，网络通信开销可能抵消并行收益。
- M4 16G 与 M1 Max 32G 的显存/统一内存和算力差异较大，训练 `yolo26m.pt` 时难以配置统一 batch 和稳定吞吐。

## 推荐分工

### M1 Max 32G

主训练：

```bash
uv run python scripts/training/train.py \
  --base-model models/yolo26m.pt \
  --epochs 100 \
  --imgsz 960 \
  --batch -1 \
  --device mps
```

### M4 16G 机器

并行承担：

- 跑 `yolo26s.pt` 快速 baseline。
- 跑不同 `imgsz`、增强参数、类别定义的对照实验。
- OCR、伪标注、Label Studio 导入前处理。
- 训练后推理验证、错误样本挖掘、混淆样本整理。
- 小目标专项实验，例如香皂、湿巾等小包装漏检分析。

## 后续建议

如果数据规模扩大、训练时间成为主要瓶颈，建议使用单台云 GPU 或本地 NVIDIA 工作站，例如 L4、A10、A100、4090 等，而不是投入成本搭建 MacBook 分布式训练。
