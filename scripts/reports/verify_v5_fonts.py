import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

v5_path = Path("/Users/guobiao/PRO/me/yoloExample/docs/presentations/2026-09-23_YOLO门店陈列识别_COO_CTO汇报_v5.pptx")

all_typefaces = set()
with zipfile.ZipFile(v5_path, 'r') as z:
    for name in z.namelist():
        if name.startswith('ppt/slides/slide') and name.endswith('.xml'):
            root = ET.fromstring(z.read(name))
            for elem in root.iter():
                tf = elem.attrib.get('typeface')
                if tf:
                    all_typefaces.add(tf)

print("Typeface values across all slide XMLs in v5:", all_typefaces)
