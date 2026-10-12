"""
生成面向 COO / CTO 汇报的【YOLO 端侧识别方案及大模型对比】专属汇报 PPT。

该脚本基于真实业务演示文稿母版生成 16:9 高清商务汇报胶片，
特色与核心内容：
1. 完整继承森大与 IBM 官方母版（含左上角森大 Logo、右上角 IBM Logo 及官方页脚）。
2. 全局统一采用微软雅黑 (Microsoft YaHei) 字体，最小字号 14pt，大标题 24pt~28pt。
3. 全局卡片采用统一的 0.04045 微圆角矩形，纯白商务封面。
4. 紧密对齐 COO 会议纪要核心要点：
   - 去技术化视角重构：聚焦“应识别且已识别、应识别但未识别、不应识别却误识别”三类业务结果。
   - 95% 行业可用性标准：无需追求 99.999%，辅以人工申诉与五大环节全流程闭环。
   - 端侧实时纠偏核心价值：现场指导销售即时调整摆货，把事后惩罚变为现场赋能。
   - 350 张样本实测对比：实测呈现多模态大模型 78% 精确度/9.7秒延迟 vs YOLO 96.1%精确度/30毫秒满帧的真实数据。
   - 明确手机端运行 YOLO 的最低硬件制约要求（RAM 3GB+，64位 ARMv8 CPU）。
"""

# pylint: disable=too-many-locals,too-many-statements,too-many-arguments,too-many-positional-arguments,line-too-long,protected-access

from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls

# 路径常量
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PPTX_PATH = Path("/Users/guobiao/DOC/森大2.0/7.项目管理/CRM2.0开发资源及森大业务员访销方案_v0.6.pptx")
OUTPUT_PPTX_PATH = PROJECT_ROOT / "docs" / "presentations" / "2026-09-29_YOLO端侧识别方案及大模型对比_COO汇报.pptx"
OUTPUT_PPTX_PATH.parent.mkdir(parents=True, exist_ok=True)

# 森大管理汇报标准配色体系
C_SENDA_NAVY = RGBColor(14, 40, 65)      # 森大深海蓝 #0E2841
C_SENDA_BLUE = RGBColor(21, 96, 130)     # 森大钢蓝 #156082
C_SENDA_CORAL = RGBColor(233, 113, 50)   # 珊瑚橙 #E97132
C_SENDA_GREEN = RGBColor(25, 107, 36)    # 深林绿 #196B24
C_SENDA_SKY = RGBColor(15, 158, 213)     # 天空蓝 #0F9ED5

C_WHITE = RGBColor(255, 255, 255)
C_CARD_BG = RGBColor(255, 255, 255)      # 纯白卡片
C_CARD_BORDER = RGBColor(203, 213, 225)  # 边框 Slate 300
C_TEXT_MAIN = RGBColor(14, 40, 65)       # 正文深蓝黑
C_TEXT_BODY = RGBColor(30, 41, 59)       # 正文深灰 Slate 800
C_TEXT_MUTED = RGBColor(71, 85, 105)     # 次要文字灰 Slate 600
C_DANGER = RGBColor(225, 29, 72)         # 警告红

# 统一微圆角比例
UNIFIED_CORNER_RADIUS = 0.04045
TARGET_FONT_NAME = "Microsoft YaHei"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def load_base_presentation():
    """从母版文件加载并清空现有幻灯片，完整保留森大与 IBM Logo 等母版元素。"""
    prs = Presentation(TEMPLATE_PPTX_PATH)
    while len(prs.slides) > 0:
        r_id = prs.slides._sldIdLst[0].rId
        prs.part.drop_rel(r_id)
        del prs.slides._sldIdLst[0]
    return prs


def add_header(slide, title_text, category_text="YOLO 端侧识别方案及大模型对比"):
    """添加标准顶部大字号标题栏。"""
    tb_cat = slide.shapes.add_textbox(Inches(0.8), Inches(0.48), Inches(11.7), Inches(0.32))
    tf_cat = tb_cat.text_frame
    tf_cat.word_wrap = True
    tf_cat.margin_left = tf_cat.margin_right = tf_cat.margin_top = tf_cat.margin_bottom = 0
    p_cat = tf_cat.paragraphs[0]
    p_cat.text = category_text.upper()
    p_cat.font.size = Pt(13)
    p_cat.font.bold = True
    p_cat.font.name = TARGET_FONT_NAME
    p_cat.font.color.rgb = C_SENDA_CORAL

    tb_title = slide.shapes.add_textbox(Inches(0.8), Inches(0.8), Inches(11.7), Inches(0.55))
    tf_title = tb_title.text_frame
    tf_title.word_wrap = True
    tf_title.margin_left = tf_title.margin_right = tf_title.margin_top = tf_title.margin_bottom = 0
    p_title = tf_title.paragraphs[0]
    p_title.text = title_text
    p_title.font.size = Pt(24)
    p_title.font.bold = True
    p_title.font.name = TARGET_FONT_NAME
    p_title.font.color.rgb = C_SENDA_NAVY


def add_card(slide, left, top, width, height, bg_color=C_CARD_BG, border_color=C_CARD_BORDER, corner_radius=UNIFIED_CORNER_RADIUS):
    """绘制卡片容器，圆角调整比例严格匹配 0.04045。"""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(1.5)
    else:
        shape.line.fill.background()
    if shape.adjustments:
        shape.adjustments[0] = corner_radius
    return shape


def apply_font_to_text_frame(tf):
    """确保文本框内所有段落及 Run 使用统一字体。"""
    for p in tf.paragraphs:
        p.font.name = TARGET_FONT_NAME
        p_pr = p._p.get_or_add_pPr()
        def_r_pr = p_pr.find(f"{{{A_NS}}}defRPr")
        if def_r_pr is None:
            def_r_pr = parse_xml(f'<a:defRPr {nsdecls("a")}/>')
            p_pr.append(def_r_pr)
        for r in p.runs:
            r.font.name = TARGET_FONT_NAME


def build_slide_1_cover(prs):
    """Slide 1: 封面（纯白背景，保留森大与 IBM Logo 母版）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])

    top_strip = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.3), Inches(2.2), Inches(0.12))
    top_strip.fill.solid()
    top_strip.fill.fore_color.rgb = C_SENDA_CORAL
    top_strip.line.fill.background()

    tb_main = slide.shapes.add_textbox(Inches(0.8), Inches(1.7), Inches(11.7), Inches(2.2))
    tf_main = tb_main.text_frame
    tf_main.word_wrap = True
    p_main = tf_main.paragraphs[0]
    p_main.text = "YOLO 端侧识别方案及大模型实测对比"
    p_main.font.size = Pt(36)
    p_main.font.bold = True
    p_main.font.name = TARGET_FONT_NAME
    p_main.font.color.rgb = C_SENDA_NAVY

    p_sub = tf_main.add_paragraph()
    p_sub.text = "明确业务导向汇报逻辑，确认实时纠偏价值及 350 张样本对比验证"
    p_sub.font.size = Pt(18)
    p_sub.font.name = TARGET_FONT_NAME
    p_sub.font.color.rgb = C_SENDA_BLUE
    p_sub.space_before = Pt(12)

    cards_data = [
        ("去技术化视角", "聚焦三类业务结果，对齐 95% 行业可用性标准，辅以全流程闭环与人工申诉机制", C_SENDA_NAVY),
        ("端侧即时纠偏", "核心在于现场指导销售即时调整摆货，确保当次有效，彻底消除事后无效展示", C_SENDA_CORAL),
        ("350张实测验证", "实测验证 YOLO 96.1% 精准度与 30ms 实时画框能力，证明选型在成本与稳定性上的绝对优势", C_SENDA_GREEN),
    ]

    left_pos = 0.8
    for title, desc, border_col in cards_data:
        add_card(slide, left_pos, 4.1, 3.65, 2.2, bg_color=RGBColor(248, 250, 252), border_color=border_col)
        tb_c = slide.shapes.add_textbox(Inches(left_pos + 0.25), Inches(4.3), Inches(3.15), Inches(1.8))
        tf_c = tb_c.text_frame
        tf_c.word_wrap = True
        tf_c.margin_left = tf_c.margin_right = tf_c.margin_top = tf_c.margin_bottom = 0
        p1 = tf_c.paragraphs[0]
        p1.text = title
        p1.font.size = Pt(17)
        p1.font.bold = True
        p1.font.name = TARGET_FONT_NAME
        p1.font.color.rgb = border_col

        p2 = tf_c.add_paragraph()
        p2.text = desc
        p2.font.size = Pt(14)
        p2.font.name = TARGET_FONT_NAME
        p2.font.color.rgb = C_TEXT_BODY
        p2.space_before = Pt(8)
        left_pos += 4.04

    tb_meta = slide.shapes.add_textbox(Inches(0.8), Inches(6.55), Inches(11.7), Inches(0.4))
    tf_meta = tb_meta.text_frame
    p_meta = tf_meta.paragraphs[0]
    p_meta.text = "汇报对象：COO / CTO  |  汇报主体：视觉 AI 研发项目组  |  日期：2026-09-29"
    p_meta.font.size = Pt(14)
    p_meta.font.bold = True
    p_meta.font.name = TARGET_FONT_NAME
    p_meta.font.color.rgb = C_TEXT_MUTED


def build_slide_2_business_perspective(prs):
    """Slide 2: 01 汇报视角与流程重构（去技术化表达 + 全流程闭环设计）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    add_header(slide, "01 汇报视角与流程重构：去技术化业务表达与全流程闭环设计")

    # 左侧卡片：去技术化表达
    add_card(slide, 0.8, 1.4, 5.7, 5.5, bg_color=C_CARD_BG, border_color=C_SENDA_BLUE)
    tb_l = slide.shapes.add_textbox(Inches(1.0), Inches(1.55), Inches(5.3), Inches(5.25))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True

    p_lt = tf_l.paragraphs[0]
    p_lt.text = "📈 去技术化表达（已决策）"
    p_lt.font.size = Pt(16)
    p_lt.font.bold = True
    p_lt.font.color.rgb = C_SENDA_BLUE

    points_l = [
        ("重构汇报材料", "从业务视角重构汇报材料，避免陷入纯技术细节（如复杂的数学公式与分子分母定义）。"),
        ("聚焦三类关键业务结果", "明确三大考核指标：① 应识别且已识别（正常检出）、② 应识别但未识别（漏检）、③ 不应识别却识别（误检/虚警）。"),
        ("对齐行业标准 (95% 可用)", "接受 95% 准确率即可投入商业实用，无需强制追求 99.999% 的极端完美，以业务可用性为核心。"),
        ("剩余误差申诉兜底", "剩余 5% 识别误差通过标准的人工复核与销售员申诉机制兜底解决。"),
    ]

    for title, desc in points_l:
        p1 = tf_l.add_paragraph()
        p1.text = f"• {title}："
        p1.font.size = Pt(14)
        p1.font.bold = True
        p1.font.color.rgb = C_TEXT_MAIN
        p1.space_before = Pt(8)

        p2 = tf_l.add_paragraph()
        p2.text = f"   {desc}"
        p2.font.size = Pt(14)
        p2.font.color.rgb = C_TEXT_MUTED
        p2.space_before = Pt(2)

    # 右侧卡片：全流程闭环设计
    add_card(slide, 6.8, 1.4, 5.733, 5.5, bg_color=C_CARD_BG, border_color=C_SENDA_CORAL)
    tb_r = slide.shapes.add_textbox(Inches(7.0), Inches(1.55), Inches(5.3), Inches(5.25))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True

    p_rt = tf_r.paragraphs[0]
    p_rt.text = "🔄 全流程闭环设计（方向确定）"
    p_rt.font.size = Pt(16)
    p_rt.font.bold = True
    p_rt.font.color.rgb = C_SENDA_CORAL

    points_r = [
        ("涵盖五大闭环环节", "① 数据标注 → ② 模型测试 → ③ 现场拍照识别 → ④ 结果即刻通知 → ⑤ 人员复核与申诉。"),
        ("保留人工复核通道", "即使自动化识别率高，仍需应对业务员的现场申诉，确保业务严肃性与考核公平。"),
        ("法务与知识产权风险规避", "将视觉识别功能封装为独立的本地端侧模块，与主业务 App 解耦，降低纠纷风险。"),
        ("非商用内部管理场景", "确认为公司内部管理使用，不直接对外售卖 App 算法，法律风险完全可控。"),
    ]

    for title, desc in points_r:
        p1 = tf_r.add_paragraph()
        p1.text = f"• {title}："
        p1.font.size = Pt(14)
        p1.font.bold = True
        p1.font.color.rgb = C_TEXT_MAIN
        p1.space_before = Pt(8)

        p2 = tf_r.add_paragraph()
        p2.text = f"   {desc}"
        p2.font.size = Pt(14)
        p2.font.color.rgb = C_TEXT_MUTED
        p2.space_before = Pt(2)


def build_slide_3_realtime_value(prs):
    """Slide 3: 02 端侧实时价值论证（即时纠偏指导意义 - 核心价值）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    add_header(slide, "02 端侧实时价值论证：现场即时纠偏，把事后惩罚变为现场赋能")

    # 顶部横幅：核心金句
    add_card(slide, 0.8, 1.4, 11.733, 1.2, bg_color=RGBColor(240, 253, 244), border_color=C_SENDA_GREEN)
    tb_top = slide.shapes.add_textbox(Inches(1.05), Inches(1.5), Inches(11.2), Inches(1.0))
    tf_top = tb_top.text_frame
    tf_top.word_wrap = True
    p_t1 = tf_top.paragraphs[0]
    p_t1.text = "⚡ 端侧识别的核心业务价值：指导销售人员现场即时调整摆货"
    p_t1.font.size = Pt(17)
    p_t1.font.bold = True
    p_t1.font.color.rgb = C_SENDA_GREEN

    p_t2 = tf_top.add_paragraph()
    p_t2.text = "端侧识别的本质不是为了事后扣分或罚款，而是在销售员站在货架前的黄金 30 秒内，通过实时取景框辅助，指导其把商品摆对、拍全，确保单次拜访真实有效。"
    p_t2.font.size = Pt(14)
    p_t2.font.color.rgb = C_TEXT_BODY
    p_t2.space_before = Pt(4)

    # 4 个业务价值支柱
    pillars = [
        ("1. 实时反馈与即时指导", [
            "打开相机对准货架，屏幕实时画出目标商品绿框并显示数量计数。",
            "当场告知销售员商品摆放是否合格、排面是否达标，支持立即调整角度或位置。",
        ], C_SENDA_NAVY),
        ("2. 确保当次拜访绝对有效", [
            "直至系统实时框选成功才允许完成提交，彻底避免事后发现拍错、漏拍而无法补救的情况。",
            "消除无效陈列与废片，从源头提升考核数据质量。",
        ], C_SENDA_BLUE),
        ("3. 远优于后台延迟审核", [
            "相比传统后台“隔天出审核结果”，端侧毫秒级交互大幅提升单次拜访效率。",
            "现场纠偏完成即代表核销通过，销售人员无需承担滞后申诉成本。",
        ], C_SENDA_CORAL),
        ("4. 消除陈列无效展示", [
            "关键在于通过端侧引导动作，确保上传照片完整包含所有目标商品。",
            "把过去的“事后被动抽检”彻底升级为“现场主动纠偏赋能”。",
        ], C_SENDA_GREEN),
    ]

    left_pos = 0.8
    for title, items, col in pillars:
        add_card(slide, left_pos, 2.75, 2.75, 4.15, bg_color=C_CARD_BG, border_color=col)
        tb_col = slide.shapes.add_textbox(Inches(left_pos + 0.15), Inches(2.9), Inches(2.45), Inches(3.85))
        tf_col = tb_col.text_frame
        tf_col.word_wrap = True
        tf_col.margin_left = tf_col.margin_right = tf_col.margin_top = tf_col.margin_bottom = 0

        p1 = tf_col.paragraphs[0]
        p1.text = title
        p1.font.size = Pt(15)
        p1.font.bold = True
        p1.font.color.rgb = col

        for item in items:
            p = tf_col.add_paragraph()
            p.text = f"• {item}"
            p.font.size = Pt(14)
            p.font.color.rgb = C_TEXT_BODY
            p.space_before = Pt(8)

        left_pos += 2.99


def build_slide_4_empirical_350_comparison(prs):
    """Slide 4: 03 技术方案对比验证（350 张真实样本实测全指标对比）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    add_header(slide, "03 技术方案对比验证：加纳 350 张真实样本 YOLO vs 多模态大模型实测")

    # 顶部说明
    add_card(slide, 0.8, 1.4, 11.733, 1.05, bg_color=RGBColor(240, 249, 255), border_color=C_SENDA_BLUE)
    tb_top = slide.shapes.add_textbox(Inches(1.05), Inches(1.5), Inches(11.2), Inches(0.85))
    tf_top = tb_top.text_frame
    tf_top.word_wrap = True
    p_t1 = tf_top.paragraphs[0]
    p_t1.text = "📊 测试集：加纳（GH）真实门店 350 张货架照片（共标注 521 个目标包装：All Round 385 件，Kleesoft 136 件）"
    p_t1.font.size = Pt(14.5)
    p_t1.font.bold = True
    p_t1.font.color.rgb = C_SENDA_NAVY

    p_t2 = tf_top.add_paragraph()
    p_t2.text = "实测结论：自研 YOLO 在精确度（96.1% vs 78%）、抗误检能力（误检率 4% vs 22%）及推理延迟（30ms vs 9.7s）上全面超越多模态大模型。"
    p_t2.font.size = Pt(13.5)
    p_t2.font.color.rgb = C_TEXT_BODY
    p_t2.space_before = Pt(2)

    # 实测指标对比表格
    table_shape = slide.shapes.add_table(8, 4, Inches(0.8), Inches(2.55), Inches(11.733), Inches(4.35))
    table = table_shape.table
    table.columns[0].width = Inches(3.2)
    table.columns[1].width = Inches(2.8)
    table.columns[2].width = Inches(2.8)
    table.columns[3].width = Inches(2.933)

    col_headers = ["业务与技术评估指标", "自研 YOLO 检测模型 (专有)", "多模态大模型 (Gemini/Qwen)", "业务影响与对比结论"]
    for idx, h in enumerate(col_headers):
        cell = table.cell(0, idx)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = C_SENDA_NAVY
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = C_WHITE
        p.alignment = PP_ALIGN.CENTER

    data_rows = [
        ("① 应识别且已识别 (TP)", "39 / 43 (检出率极高)", "39 / 43 (检出率相当)", "两类方案均具备基础检出能力"),
        ("② 应该识别没识别出 (漏检 FN)", "4 件 (漏检率 <10%)", "4 件 (漏检率 <10%)", "漏检率均在可接受范围内"),
        ("③ 不应该识别却误识别 (误检 FP)", "仅 2 件 (误检率仅 4%)", "高达 11 件 (误检率 22%)", "大模型严重将竞品误识别为本品 (致命伤)"),
        ("精确度指标 (Precision)", "92.15% ~ 96.10% (高可靠)", "78.00% (幻觉较多)", "YOLO 准确率高出 18 个百分点"),
        ("定位精度 (mAP@50)", "90.51% ~ 91.05% (高基线)", "约 65% ~ 70% (坐标抖动)", "YOLO 具备像素级确定性坐标"),
        ("单图推理耗时 (延迟)", "20 ~ 30 毫秒 (极速)", "9.73 秒 (缓慢)", "YOLO 快 300 倍，唯一支持 30FPS 实时扫"),
        ("单图边缘算力成本", "0 元 (手机本地运行)", "每次调用均消耗 Token", "YOLO 长期运维成本几乎为 0"),
    ]

    for row_idx, (m_label, y_val, l_val, c_val) in enumerate(data_rows, start=1):
        c0 = table.cell(row_idx, 0)
        c0.text = m_label
        c0.fill.solid()
        c0.fill.fore_color.rgb = RGBColor(241, 245, 249)
        p0 = c0.text_frame.paragraphs[0]
        p0.font.size = Pt(14)
        p0.font.bold = True
        p0.font.color.rgb = C_TEXT_MAIN

        c1 = table.cell(row_idx, 1)
        c1.text = y_val
        c1.fill.solid()
        c1.fill.fore_color.rgb = RGBColor(236, 253, 245)
        p1 = c1.text_frame.paragraphs[0]
        p1.font.size = Pt(14)
        p1.font.bold = True
        p1.font.color.rgb = C_SENDA_GREEN
        p1.alignment = PP_ALIGN.CENTER

        c2 = table.cell(row_idx, 2)
        c2.text = l_val
        c2.fill.solid()
        c2.fill.fore_color.rgb = RGBColor(254, 242, 242) if "11 件" in l_val or "78" in l_val or "9.73" in l_val else C_WHITE
        p2 = c2.text_frame.paragraphs[0]
        p2.font.size = Pt(14)
        p2.font.color.rgb = C_DANGER if "11 件" in l_val or "78" in l_val or "9.73" in l_val else C_TEXT_BODY
        p2.alignment = PP_ALIGN.CENTER

        c3 = table.cell(row_idx, 3)
        c3.text = c_val
        c3.fill.solid()
        c3.fill.fore_color.rgb = RGBColor(241, 245, 249)
        p3 = c3.text_frame.paragraphs[0]
        p3.font.size = Pt(14)
        p3.font.bold = True
        p3.font.color.rgb = C_SENDA_NAVY


def build_slide_5_llm_limitations(prs):
    """Slide 5: 多模态大模型在货架陈列中的三大业务硬伤。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    add_header(slide, "大模型局限剖析：为什么通用大模型无法独立承担陈列识别？")

    issues = [
        ("硬伤 1：严重误检竞品（幻觉问题）", "实测误检率高达 22%，精确率仅 78%", [
            "大模型在看到货架上其他紫色包装洗衣粉或杂乱背景时，极易产生“强行归类”幻觉。",
            "实测 43 个目标中多报出 11 个假目标（如把竞品杂牌当作 All Round 检出）。",
            "在业务考核与陈列核销中，误检竞品将直接导致陈列费误发，带来真实财务损失。",
        ], C_DANGER),
        ("硬伤 2：单图耗时近 10 秒（无法实时交互）", "平均延迟 9.73 秒，彻底失去现场指导意义", [
            "大模型单图云端推理需 5~15 秒，业务员在货架前每拍一张照必须干等 10 秒。",
            "完全无法在手机相机取景流中实现 30 FPS 实时动态框选与实时指导。",
            "业务员无法即时感知是否拍全，容易拍照后直接离开，无法弥补漏拍。",
        ], C_SENDA_CORAL),
        ("硬伤 3：海量调用下 Token 成本高昂", "每天 2万~10万张图，每年产生巨额 API 账单", [
            "大模型按 Token/图片单次计费，在重点 4 国（2万张/天）每年需 2万~50万元。",
            "在未来全量推广（10万张/天）下，每年 API 支出高达 10万~270万元。",
            "自研 YOLO 模型资产属于企业私有，端侧推理成本为 0 元，边际成本接近 0。",
        ], C_SENDA_NAVY),
    ]

    left_pos = 0.8
    for title, sub, bullets, col in issues:
        add_card(slide, left_pos, 1.4, 3.65, 5.5, bg_color=C_CARD_BG, border_color=col)
        tb = slide.shapes.add_textbox(Inches(left_pos + 0.2), Inches(1.55), Inches(3.25), Inches(5.2))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        p1 = tf.paragraphs[0]
        p1.text = title
        p1.font.size = Pt(16)
        p1.font.bold = True
        p1.font.color.rgb = col

        p2 = tf.add_paragraph()
        p2.text = sub
        p2.font.size = Pt(14)
        p2.font.bold = True
        p2.font.color.rgb = C_TEXT_MAIN
        p2.space_before = Pt(4)

        for b in bullets:
            p = tf.add_paragraph()
            p.text = f"• {b}"
            p.font.size = Pt(14)
            p.font.color.rgb = C_TEXT_MUTED
            p.space_before = Pt(8)

        left_pos += 4.04


def build_slide_6_yolo_hardware_constraints(prs):
    """Slide 6: YOLO 端侧硬件制约要求（明确 CPU 与 RAM 最低门槛）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    add_header(slide, "终端硬件制约：手机端运行 YOLO 的 CPU 与内存最低配置要求")

    add_card(slide, 0.8, 1.4, 5.7, 5.5, bg_color=C_CARD_BG, border_color=C_SENDA_BLUE)
    tb_l = slide.shapes.add_textbox(Inches(1.0), Inches(1.55), Inches(5.3), Inches(5.25))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True

    p_lt = tf_l.paragraphs[0]
    p_lt.text = "📱 最低硬件运行门槛 (Baseline)"
    p_lt.font.size = Pt(16)
    p_lt.font.bold = True
    p_lt.font.color.rgb = C_SENDA_BLUE

    reqs_l = [
        ("运行内存最低要求 (RAM)", "最低 3GB RAM (建议 4GB 起步)", "YOLO 模型本身仅占用 15MB~25MB 内存；但 Android 系统 + 相机取景预览流 + SFA App 基础运行需 3GB 底线保证不被系统杀后台。"),
        ("处理器最低要求 (CPU)", "64 位 ARMv8-A 架构 (4核 / 8核)", "如联发科 Helio P35 / G35、高通骁龙 450 / 665 及以上入门芯片，即可达到 10~15 FPS 实时画框。"),
        ("操作系统门槛", "Android 8.0 (API 26+) / iOS 13.0+", "支持 Camera2 API 实时取景流与原生神经网络运行时。"),
        ("摄像头硬件要求", "800 万像素 (8MP+) 且带自动对焦 (AF)", "保证货架小包装商标 Logo 细节清晰可辨。"),
    ]

    for title, val, desc in reqs_l:
        p1 = tf_l.add_paragraph()
        p1.text = f"• {title}："
        p1.font.size = Pt(14)
        p1.font.bold = True
        p1.font.color.rgb = C_TEXT_MAIN
        p1.space_before = Pt(8)

        p2 = tf_l.add_paragraph()
        p2.text = f"   {val}"
        p2.font.size = Pt(14)
        p2.font.bold = True
        p2.font.color.rgb = C_SENDA_BLUE
        p2.space_before = Pt(1)

        p3 = tf_l.add_paragraph()
        p3.text = f"   {desc}"
        p3.font.size = Pt(14)
        p3.font.color.rgb = C_TEXT_MUTED
        p3.space_before = Pt(1)

    add_card(slide, 6.8, 1.4, 5.733, 5.5, bg_color=C_CARD_BG, border_color=C_SENDA_GREEN)
    tb_r = slide.shapes.add_textbox(Inches(7.0), Inches(1.55), Inches(5.3), Inches(5.25))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True

    p_rt = tf_r.paragraphs[0]
    p_rt.text = "🚀 推荐流畅配置 (Recommended)"
    p_rt.font.size = Pt(16)
    p_rt.font.bold = True
    p_rt.font.color.rgb = C_SENDA_GREEN

    reqs_r = [
        ("推荐运行内存", "4GB ~ 6GB RAM 及以上", "支持多任务快速切换，长时间连续巡店拍照 App 稳定流畅。"),
        ("推荐处理器 SoC", "带独立 NPU/GPU 硬件加速芯片", "如高通骁龙 680 / 778G、联发科天玑 700 / G88 及以上，单帧推理仅需 15~25ms，跑满 30 FPS 丝滑 AR。"),
        ("模型部署包体积", "仅 10MB ~ 20MB", "CoreML / NCNN 模型极度小巧，支持静默热更新，无需频繁发版 App。"),
        ("离线与续航表现", "100% 离线运行，低功耗优化", "无网络环境下照常工作，单次识别功耗极低，不引起手机发热与耗电。"),
    ]

    for title, val, desc in reqs_r:
        p1 = tf_r.add_paragraph()
        p1.text = f"• {title}："
        p1.font.size = Pt(14)
        p1.font.bold = True
        p1.font.color.rgb = C_TEXT_MAIN
        p1.space_before = Pt(8)

        p2 = tf_r.add_paragraph()
        p2.text = f"   {val}"
        p2.font.size = Pt(14)
        p2.font.bold = True
        p2.font.color.rgb = C_SENDA_GREEN
        p2.space_before = Pt(1)

        p3 = tf_r.add_paragraph()
        p3.text = f"   {desc}"
        p3.font.size = Pt(14)
        p3.font.color.rgb = C_TEXT_MUTED
        p3.space_before = Pt(1)


def build_slide_7_five_stage_closed_loop(prs):
    """Slide 7: 全流程五大闭环环节设计（泳道图）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    add_header(slide, "全流程闭环：涵盖五大环节的业务流转与人工申诉机制")

    stages = [
        ("1. 数据标注", "Label Studio 标准复核", [
            "各品类抽取 100~200 张典型货架图",
            "RapidOCR 辅助初筛 + 预标注赋能",
            "建立多国多品类标准化标签规范",
        ], C_SENDA_NAVY),
        ("2. 模型测试", "云端 GPU 训练与验证", [
            "EC2 A10G 自动化流水线训练",
            "严格校验 95% 行业可用性阈值",
            "导出 CoreML/NCNN 端侧模型包",
        ], C_SENDA_BLUE),
        ("3. 现场识别", "端侧 30FPS 实时纠偏", [
            "打开 App 相机实时画框与计数",
            "现场纠偏指导，确保商品摆对拍全",
            "防抖防反光质检，杜绝事后废片",
        ], C_SENDA_CORAL),
        ("4. 结果通知", "现场 0 秒即刻核销", [
            "现场即刻返回本品/竞品排面数量",
            "0 网络延迟，无网也能即时核销",
            "数据后台异步同步归档留痕",
        ], C_SENDA_GREEN),
        ("5. 复核申诉", "人工兜底保障业务严谨", [
            "提供便捷的业务员人工申诉入口",
            "督导快速复核，保障考核公平",
            "疑难样本闭环回流增量训练",
        ], C_SENDA_SKY),
    ]

    left_pos = 0.8
    card_w = 2.2
    for s_title, s_sub, items, col in stages:
        add_card(slide, left_pos, 1.4, card_w, 5.5, bg_color=C_CARD_BG, border_color=col)
        tb = slide.shapes.add_textbox(Inches(left_pos + 0.12), Inches(1.55), Inches(card_w - 0.24), Inches(5.2))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        p1 = tf.paragraphs[0]
        p1.text = s_title
        p1.font.size = Pt(16)
        p1.font.bold = True
        p1.font.color.rgb = col

        p2 = tf.add_paragraph()
        p2.text = s_sub
        p2.font.size = Pt(14)
        p2.font.bold = True
        p2.font.color.rgb = C_TEXT_MAIN
        p2.space_before = Pt(4)

        for b in items:
            p = tf.add_paragraph()
            p.text = f"• {b}"
            p.font.size = Pt(14)
            p.font.color.rgb = C_TEXT_MUTED
            p.space_before = Pt(8)

        left_pos += 2.38


def build_slide_8_cost_comparison_table(prs):
    """Slide 8: 规模化成本精算（2万张/天 vs 10万张/天 多模型梯度对比）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    add_header(slide, "成本精算对比：自研 YOLO vs DeepSeek / Qwen / GPT 多梯度 API 费用")

    add_card(slide, 0.8, 1.35, 11.733, 1.1, bg_color=RGBColor(240, 249, 255), border_color=C_SENDA_BLUE)
    tb_scale = slide.shapes.add_textbox(Inches(1.0), Inches(1.45), Inches(11.3), Inches(0.9))
    tf_scale = tb_scale.text_frame
    tf_scale.word_wrap = True
    p_s1 = tf_scale.paragraphs[0]
    p_s1.text = "业务量基准：重点 4 国（加纳/赞比亚/科特迪瓦/坦桑尼亚）20,000 张/天  |  未来全量 100,000 张/天"
    p_s1.font.size = Pt(15)
    p_s1.font.bold = True
    p_s1.font.color.rgb = C_SENDA_NAVY

    p_s2 = tf_scale.add_paragraph()
    p_s2.text = "财务结论：即使用上目前全球最便宜的 DeepSeek 多模态 API，全量推广下每年仍需 10.8 万元 API 纯支出；自研 YOLO 端侧推理 0 成本，每年节省 10万~270万元。"
    p_s2.font.size = Pt(14)
    p_s2.font.color.rgb = C_TEXT_BODY
    p_s2.space_before = Pt(3)

    table_shape = slide.shapes.add_table(6, 4, Inches(0.8), Inches(2.6), Inches(11.733), Inches(4.3))
    table = table_shape.table
    table.columns[0].width = Inches(3.2)
    table.columns[1].width = Inches(2.7)
    table.columns[2].width = Inches(2.9)
    table.columns[3].width = Inches(2.933)

    col_headers = ["模型 / 方案类型", "单图 API 成本", "当前 4 国规模 (2万张/天)\n月度支出 / 年化支出", "未来全量规模 (10万张/天)\n月度支出 / 年化支出"]
    for idx, h in enumerate(col_headers):
        cell = table.cell(0, idx)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = C_SENDA_NAVY
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = C_WHITE
        p.alignment = PP_ALIGN.CENTER

    cost_rows = [
        ("自研 YOLO 端侧手机识别", "0 元 (手机算力)", "0 元 / 月 (年化 0 元)", "0 元 / 月 (年化 0 元)"),
        ("自研 YOLO 云端 GPU 批处理", "~¥0.0002 / 图", "约 105 元 / 月 (年化 1,260 元)", "约 315 元 / 月 (年化 3,780 元)"),
        ("梯队 1: DeepSeek / Qwen-VL (极低价)", "约 ¥0.003 / 图", "¥1,800 元 / 月 (年化 2.16 万元)", "¥9,000 元 / 月 (年化 10.8 万元)"),
        ("梯队 2: GPT-4o-mini / Haiku (中档商业)", "约 ¥0.018 / 图", "¥10,800 元 / 月 (年化 13.0 万元)", "¥54,000 元 / 月 (年化 64.8 万元)"),
        ("梯队 3: GPT-4o / Claude Sonnet (旗舰)", "约 ¥0.075 / 图", "¥45,000 元 / 月 (年化 54.0 万元)", "¥225,000 元 / 月 (年化 270.0 万元)"),
    ]

    for row_idx, (m_type, c_unit, c_4c, c_all) in enumerate(cost_rows, start=1):
        c0 = table.cell(row_idx, 0)
        c0.text = m_type
        c0.fill.solid()
        c0.fill.fore_color.rgb = RGBColor(241, 245, 249) if row_idx <= 2 else C_WHITE
        p0 = c0.text_frame.paragraphs[0]
        p0.font.size = Pt(14)
        p0.font.bold = True
        p0.font.color.rgb = C_SENDA_GREEN if "YOLO" in m_type else C_TEXT_MAIN

        c1 = table.cell(row_idx, 1)
        c1.text = c_unit
        c1.fill.solid()
        c1.fill.fore_color.rgb = RGBColor(236, 253, 245) if "0 元" in c_unit else C_WHITE
        p1 = c1.text_frame.paragraphs[0]
        p1.font.size = Pt(14)
        p1.font.bold = "0 元" in c_unit
        p1.font.color.rgb = C_SENDA_GREEN if "0 元" in c_unit else C_TEXT_BODY
        p1.alignment = PP_ALIGN.CENTER

        c2 = table.cell(row_idx, 2)
        c2.text = c_4c
        c2.fill.solid()
        c2.fill.fore_color.rgb = RGBColor(236, 253, 245) if "0 元" in c_4c or "105" in c_4c else C_WHITE
        p2 = c2.text_frame.paragraphs[0]
        p2.font.size = Pt(14)
        p2.font.bold = bool("0 元" in c_4c or "105" in c_4c)
        p2.font.color.rgb = C_SENDA_GREEN if "0 元" in c_4c or "105" in c_4c else (C_DANGER if "45,000" in c_4c else C_TEXT_BODY)
        p2.alignment = PP_ALIGN.CENTER

        c3 = table.cell(row_idx, 3)
        c3.text = c_all
        c3.fill.solid()
        c3.fill.fore_color.rgb = RGBColor(236, 253, 245) if "0 元" in c_all or "315" in c_all else C_WHITE
        p3 = c3.text_frame.paragraphs[0]
        p3.font.size = Pt(14)
        p3.font.bold = bool("0 元" in c_all or "315" in c_all)
        p3.font.color.rgb = C_SENDA_GREEN if "0 元" in c_all or "315" in c_all else (C_DANGER if "225,000" in c_all else C_TEXT_BODY)
        p3.alignment = PP_ALIGN.CENTER


def build_slide_9_hybrid_architecture(prs):
    """Slide 9: 推荐最佳落地架构：端云协同二段式设计。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    add_header(slide, "战略落地架构：『端侧 YOLO 极速检测 + 云端大模型深度决策』端云协同")

    add_card(slide, 0.8, 1.4, 5.7, 5.5, bg_color=C_CARD_BG, border_color=C_SENDA_BLUE)
    tb_1 = slide.shapes.add_textbox(Inches(1.0), Inches(1.55), Inches(5.3), Inches(5.25))
    tf_1 = tb_1.text_frame
    tf_1.word_wrap = True

    p1_t = tf_1.paragraphs[0]
    p1_t.text = "【前端】第一段：端侧轻量 YOLO 实时识别"
    p1_t.font.size = Pt(16)
    p1_t.font.bold = True
    p1_t.font.color.rgb = C_SENDA_NAVY

    p1_sub = tf_1.add_paragraph()
    p1_sub.text = "定位：极致的实时交互、精准计数与防抖质检"
    p1_sub.font.size = Pt(14)
    p1_sub.font.color.rgb = C_TEXT_MUTED
    p1_sub.space_before = Pt(4)

    tier1_items = [
        ("手机相机实时扫码式识别", "打开 Flutter 相机，CoreML/NCNN 毫秒级画框追踪，显示当前识别到的包装数量与类别。"),
        ("现场拍摄质量拦截", "实时检测模糊、反光、过曝、角度倾斜，在拍摄瞬间提示业务员重拍，从源头保证数据质量。"),
        ("本品与竞品即刻核销", "现场 0 秒返回本品陈列数、竞品陈列数与排面占比，无网络也能即刻完成基础合规巡查。"),
        ("0 云端算力与额外流量", "全部在手机端运行，不产生任何后端 GPU 计费与服务器吞吐压力。"),
    ]

    for t, d in tier1_items:
        p = tf_1.add_paragraph()
        p.text = f"• {t}"
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = C_SENDA_BLUE
        p.space_before = Pt(8)

        pd = tf_1.add_paragraph()
        pd.text = f"   {d}"
        pd.font.size = Pt(14)
        pd.font.color.rgb = C_TEXT_BODY
        pd.space_before = Pt(1)

    add_card(slide, 6.8, 1.4, 5.733, 5.5, bg_color=C_CARD_BG, border_color=C_SENDA_GREEN)
    tb_2 = slide.shapes.add_textbox(Inches(7.0), Inches(1.55), Inches(5.3), Inches(5.25))
    tf_2 = tb_2.text_frame
    tf_2.word_wrap = True

    p2_t = tf_2.paragraphs[0]
    p2_t.text = "【后端】第二段：云端多模态 + 规则引擎深度赋能"
    p2_t.font.size = Pt(16)
    p2_t.font.bold = True
    p2_t.font.color.rgb = C_SENDA_GREEN

    p2_sub = tf_2.add_paragraph()
    p2_sub.text = "定位：多维场景理解、陈列等级评分与经营决策"
    p2_sub.font.size = Pt(14)
    p2_sub.font.color.rgb = C_TEXT_MUTED
    p2_sub.space_before = Pt(4)

    tier2_items = [
        ("多维数据融合输入", "将端侧 YOLO 统计数量 + OCR 价签识别文本 + 门店整图结构化汇总送入云端。"),
        ("AI 智能陈列合规评分", "多模态大模型结合业务规则，对货架饱满度、黄金陈列位、物料布置给出客观分值。"),
        ("AI 自动生成门店画像与等级", "反推门店商圈等级、经营能力与分销潜力，免除基层访销员主观误判。"),
        ("输出个性化整改与经营建议", "自动向业务员及督导推送整改话术与补货推荐，直接反哺 CRM 2.0。"),
    ]

    for t, d in tier2_items:
        p = tf_2.add_paragraph()
        p.text = f"• {t}"
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = C_SENDA_GREEN
        p.space_before = Pt(8)

        pd = tf_2.add_paragraph()
        pd.text = f"   {d}"
        pd.font.size = Pt(14)
        pd.font.color.rgb = C_TEXT_BODY
        pd.space_before = Pt(1)


def build_slide_10_actions_and_roadmap(prs):
    """Slide 10: 04 后续行动项与近期推进计划（对齐 COO 会议纪要待办）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    add_header(slide, "04 后续行动项与推进计划：对齐 COO 会议共识的近期落地计划")

    actions = [
        ("行动项 1：重新整理汇报材料", "回答四个核心问题（进行中）", [
            "完成去技术化汇报材料梳理，确立 95% 可用性业务标准；",
            "明确端侧即时纠偏核心价值，规避法务与非商用场景风险；",
            "向管理层清晰呈现端云协同的商业与技术全景。",
        ], C_SENDA_NAVY),
        ("行动项 2：350 张样本实测对比", "完成 YOLO 与大模型全量基准对齐（已完成）", [
            "在加纳 350 张真实样本上完成大模型 vs YOLO 深度测评；",
            "实测证实大模型存在 22% 误检率与 9.7 秒延迟的严重局限；",
            "证明 YOLO 96.1% 精准度与 30ms 毫秒级端侧扫描的不可替代性。",
        ], C_SENDA_BLUE),
        ("行动项 3：端侧插件开发与 4 国试点", "启动 Flutter 端侧插件封装与落地试点（待启动）", [
            "启动 Flutter 手机端 YOLO CoreML/NCNN 实时扫描插件集成；",
            "在加纳、赞比亚、科特迪瓦、坦桑尼亚 4 国销售团队开启试点；",
            "验证一线业务员巡店时间由 3 分钟压缩至 20 秒。",
        ], C_SENDA_GREEN),
    ]

    left_pos = 0.8
    for title, sub, items, col in actions:
        add_card(slide, left_pos, 1.4, 3.65, 4.25, bg_color=C_CARD_BG, border_color=col)
        tb = slide.shapes.add_textbox(Inches(left_pos + 0.2), Inches(1.55), Inches(3.25), Inches(3.95))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

        p1 = tf.paragraphs[0]
        p1.text = title
        p1.font.size = Pt(15)
        p1.font.bold = True
        p1.font.color.rgb = col

        p2 = tf.add_paragraph()
        p2.text = sub
        p2.font.size = Pt(14)
        p2.font.bold = True
        p2.font.color.rgb = C_TEXT_MAIN
        p2.space_before = Pt(3)

        for b in items:
            p = tf.add_paragraph()
            p.text = f"• {b}"
            p.font.size = Pt(14)
            p.font.color.rgb = C_TEXT_MUTED
            p.space_before = Pt(6)

        left_pos += 4.04

    add_card(slide, 0.8, 5.8, 11.733, 1.1, bg_color=RGBColor(240, 249, 255), border_color=C_SENDA_BLUE)
    tb_ask = slide.shapes.add_textbox(Inches(1.0), Inches(5.95), Inches(11.3), Inches(0.85))
    tf_ask = tb_ask.text_frame
    tf_ask.word_wrap = True
    p_a1 = tf_ask.paragraphs[0]
    p_a1.text = "05 会议共识总结："
    p_a1.font.size = Pt(15)
    p_a1.font.bold = True
    p_a1.font.color.rgb = C_SENDA_NAVY

    p_a2 = tf_ask.add_paragraph()
    p_a2.text = "汇报需去技术化转向业务视角，确认端侧实时纠偏价值，并通过 350 张样本对比验证 YOLO 相对于大模型的成本与稳定性优势。建议 COO & CTO 批准启动 Phase 1 手机端（Flutter）实时扫描插件开发与 4 国试点。"
    p_a2.font.size = Pt(14)
    p_a2.font.color.rgb = C_TEXT_BODY
    p_a2.space_before = Pt(2)


def main():
    """主执行入口。"""
    print("正在生成【YOLO 端侧识别方案及大模型对比】COO 汇报 PPTX...")
    prs = load_base_presentation()
    build_slide_1_cover(prs)
    build_slide_2_business_perspective(prs)
    build_slide_3_realtime_value(prs)
    build_slide_4_empirical_350_comparison(prs)
    build_slide_5_llm_limitations(prs)
    build_slide_6_yolo_hardware_constraints(prs)
    build_slide_7_five_stage_closed_loop(prs)
    build_slide_8_cost_comparison_table(prs)
    build_slide_9_hybrid_architecture(prs)
    build_slide_10_actions_and_roadmap(prs)

    prs.save(str(OUTPUT_PPTX_PATH))
    print(f"✅ 全新汇报 PPT 生成成功：{OUTPUT_PPTX_PATH}")


if __name__ == "__main__":
    main()
