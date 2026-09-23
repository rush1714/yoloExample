# 门店陈列 AI 智能识别汇报方案 (v5.0 微软雅黑字体统一版)

## 沟通背景与调整说明

在用户对 `v4` 版本（统一圆角与布局）进行了手动微调与内容确认后，基于用户的最新修改成果递增生成全新的 **v5.0 演示文稿及决策文档**。

本次 v5.0 核心更新：
1. **基于用户手动修改的 v4 版本基准**：
   - 完整保留用户对 v4 演示文稿所做的全部文字、排版、圆角及版式微调，不改动任何位置与内容结构。
2. **全 PPT 字体全局统一为『微软雅黑 (Microsoft YaHei)』**：
   - 遍历全篇 10 页幻灯片中所有的文本框、标题、表格单元格、卡片描述及复合形状。
   - 深度写入 DrawingML 的 `<a:latin>`、`<a:ea>`（East Asian 中文字体）与 `<a:cs>` 节点，确保中文字体、英文字符与数字在 Windows、macOS 及 Office 投屏环境中均呈现标准的微软雅黑视觉效果。
3. **历史版本完整归档**：
   - 完整保留 `v1`、`v2`、`v3`、`v4` 历史文件，递增归档 `v5.0`。

---

## 核心业务与技术结论一览

1. **加纳实测指标突破 96%**：加纳真实门店 350 张复杂货架图实测取得 **96.10% Precision** 与 **90.51% mAP@50**，误检极低。
2. **终端 30FPS 实时扫码唯一解**：手机端直接打开相机实时画框计数，必须采用 YOLO（已导出 CoreML/ONNX），单次推理仅需 20~50ms，**服务器算力开销为 0 元**，100% 离线可用。
3. **多模态大模型价格梯度与年化降本**：
   - 即便采用全球价格最低的 DeepSeek 多模态 API（约 ¥0.003/图），在 2万~10万张/天规模下自研端侧方案每年仍可节省 **2.16 万元 至 270.0 万元** 纯 API 支出。
4. **终端运行最低硬件制约**：
   - RAM ≥ 3GB（建议 4G~6G），64 位 ARMv8 CPU（Helio P35 / 骁龙 450 起步），Android 8.0+ / iOS 13+，800万像素 AF 相机。
5. **推荐落地架构**：
   - 前端端侧轻量 YOLO 秒级画框核销 + 后端云端多模态大模型深度门店画像与经营建议。

---

## 产出物归档清单

- **PPTX 演示文稿 (v5.0 微软雅黑版)**：`/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v5.pptx`
- **PPTX 演示文稿 (v4.0 统一圆角版)**：`/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v4.pptx`
- **PPTX 演示文稿 (v3.0 深度定制版)**：`/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v3.pptx`
- **PPTX 演示文稿 (v2.0 版)**：`/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v2.pptx`
- **PPTX 演示文稿 (v1.0 原始版)**：`/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报.pptx`
- **生成脚本**：`/Users/guobiao/PRO/me/yoloExample/scripts/reports/generate_executive_deck_v5.py` (Pylint: 10.00/10)
- **第五版决策文档**：`/Users/guobiao/PRO/me/yoloExample/docs/plans/2026-09-23_5_plan_COO_CTO汇报方案_v5.md`
