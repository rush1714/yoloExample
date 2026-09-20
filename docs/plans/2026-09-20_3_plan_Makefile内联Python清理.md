# Makefile 内联 Python 清理计划

## 背景

用户执行：

```bash
make 3-label-s3-workflow-ec2-train COUNTRY=GH DATA_VERSION=v2026-09-20 LABEL_SET=general LABELS=kleesoft_purple,allround_purple S3_EC2_DOWNLOAD_MODE=auto EC2_HOST=18.209.241.0 EC2_USER=ec2-user EC2_KEY=~/.ssh/smdp-yolo-gpu-key.pem EC2_BASE_MODEL=yolo26m.pt EC2_TRAIN_EPOCHS=100 EC2_TRAIN_IMGSZ=960 EC2_TRAIN_BATCH=-1 EC2_TRAIN_DEVICE=0 EC2_RUN_NAME=yolo26m_img960_e100 EC2_EXECUTE=0
```

由于 `EC2_EXECUTE=0` 是 dry-run，脚本会打印将要执行的远端命令。当前 `scripts/ec2/s3_workflow.py` 在 `download-images` 阶段会拼出一大段 `python -c '<很多 Python 代码>'` 远端命令，所以 dry-run 输出里出现大量 Python 代码。用户认为这种方式不规范，要求检查所有 `Makefile.mk`，不要在 Makefile 命令里写 Python 代码。

## 已检查情况

### 1. 直接导致大量 Python 代码打印的问题

根因不在 `Makefile.mk` 直接写了大段 Python，而在：

```text
scripts/ec2/s3_workflow.py
```

其中：

```text
download_images_command()
```

会构造远端：

```text
python -c '<多行 Python 下载逻辑>'
```

dry-run 时被完整打印出来，看起来像 Makefile 输出了一大段 Python。

### 2. Makefile.mk 内实际存在的 Python 片段

搜索 `Makefile` 和 `makefiles/**/*.mk` 后，发现：

- 大多数 `$(VENV_BIN)/python scripts/...` 是正常调用独立脚本，不属于“把 Python 代码写在 Makefile 里”。
- 仍存在少量通过 `printf 'exec(open(...))' | label-studio shell` 或 `printf 'from django.core.management import call_command...' | label-studio shell` 的内联 Python 片段，位置包括：
  - `makefiles/common/Makefile.mk`
  - `makefiles/label-workflow/Makefile.mk`
  - `makefiles/local-dir/Makefile.mk`
  - `makefiles/brand-s3-ec2/Makefile.mk`
  - `makefiles/diaper-category-ec2/Makefile.mk`

这些虽然不是大段业务逻辑，但也属于 Makefile 中嵌入 Python 片段，应一并清理。

## 实施计划

### 1. 把 EC2 下载图片远端 Python 代码移出命令字符串

新增远端执行脚本：

```text
scripts/ec2/download_s3_manifest_images.py
```

职责：

- 读取 `ec2_image_manifest.json`。
- 按 `split` 和 `training_image_name` 下载图片到远端：

```text
<remote_dataset_root>/images/{train,val,test}/
```

- 支持现有三种下载模式：
  - `auto`
  - `public`
  - `boto3`
- 保持现有校验：
  - manifest 不能为空。
  - 不能误用上传阶段的 `s3_images.json`。
  - public 模式必须能得到公共 URL。
  - boto3 模式必须有 `s3_bucket` / `s3_key`。

修改：

```text
scripts/ec2/s3_workflow.py
```

将 `download_images_command()` 从 `python -c '<大段代码>'` 改为：

1. 通过 `rsync` 上传 `scripts/ec2/download_s3_manifest_images.py` 到 EC2 项目的同路径。
2. 远端执行类似：

```bash
python3 scripts/ec2/download_s3_manifest_images.py \
  --manifest <remote_manifest_json> \
  --dataset-root <remote_dataset_root> \
  --download-mode auto \
  --public-base-url <S3_PUBLIC_BASE_URL>
```

这样 `EC2_EXECUTE=0` dry-run 时只会打印短命令，不再打印大段 Python 源码。

### 2. 清理 Makefile.mk 中的 Label Studio shell 内联 Python

将这类写法：

```makefile
printf 'exec(open(".../apply_import.py", encoding="utf-8").read())\nexit()\n' | label-studio shell ...
```

改成把脚本文件直接作为 stdin：

```makefile
label-studio shell --data-dir ... < scripts/label_studio/apply_import.py
```

计划替换涉及：

- `makefiles/common/Makefile.mk`
  - `ls-migrate` 改为独立脚本。
  - `ls-apply` 改为 stdin 文件方式。
  - `ls-clone-annotated-project` 改为 stdin 文件方式。
- `makefiles/label-workflow/Makefile.mk`
  - `label-ls-apply`
  - `label-s3-ls-apply`
- `makefiles/local-dir/Makefile.mk`
  - `local-dir-ls-apply`
- `makefiles/brand-s3-ec2/Makefile.mk`
  - `brand-s3-ls-apply`
- `makefiles/diaper-category-ec2/Makefile.mk`
  - 相关 LS apply 目标

新增迁移脚本：

```text
scripts/label_studio/run_migrations.py
```

用于替代 `ls-migrate` 里的内联：

```python
from django.core.management import call_command
call_command("migrate", "--no-color")
```

### 3. 检查所有 Makefile.mk

再次搜索：

```text
python -c
python3 -c
python - <<
python3 - <<
exec(open
call_command(
printf '.*python
```

目标：

- `Makefile` / `makefiles/**/*.mk` 中不再出现 Python 代码片段。
- 允许保留正常脚本调用，例如：

```makefile
$(VENV_BIN)/python scripts/xxx.py ...
```

因为这只是执行独立脚本，不是在 Makefile 里写 Python 逻辑。

### 4. 文档同步

更新：

- `README.md`
- `makefiles/label-workflow/README.md`
- `设计.md`
- 本计划文件

说明：

- dry-run 不再输出大段 Python 代码。
- EC2 下载 S3 图片逻辑改为远端脚本执行。
- Makefile 中只保留脚本调用，不再嵌入 Python 代码片段。

### 5. 验证

执行：

```bash
make -n 3-label-s3-workflow-ec2-train COUNTRY=GH DATA_VERSION=v2026-09-20 LABEL_SET=general LABELS=kleesoft_purple,allround_purple S3_EC2_DOWNLOAD_MODE=auto EC2_HOST=18.209.241.0 EC2_USER=ec2-user EC2_KEY=~/.ssh/smdp-yolo-gpu-key.pem EC2_BASE_MODEL=yolo26m.pt EC2_TRAIN_EPOCHS=100 EC2_TRAIN_IMGSZ=960 EC2_TRAIN_BATCH=-1 EC2_TRAIN_DEVICE=0 EC2_RUN_NAME=yolo26m_img960_e100 EC2_EXECUTE=0
```

确认输出中不再包含大段 Python 源码。

执行：

```bash
PYTHONPATH=/Users/guobiao/PRO/me/yoloExample .venv/bin/python -m pylint \
  scripts/ec2/s3_workflow.py \
  scripts/ec2/download_s3_manifest_images.py \
  scripts/label_studio/run_migrations.py

PYTHONPATH=/Users/guobiao/PRO/me/yoloExample .venv/bin/python tests/test_brand_s3_ec2_workflow.py
```

并用搜索确认 `Makefile` / `makefiles/**/*.mk` 中没有内联 Python 片段。

## 执行结果（2026-09-20）

已完成清理与验证：

1. **EC2 下载 S3 图片的 dry-run 不再打印大段 Python 源码**
   - 新增远端脚本：`scripts/ec2/download_s3_manifest_images.py`。
   - `scripts/ec2/s3_workflow.py` 的 `download-images` 阶段改为先通过 `rsync` 上传该脚本，再执行：

```bash
python3 scripts/ec2/download_s3_manifest_images.py \
  --manifest <remote_ec2_image_manifest.json> \
  --dataset-root <remote_dataset_root> \
  --download-mode <auto|public|boto3> \
  --public-base-url <url>
```

   - `train` 阶段内部触发下载图片时也复用同一脚本命令，不再拼接 `python -c '<大段代码>'`。

2. **Makefile.mk 内联 Python 已清理**
   - `makefiles/common/Makefile.mk`：
     - `ls-migrate` 改为执行 `scripts/label_studio/run_migrations.py`。
     - `ls-apply` 改为 `label-studio shell < scripts/label_studio/apply_import.py`。
     - `ls-clone-annotated-project` 改为 `label-studio shell < scripts/label_studio/clone_annotated_project.py`。
   - `makefiles/label-workflow/Makefile.mk`：
     - `label-ls-apply` / `label-s3-ls-apply` 改为 stdin 执行独立脚本。
   - `makefiles/local-dir/Makefile.mk`：
     - `local-dir-ls-apply` 改为 stdin 执行独立脚本。
   - `makefiles/brand-s3-ec2/Makefile.mk`：
     - `brand-s3-ls-apply` 改为 stdin 执行独立脚本。
   - `makefiles/diaper-category-ec2/Makefile.mk`：
     - `diaper-ls-apply` 改为 stdin 执行独立脚本。

3. **检查结果**
   - 已搜索 `Makefile` 和 `makefiles/**/*.mk`，确认不再出现：
     - `python -c`
     - `python - <<`
     - `exec(open(...))`
     - `call_command(...)`
     - `printf '...Python...' | label-studio shell`
   - 保留了正常的脚本调用，例如 `$(VENV_BIN)/python scripts/xxx.py ...`，这类调用不属于在 Makefile 中内联 Python 代码。

4. **dry-run 输出验证**
   - 已执行用户同款 `make -n 3-label-s3-workflow-ec2-train ... EC2_EXECUTE=0`。
   - 输出现在只显示短命令和脚本路径，不再打印大段 Python 源码。

5. **测试与静态检查**
   - `pylint`：`10.00/10`
   - `tests/test_brand_s3_ec2_workflow.py`：`17 tests OK`
   - `node --check web-console/server.js`：通过
