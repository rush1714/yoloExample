# EC2 公共参数

本目录只保存所有 EC2 流程共享的连接、训练和 dry-run 参数。具体数据来自哪里，由各业务目录决定：

- `makefiles/diaper-category-ec2/`：纸尿裤 Excel / Label Studio 数据集上传到 EC2。
- `makefiles/local-dir/`：本地目录图片标注后的 YOLO 数据集上传到 EC2。
- `makefiles/brand-s3-ec2/`：本地图片先上传 S3，EC2 再按 manifest 下载图片训练。

## 统一训练参数

不再使用固定档位预设命令。训练规模统一通过显式参数控制：

```bash
make diaper-ec2-train \
  EC2_BASE_MODEL=yolo26m.pt \
  EC2_TRAIN_EPOCHS=100 \
  EC2_TRAIN_IMGSZ=960 \
  EC2_TRAIN_BATCH=-1 \
  EC2_TRAIN_DEVICE=0 \
  EC2_RUN_NAME=yolo26m_img960_e100
```

`EC2_RUN_NAME` 只用于输出目录和评估报告标识；不会自动改变模型、尺寸或轮数。

## dry-run

所有 EC2 目标默认只打印要执行的 SSH / rsync 命令。确认无误后再加：

```bash
EC2_EXECUTE=1
```

## 命令示例索引

| 命令 | 作用 | 示例 |
|---|---|---|
| `ec2-print-params` | 显示 EC2 公共连接与训练参数 | `make ec2-print-params` |
