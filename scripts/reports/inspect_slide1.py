import zipfile
import xml.etree.ElementTree as ET

ref_path = "/Users/guobiao/DOC/森大2.0/7.项目管理/CRM2.0开发资源及森大业务员访销方案_v0.6.pptx"
with zipfile.ZipFile(ref_path, 'r') as z:
    content = z.read('ppt/slides/slide1.xml')
    root = ET.fromstring(content)
    for elem in root.iter():
        if elem.tag.endswith('sp'): # Shape
            name = elem.find('.//{*}cNvPr').attrib.get('name') if elem.find('.//{*}cNvPr') is not None else 'Unknown'
            print(f"Shape: {name}")
            for t in elem.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t'):
                print(f"   Text: {t.text}")
