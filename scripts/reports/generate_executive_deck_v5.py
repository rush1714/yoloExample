"""
生成面向 COO / CTO 的 YOLO 门店陈列识别汇报 PPT (v5.0 字体统一升级版)。

该脚本以用户在 v4 版本上的最新修改成果为基准，
执行以下核心操作：
1. 完整保留用户对 v4 演示文稿的所有版式微调、内容改动、圆角弧度与排版结构。
2. 递归遍历全 PPT 所有幻灯片、文本框、表格单元格、复合形状及默认属性。
3. 将所有中文字体（East Asian）与西文字体（Latin）统一精确设置为『微软雅黑 (Microsoft YaHei)』。
4. 产出全新的 v5.0 演示文稿：2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v5.pptx。
"""

# pylint: disable=too-many-locals,too-many-statements,too-many-arguments,too-many-positional-arguments,line-too-long,protected-access

from pathlib import Path
from pptx import Presentation
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls

# 路径常量
PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_V4_PPTX_PATH = PROJECT_ROOT / "docs" / "presentations" / "2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v4.pptx"
OUTPUT_V5_PPTX_PATH = PROJECT_ROOT / "docs" / "presentations" / "2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v5.pptx"
OUTPUT_V5_PPTX_PATH.parent.mkdir(parents=True, exist_ok=True)

# 全局目标统一字体
TARGET_FONT_NAME = "Microsoft YaHei"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def set_font_on_rpr(r_pr_elem, font_name=TARGET_FONT_NAME):
    """
    在 DrawingML rPr (Run Properties) 节点上设置 latin, ea, cs 等全系字体属性。
    
    参数:
        r_pr_elem: DrawingML 的 rPr 或 defRPr XML 元素节点。
        font_name: 目标字体名称，默认为 Microsoft YaHei (微软雅黑)。
    """
    # 1. 查找或创建 latin (西文字体)
    latin = r_pr_elem.find(f"{{{A_NS}}}latin")
    if latin is None:
        latin = parse_xml(f'<a:latin {nsdecls("a")} typeface="{font_name}"/>')
        r_pr_elem.append(latin)
    else:
        latin.set("typeface", font_name)

    # 2. 查找或创建 ea (East Asian 中文字体，确保中文渲染为微软雅黑)
    ea_elem = r_pr_elem.find(f"{{{A_NS}}}ea")
    if ea_elem is None:
        ea_elem = parse_xml(f'<a:ea {nsdecls("a")} typeface="{font_name}"/>')
        r_pr_elem.append(ea_elem)
    else:
        ea_elem.set("typeface", font_name)

    # 3. 查找或创建 cs (Complex Script 字体)
    cs_elem = r_pr_elem.find(f"{{{A_NS}}}cs")
    if cs_elem is None:
        cs_elem = parse_xml(f'<a:cs {nsdecls("a")} typeface="{font_name}"/>')
        r_pr_elem.append(cs_elem)
    else:
        cs_elem.set("typeface", font_name)


def process_text_frame(text_frame, font_name=TARGET_FONT_NAME):
    """
    递归处理文本框对象中的段落与文本 Run，统一设置字体。
    
    参数:
        text_frame: pptx 的 TextFrame 对象。
        font_name: 目标字体名称。
    """
    for paragraph in text_frame.paragraphs:
        paragraph.font.name = font_name
        # 设置段落级别默认字符属性 (defRPr)
        p_pr = paragraph._p.get_or_add_pPr()
        def_r_pr = p_pr.find(f"{{{A_NS}}}defRPr")
        if def_r_pr is None:
            def_r_pr = parse_xml(f'<a:defRPr {nsdecls("a")}/>')
            p_pr.append(def_r_pr)
        set_font_on_rpr(def_r_pr, font_name)

        # 设置每个具体的文本运行块 (Run)
        for run in paragraph.runs:
            run.font.name = font_name
            r_pr = run._r.get_or_add_rPr()
            set_font_on_rpr(r_pr, font_name)


def process_shape(shape, font_name=TARGET_FONT_NAME):
    """
    递归处理幻灯片中的各种形状对象（包括常规形状、文本框、表格与复合分组形状）。
    
    参数:
        shape: pptx 的 Shape 对象。
        font_name: 目标字体名称。
    """
    if shape.has_text_frame:
        process_text_frame(shape.text_frame, font_name)
    elif shape.has_table:
        for row in shape.table.rows:
            for cell in row.cells:
                process_text_frame(cell.text_frame, font_name)
    elif shape.shape_type == 6:  # MSO_SHAPE_TYPE.GROUP
        for sub_shape in shape.shapes:
            process_shape(sub_shape, font_name)


def convert_presentation_fonts(input_pptx_path=INPUT_V4_PPTX_PATH, output_pptx_path=OUTPUT_V5_PPTX_PATH):
    """
    加载输入的 PPTX 文件，将全文字体统一转换为微软雅黑并另存为新版本文件。
    """
    print(f"正在加载输入演示文稿：{input_pptx_path}")
    prs = Presentation(str(input_pptx_path))

    slide_count = len(prs.slides)
    print(f"共检测到 {slide_count} 页幻灯片，开始统一字体为【{TARGET_FONT_NAME}】...")

    for idx, slide in enumerate(prs.slides, start=1):
        for shape in slide.shapes:
            process_shape(shape, TARGET_FONT_NAME)
        print(f"  - 第 {idx} 页字体转换完成")

    prs.save(str(output_pptx_path))
    print(f"✅ 全新 v5.0 演示文稿生成成功：{output_pptx_path}")


def main():
    """主执行入口。"""
    convert_presentation_fonts()


if __name__ == "__main__":
    main()
