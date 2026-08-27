# Softcare 参考图合并计划

## 目标

将 `datasets/multibrand/visual_prompts/softcare/` 下的 47 张 Softcare 参考图合并到一张总览图片中，方便一次性查看参考图质量。

## 输入

- 目录：`datasets/multibrand/visual_prompts/softcare/`
- 图片数量：47 张
- 图片格式：PNG 等常见图片格式

## 输出

建议输出到：

```text
outputs/visual_prompts/softcare_reference_grid.png
```

## 实施方式

1. 使用 Python + Pillow 读取目录下图片。
2. 按文件名排序，保证输出顺序稳定。
3. 每张图缩放到统一缩略图尺寸，例如 220x220，保持比例并居中白底填充。
4. 按网格合并，47 张图建议 7 列 x 7 行。
5. 在每张缩略图下方标注序号和文件名简写，方便回看原始图片。
6. 保存合并图到 `outputs/visual_prompts/softcare_reference_grid.png`。

## 验证

- 确认输出图片文件存在。
- 用 Pillow 打开输出图片验证尺寸和格式正常。
- 不修改原始参考图。
