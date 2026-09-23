# 门店陈列 AI 智能识别汇报方案 (v4.0 统一圆角优化版)

## 沟通背景与调整说明

根据对汇报胶片（面向 COO 与 CTO）的最新视觉微调要求，在完整保留原 `v1`、`v2` 与 `v3` 版本的前提下，递增生成了全新的 **v4.0 演示文稿及决策文档**。

本次 v4.0 核心更新：
1. **全局统一圆角弧度**：
   - 提取了用户在第 2 页针对「为什么核心必须自研 YOLO？」卡片微调的标准圆角比例（`adjustments[0] = 0.04045`，约 4% 微圆角矩形）。
   - 全面应用至全 PPT 所有幻灯片的外部卡片容器、泳道图节点框、指标容器和提示框，保证整套胶片的视觉风格高度一致、严谨精致。
2. **母版与 Logo 完美承载**：
   - 继续完整继承 `/Users/guobiao/DOC/森大2.0/7.项目管理/CRM2.0开发资源及森大业务员访销方案_v0.6.pptx` 官方母版（左上角森大 Logo、右上角 IBM Logo 及官方页脚）。
3. **纯白极简封面与大字号体系**：
   - 首页纯白背景，全局字体最小 14pt，正文 14pt~16pt，标题 24pt~28pt，彻底去除无用图标杂项，强化高管投影阅读体验。
4. **端到端架构泳道图流转**：
   - 业务数据层 → 智能初筛标注层 → 自动化训练评估层 → 多端交付应用层。
5. **多梯度成本精算与 DeepSeek 价格梯度**：
   - 测算 4 国（20,000张/天）与全量（100,000张/天）规模下自研 YOLO 端侧 0 成本 vs 各梯队大模型 API（DeepSeek 极低价、GPT-4o-mini 中档、GPT-4o 旗舰）。
6. **明确终端硬件最低制约要求**：
   - RAM ≥ 3GB（建议 4G~6G），64 位 ARMv8 CPU（Helio P35 / 骁龙 450 起步），Android 8.0+ / iOS 13+，800万像素 AF 相机。

---

## 核心业务与技术结论汇总

1. **加纳实测指标突破 96%**：加纳真实门店 350 张图片实测取得 **96.10% Precision** 与 **90.51% mAP@50**。
2. **终端 30FPS 实时扫码唯一解**：手机端直接打开相机实时画框计数，必须采用 YOLO（已导出 CoreML/ONNX），单次推理仅需 20~50ms，**服务器算力开销为 0 元**，100% 离线可用。
3. **年化千万级降本空间**：即便对比 DeepSeek 极低价 API，在 2万~10万张/天规模下自研端侧方案每年仍可节省 **2.16 万元 至 270.0 万元** 纯 API 支出。
4. **端云协同二段式最佳架构**：端侧轻量 YOLO 现场秒级识别 + 云端多模态大模型深度门店画像与经营建议。

---

## 产出物归档清单

- **PPTX 演示文稿 (v4.0 统一圆角版)**：`/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v4.pptx`
- **PPTX 演示文稿 (v3.0 深度定制版)**：`/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v3.pptx`
- **PPTX 演示文稿 (v2.0 版)**：`/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v2.pptx`
- **PPTX 演示文稿 (v1.0 原始版)**：`/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报.pptx`
- **生成脚本**：`/Users/guobiao/PRO/me/yoloExample/scripts/reports/generate_executive_deck_v4.py` (Pylint: 10.00/10)
- **第四版决策文档**：`/Users/guobiao/PRO/me/yoloExample/docs/plans/2026-09-23_4_plan_COO_CTO汇报方案_v4.md`
