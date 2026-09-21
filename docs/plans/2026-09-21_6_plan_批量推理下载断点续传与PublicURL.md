# 批量推理下载断点续传与 Public URL 优化计划

## 背景

用户反馈 `label-s3-ec2-download-predict-results` 已支持进度日志和并发下载，但还需要：

1. 已经下载过的结果文件/原始图片应跳过，不重复下载；未下载或空文件继续下载，实现断点续传。
2. 如果配置了 `public_base_url`（例如 `https://uat-smdp4cust-bak.s3.af-south-1.amazonaws.com`），下载 S3 结果文件时优先使用 public URL 直连下载；如果未配置，则继续使用 boto3。若 public URL 未必更快，但配置后按用户意图使用它，并在控制台暴露参数。

## 已阅读上下文

- `scripts/s3/download_predict_results.py`：当前负责本地下载 `uploaded_s3_uris.txt`、结果文件和原始推理图片；已加入并发下载、实时日志和 HTTP timeout。
- `makefiles/ec2/Makefile.mk`：已有 `EC2_PREDICT_DOWNLOAD_WORKERS`、`EC2_PREDICT_SOURCE_DOWNLOAD_TIMEOUT`、`EC2_PREDICT_DOWNLOAD_SOURCE_IMAGES` 等下载参数。
- `makefiles/label-workflow/Makefile.mk`：`label-s3-ec2-download-predict-results` 当前调用下载脚本并传入 profile/region/endpoint、workers、timeout。
- `makefiles/brand-s3-ec2/Makefile.mk`：兼容下载命令同样调用下载脚本。
- `web-console/server.js`：下载命令已加入控制台，参数白名单已有 `S3_PUBLIC_BASE_URL`，但下载命令参数列表尚未包含该参数。

## 阶段结果

- 已在 `scripts/s3/download_predict_results.py` 实现断点续传：结果文件和原始推理图片如果本地已存在且非空，会打印 `skip existing ...` 并跳过。
- 已支持 `--public-base-url`：当设置 `S3_PUBLIC_BASE_URL` 时，S3 结果文件和 S3 原图会优先转为 public URL 通过 HTTP 下载，失败后回退 boto3。
- 已保留并发下载、实时进度日志和 HTTP timeout；下载模式日志会显示 `mode=public+boto3-fallback` 或 `mode=boto3`。
- 已在 `label-s3-ec2-download-predict-results` 和 `brand-s3-ec2-download-predict-results` 透传 `--public-base-url '$(S3_PUBLIC_BASE_URL)'`。
- 已在 Web 控制台“下载 EC2 批量推理结果”参数中加入 `S3_PUBLIC_BASE_URL`。
- 已更新 `README.md`、`makefiles/label-workflow/README.md`，说明断点续传、public URL 优先下载和并发参数。
- 已验证：`uv run python -m unittest discover -s tests -p 'test_download_predict_results.py' && uv run python -m unittest discover -s tests -p 'test_brand_s3_ec2_workflow.py'` 通过，共 27 个测试。
- 已验证：`uv run pylint scripts/s3/download_predict_results.py tests/test_download_predict_results.py` 评分 10.00/10。
- 已 dry-run 验证下载命令已包含 `--public-base-url`、`--workers` 和 `--source-download-timeout`。

## 实现方案

### 1. 已下载文件跳过

修改 `scripts/s3/download_predict_results.py`：

1. 在下载 S3 结果文件前检查本地目标文件：
   - 如果目标文件存在且大小大于 0，则跳过。
   - 打印：`skip existing result file i/N <target>`。
   - 报告中记录 `status=skipped_existing`。
2. 在下载原始图片前检查本地目标文件：
   - 如果目标文件存在且大小大于 0，则跳过。
   - 打印：`skip existing source image i/N <target>`。
   - 报告中记录 `status=skipped_existing`。
3. 空文件视为未完成下载，继续重新下载。
4. 统计报告新增/保留 skipped 状态，便于确认断点续传效果。

### 2. 结果文件支持 public base URL 下载

修改 `scripts/s3/download_predict_results.py`：

1. 新增参数：
   - `--public-base-url`：公开 S3/CDN Base URL，例如 `https://uat-smdp4cust-bak.s3.af-south-1.amazonaws.com`。
2. 对于 `uploaded_s3_uris.txt` 和其中列出的结果文件：
   - 如果 `--public-base-url` 非空，优先把 `s3://bucket/key` 转成 `public_base_url/key` 通过 HTTP 下载。
   - 如果 public URL 下载失败，保守回退 boto3 下载，避免 public URL 临时不可用导致整个流程失败。
   - 如果 `--public-base-url` 为空，继续使用 boto3。
3. 原始图片下载：
   - 原始图片如果本身是 HTTP(S) CDN URL，继续直接 HTTP 下载。
   - 原始图片如果是 `s3://bucket/key` 且 `--public-base-url` 非空，也优先使用 public URL 下载，再回退 boto3。
4. 日志体现下载模式：
   - `download result file ... via public ...`
   - `download result file ... via boto3 ...`
   - 回退时打印 `public download failed, fallback boto3 ...`。

### 3. Make 参数透传

修改 `makefiles/label-workflow/Makefile.mk`：

- `label-s3-ec2-download-predict-results` 增加：
  ```bash
  --public-base-url '$(S3_PUBLIC_BASE_URL)'
  ```

修改 `makefiles/brand-s3-ec2/Makefile.mk`：

- `brand-s3-ec2-download-predict-results` 同样增加 `--public-base-url '$(S3_PUBLIC_BASE_URL)'`。

`makefiles/ec2/Makefile.mk` 不需要新增变量，因为已有通用 `S3_PUBLIC_BASE_URL`；如需在 `ec2-print-params` 展示，可不强制添加，避免 EC2 公共参数和 S3 参数职责混淆。

### 4. 控制台参数补充

修改 `web-console/server.js`：

- 在“下载 EC2 批量推理结果”命令的参数列表中加入：
  - `S3_PUBLIC_BASE_URL`

`PARAM_DEFINITIONS` 已存在 `S3_PUBLIC_BASE_URL`，无需新增定义。

### 5. 文档同步

更新：

- `README.md`：下载命令示例加入 `S3_PUBLIC_BASE_URL=https://uat-smdp4cust-bak.s3.af-south-1.amazonaws.com`，并说明已下载文件会跳过。
- `makefiles/label-workflow/README.md`：同步说明。
- 本计划文件追加阶段结果。

`设计.md` 不涉及架构变化，仅是下载行为优化，原则上不更新。

### 6. 测试与静态检查

计划更新测试：

1. `tests/test_download_predict_results.py`
   - 验证 `public_base_url` 拼接逻辑。
   - 验证目标文件存在且非空时跳过。
   - 验证 `--public-base-url` 参数可解析。
2. `tests/test_brand_s3_ec2_workflow.py`
   - 验证控制台下载命令包含 `S3_PUBLIC_BASE_URL`。

执行：

```bash
uv run python -m unittest discover -s tests -p 'test_download_predict_results.py'
uv run python -m unittest discover -s tests -p 'test_brand_s3_ec2_workflow.py'
uv run pylint scripts/s3/download_predict_results.py tests/test_download_predict_results.py
```
