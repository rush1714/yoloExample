import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from pptx import Presentation

deck_path = Path("/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-29_YOLO端侧识别方案及大模型对比_COO汇报.pptx")
prs = Presentation(deck_path)

print(f"Total slides in new deck: {len(prs.slides)}")

all_typefaces = set()
with zipfile.ZipFile(deck_path, 'r') as z:
    for name in z.namelist():
        if name.startswith('ppt/slides/slide') and name.endswith('.xml'):
            root = ET.fromstring(z.read(name))
            for elem in root.iter():
                tf = elem.attrib.get('typeface')
                if tf:
                    all_typefaces.add(tf)

print("Typeface values across XMLs:", all_typefaces)

for s_idx, slide in enumerate(prs.slides, start=1):
    rounded_shapes = []
    for sh_idx, shape in enumerate(slide.shapes):
        if hasattr(shape, "adjustments") and len(shape.adjustments) > 0:
            rounded_shapes.append((shape.name, round(shape.adjustments[0], 5)))
    print(f"Slide {s_idx}: {len(rounded_shapes)} rounded shapes -> adjustments: {set(v for _, v in rounded_shapes)}")

