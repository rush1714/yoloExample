import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ref_path = Path("/Users/guobiao/DOC/森大2.0/7.项目管理/CRM2.0开发资源及森大业务员访销方案_v0.6.pptx")
with zipfile.ZipFile(ref_path, 'r') as z:
    for name in z.namelist():
        if 'theme' in name or 'slide1.xml' in name:
            print(f"Found: {name}")
            content = z.read(name)
            if 'theme' in name:
                root = ET.fromstring(content)
                print("--- Theme Color Elements ---")
                for elem in root.iter():
                    if 'srgbClr' in elem.tag or 'sysClr' in elem.tag:
                        val = elem.attrib.get('val') or elem.attrib.get('lastClr')
                        print(f"{elem.tag.split('}')[-1]}: {val}")
