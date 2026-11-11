# S3 上传本地图片与数据文件自动填充 ContentType 计划

## 背景与问题分析

在当前项目中使用 S3 上传功能（如执行 `make brand-s3-upload-images` 或运行 `scripts/s3/upload_images_to_s3.py`、`scripts/ec2/s3_batch_predict.py`）时，底层直接调用 `boto3` 的 `client.upload_file(str(image_path), config.bucket, key)`，未传入 `ExtraArgs`。

当用户或调用方未显式传递 `ExtraArgs={"ContentType": ...}` 时，AWS S3 服务端及 boto3 默认会将对象 ContentType 设置为 `binary/octet-stream`。

带来的主要问题：
1. **浏览器预览受阻**：在 Label Studio、Nginx 代理或通过公网 HTTP(S) URL 访问图片时，`binary/octet-stream` 会导致浏览器将其当作二进制下载流而不是直接渲染图片。
2. **元数据不准确**：上传后生成的清单文件（`s3_images.json`、`s3_images.csv`）通过 `head_object` 读取到的 `content_type` 也是 `binary/octet-stream`，失去了真实格式信息。
3. **其他文件格式扩散**：除了图片之外，EC2 批量推理结果上传的 `.json`、`.csv`、`.txt` 等同样面临被保存为 `binary/octet-stream` 的问题。

用户明确要求：
> 当用户没有显式传递 `ExtraArgs={"ContentType": ...}` 时，自动依据文件后缀填充 `image/jpeg`、`image/png`、`application/json` 等，彻底杜绝 S3 默认将其落成 `binary/octet-stream`。

## 已阅读的相关上下文与既定架构

- `设计.md`（第 527-542 行）：S3 上传脚本 `scripts/s3/upload_images_to_s3.py` 负责把本地训练图片目录上传至 S3，并生成 `s3_images.json/csv`；修改方案需要保持既有路径规则与断点续传逻辑，并同步更新文档说明。
- `scripts/s3/brand_s3_config.py`：纯逻辑公共模块，负责路径解析、前缀处理与 URL 计算，不直连 AWS，便于单元测试脱离 AWS 凭证运行。非常适合作为 MIME 推断与 `ExtraArgs` 补全逻辑的沉淀位置。
- `scripts/s3/upload_images_to_s3.py`：图片并发上传入口，当前在 `upload_one_image` 中调用 `client.upload_file`，并用 `client.head_object` 采集 `ContentType`。
- `scripts/ec2/s3_batch_predict.py`：EC2 批量推理脚本，在 `upload_results_to_s3` 中上传预测结果汇总 JSON、CSV、带框图和清单。
- `tests/test_brand_s3_ec2_workflow.py`：已有 S3 与 EC2 工作流测试用例，可复用 Mock Client 机制测试 `ExtraArgs` 传递与 ContentType 填充。

## 详细实施计划

### 1. 公共 MIME 推断与 ExtraArgs 解析逻辑 (`scripts/s3/brand_s3_config.py`)

1. **定义常用扩展名标准映射 `KNOWN_CONTENT_TYPES`**：
   - 图片格式：
     - `.jpg`, `.jpeg` -> `image/jpeg`
     - `.png` -> `image/png`
     - `.webp` -> `image/webp`
     - `.bmp` -> `image/bmp`
     - `.gif` -> `image/gif`
     - `.tif`, `.tiff` -> `image/tiff`
     - `.svg` -> `image/svg+xml`
   - 数据与文本格式：
     - `.json` -> `application/json`
     - `.csv` -> `text/csv`
     - `.txt` -> `text/plain`
     - `.yaml`, `.yml` -> `text/yaml`
     - `.xml` -> `application/xml`
2. **实现 `guess_content_type(file_path: str | Path, fallback: str = "application/octet-stream") -> str`**：
   - 优先查 `KNOWN_CONTENT_TYPES`（规避不同操作系统上 `/etc/mime.types` 的缺失或差异）；
   - 若未命中，回退至 Python 标准库 `mimetypes.guess_type`；
   - 仍未识别时返回 fallback（默认 `application/octet-stream`）。
3. **实现 `resolve_s3_extra_args(file_path: str | Path, extra_args: dict[str, Any] | None = None) -> dict[str, Any]`**：
   - 复制原有 `extra_args`（避免修改入参字典引用）；
   - 支持检查 `ContentType` 及大小写形式 `content_type`；
   - **当未显式传递 ContentType 时**：自动调用 `guess_content_type(file_path)` 填充 `resolved["ContentType"]`；
   - **当调用方显式传递了 ContentType 时**：严格保留调用方传递的值；若传递的是小写 `content_type`，规范化为 S3 标准的 `ContentType`；
   - 保留其他原样传入的 `ExtraArgs` 参数（例如 `ACL`、`ServerSideEncryption` 等）。
4. **实现通用上传包装器 `upload_file_to_s3(client: Any, file_path: str | Path, bucket: str, key: str, extra_args: dict[str, Any] | None = None, **kwargs: Any) -> None`**：
   - 统一封装 `client.upload_file`，内部调用 `resolve_s3_extra_args` 并透传至 `ExtraArgs`。

### 2. 本地图片上传逻辑改造 (`scripts/s3/upload_images_to_s3.py`)

1. 在 `upload_one_image` 中引入 `extra_args: dict[str, Any] | None = None` 参数：
   - 调用 `upload_file_to_s3` 或 `resolve_s3_extra_args`；
   - 执行 `client.upload_file(str(image_path), config.bucket, key, ExtraArgs=resolved_extra_args)`；
   - 确保从 `client.head_object` 获取到的 `ContentType` 符合推断类型（如 `image/jpeg`、`image/png` 等）。
2. 在 `upload_images` 中支持接收 `extra_args` 并透传给多线程执行器。

### 3. EC2 结果上传同步改造 (`scripts/ec2/s3_batch_predict.py`)

1. 在 `upload_results_to_s3` 中，将结果文件（`summary.json`、`summary.csv`、`uploaded_s3_uris.txt`、`source_image_uris.txt`、`annotated/*.jpg`、`json/*.json`）上传逻辑改为使用 `resolve_s3_extra_args`；
2. 彻底杜绝推理结果文件被 S3 默认标记为 `binary/octet-stream`。

### 4. 架构文档更新 (`设计.md`)

- 在第 531 行 `S3 上传脚本` 说明中，补充说明：
  > 上传时自动根据文件扩展名推断并设置 `ExtraArgs={"ContentType": ...}`（例如 `image/jpeg`、`image/png`、`application/json` 等），彻底杜绝 S3 默认将其落成 `binary/octet-stream`；调用方也可以显式传递自定义 `ContentType`。

### 5. 测试用例补充与验证 (`tests/test_brand_s3_ec2_workflow.py`)

1. **测试 `guess_content_type`**：覆盖 `.jpg`、`.jpeg`、`.png`、`.webp`、`.json`、`.csv`、`.txt`、`.yaml` 以及未知后缀。
2. **测试 `resolve_s3_extra_args`**：
   - 无 `extra_args` 时自动补充正确的 `ContentType`；
   - 有其他参数（如 `{"ACL": "public-read"}`）但无 `ContentType` 时，原有参数保留并补充 `ContentType`；
   - 显式指定 `{"ContentType": "application/custom"}` 时，保留显式值不被覆盖。
3. **测试 `upload_one_image` 与 Mock S3 Client**：
   - 验证调用 `client.upload_file` 时传递了包含推断 `ContentType` 的 `ExtraArgs`；
   - 验证 `head_object` 返回该 `ContentType` 能够正确写入返回的记录中。
4. **运行全量测试与静态检查**：
   - `uv run python -m unittest discover tests` 全量通过；
   - `uv run pylint scripts/s3/brand_s3_config.py scripts/s3/upload_images_to_s3.py scripts/ec2/s3_batch_predict.py tests/test_brand_s3_ec2_workflow.py` 满分 10.00/10 通过。

## 执行结果与阶段性结论

- **完成公共推断与 ExtraArgs 组装工具**：在 `scripts/s3/brand_s3_config.py` 中实现了 `KNOWN_CONTENT_TYPES` 常见映射字典、`guess_content_type` 函数、`resolve_s3_extra_args` 函数以及通用封装 `upload_file_to_s3`。
- **完成本地图片上传脚本改造**：在 `scripts/s3/upload_images_to_s3.py` 中改造了 `upload_one_image` 与 `upload_images`，上传时默认自动携带推断的 `ContentType`，若显式传递 `ExtraArgs` 则保留用户显式值。
- **完成 EC2 推理结果上传同步改造**：在 `scripts/ec2/s3_batch_predict.py` 中使用 `upload_file_to_s3` 自动推断上传汇总 JSON、CSV、TXT 和带框图。
- **同步更新架构设计文档**：已在 `设计.md` 对应章节明确记录 S3 ContentType 自动填充与自定义规则。
- **单元测试验证**：在 `tests/test_brand_s3_ec2_workflow.py` 中新增 5 个专项测试用例，全项目 92 个单元测试全部通过。
- **静态代码检查**：所有修改文件执行 `pylint` 检查，均获得 10.00/10 满分评价。

