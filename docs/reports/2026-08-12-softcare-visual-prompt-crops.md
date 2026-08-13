# 2026-08-12 Softcare visual prompt 参考图清洗记录

## 背景

`datasets/multibrand/visual_prompts/softcare/` 中的 Softcare 参考包装图将用于 YOLOE visual prompt 伪标注。原始图多数来自电商白底包装图，部分图片带透明背景、镜面倒影或较大的展示留白。为了让 YOLOE 参考框更接近“单个包装主体”，本次将目录内参考图统一转换为紧凑、干净的白底单包装 crop。

## 处理范围

- 输入目录：`datasets/multibrand/visual_prompts/softcare/`
- 处理图片数：44 张
- 输出方式：原地覆盖同名 PNG，便于现有 visual prompt 流程继续按原目录读取。
- 原图备份：`.tmp/visual_prompt_backups/softcare_20260812_180943/`
- 清洗清单：`.tmp/visual_prompt_backups/metadata/softcare_clean_manifest.csv`

## 处理方法

新增脚本：`scripts/data_import/clean_visual_prompt_crops.py`

脚本逻辑：

1. 使用 Pillow 将 RGBA/透明图合成到纯白背景，避免透明区域在预览或模型读取链路中呈现黑底。
2. 对 Softcare 已知带镜面倒影的电商产品图按文件名记录底部裁切线，去除不属于包装主体的倒影区域。
3. 使用 OpenCV/Pillow 基于“非纯白像素 + 轻微膨胀”的方式估计商品内容外接框。
4. 对检测框向外扩展少量 padding，保留包装边缘、阴影与白色包装区域。
5. 输出 RGB PNG，并增加很小白边，避免 visual prompt 在缩放时贴边截断。

## 验证结果

已完成以下验证：

```bash
PYLINTHOME=.tmp/pylint .venv/bin/python -m pylint --persistent=n scripts/data_import/clean_visual_prompt_crops.py
.venv/bin/python -m py_compile scripts/data_import/clean_visual_prompt_crops.py
.venv/bin/python - <<'PY'
from pathlib import Path
from PIL import Image
src = Path('datasets/multibrand/visual_prompts/softcare')
files = sorted(p for p in src.iterdir() if p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'})
print('image_count', len(files))
for path in files:
    with Image.open(path) as image:
        if image.mode != 'RGB':
            raise SystemExit(f'{path.name}: mode={image.mode}, expected RGB')
        if image.width <= 0 or image.height <= 0:
            raise SystemExit(f'{path.name}: invalid size {image.size}')
print('all_images_rgb_and_readable')
PY
```

结果：

- `pylint`：10.00/10
- `py_compile`：通过
- 图片可读性：44 张全部可读
- 图片模式：44 张全部为 RGB

## 结论

Softcare visual prompt 参考图已转换为紧凑、白底、单包装主体 crop。后续执行 YOLOE visual prompt 伪标注时，可继续使用原目录 `datasets/multibrand/visual_prompts/softcare/`，无需修改现有推理脚本参数。
