# Softcare 纸尿裤检测与计数 Demo

## 已确认的范围

- 目标类别：仅识别 `softcare_diaper`，每个可见 Softcare 纸尿裤包装算一个实例并计数。
- 本次只实现可直接运行的 Python Demo；暂不接入 Vue 3 和 Spring Boot。
- 示例图片可下载到本地，但当前项目尚未安装 Ultralytics，且没有经过标注和训练的 Softcare 模型，因此此时无法可靠输出该图片的商品数量。

## 标注与数据方案

1. 采用**目标检测（bounding box）**：对每个可辨认的 Softcare 包装各画一个矩形框，类别统一设为 `softcare_diaper`；遮挡包装也标注其可见部分。
2. 先制作约 300–500 张多门店、多角度、不同光照和遮挡程度的图像；按训练/验证/测试约 70%/20%/10% 划分。同一原图的近似裁剪或连拍图只能放进一个划分，避免数据泄漏。
3. 将标注导出为 YOLO 格式：每张图片对应一个 `.txt`，每行是 `class_id center_x center_y width height`（坐标均归一化）；使用单类别 `0`。
4. 推荐标注工具：
   - **CVAT**：多人协作、审核流、预标注和 YOLO 导出能力最完整，首选生产数据集建设。
   - **Label Studio**：通用开源数据标注平台，适合扩展审核流或混合图文任务。
   - **Labelme**：轻量本地 Python 工具，适合快速人工框选，导出后需转换为 YOLO 格式。
   - **makesense.ai**：浏览器端开源工具，免部署，适合少量 PoC 数据；不适合作为长期协作平台。

## 目录与文件

1. 更新 `pyproject.toml`，添加运行依赖：`ultralytics`、`pillow` 与 `pyyaml`；开发环境通过 `uv sync` 安装。
2. 增加 `data/softcare.yaml`，声明训练、验证、测试图片目录及单一类别名 `softcare_diaper`。
3. 增加空目录占位约定（用 `.gitkeep`）：
   - `datasets/softcare/images/{train,val,test}`
   - `datasets/softcare/labels/{train,val,test}`
   - `models/`
   - `outputs/`
4. 增加 `scripts/download_sample.py`：下载给定 WebP 图片到 `data/samples/softcare-shelf.webp`，并拒绝非 HTTP(S) URL、HTTP 下载错误或空文件。
5. 增加 `scripts/train.py`：以预训练 `yolo26n.pt` 为起点，读取 `data/softcare.yaml`，提供 `--epochs`、`--imgsz`、`--device`、`--project` 等参数，训练完成后打印 `best.pt` 的位置。
6. 增加 `scripts/predict.py`：接收本地路径或 HTTP(S) 图片 URL 及 `--model`；运行预测，过滤 `softcare_diaper`，将每个框的类别、置信度和 `xyxy` 像素坐标写入 JSON，并在终端输出 `softcare_count`；同时保存含检测框的标注图片。
7. 增加 `scripts/validate_dataset.py`：检查图片与标签是否一一对应、YOLO 标签列数、类别 ID、归一化坐标范围及空数据集，并在训练前明确报错。
8. 增加 `README.md` 的运行章节：环境安装、示例图片下载、标注数据放置、数据校验、训练、推理、JSON 输出样例，以及准确率验收方法。

## 验证计划

1. 安装依赖后执行 `uv run python scripts/download_sample.py`，确认示例图片成功落盘并可由 Pillow 打开。
2. 用人工建立的最小 YOLO 标签夹具运行 `validate_dataset.py`，覆盖有效标注、越界坐标、未知类别和缺失标签四种情况。
3. 在未传入已训练 `best.pt` 时，让 `predict.py` 明确拒绝启动或显示“模型未训练”的可操作提示；不把 COCO 通用模型的结果伪装为 Softcare 计数。
4. 在提供至少一个训练后的模型与保留测试集时，执行推理，确认：输出 JSON 的 `softcare_count` 等于检测框数组长度、框坐标在图片范围内、带框图片确实生成。
5. 用未参与训练的门店照片做验收，人工逐张对比真实包数，统计 precision、recall、F1 与计数绝对误差；根据漏检/误检图片补充标注并迭代训练。

## 后续集成边界（本次不实现）

Python 推理服务应作为独立模型服务暴露 `POST /predict`，返回 JSON。Spring Boot 只负责鉴权、图片业务记录和调用模型服务；Vue 3 上传图片并显示原图、框选结果及 `softcare_count`。这样不会把 Python/torch 运行时嵌进 JVM，也符合“YOLO 识别 → 规则引擎 → 审核结果”的既有架构。
