from pptx import Presentation
from pathlib import Path

ref_path = Path("/Users/guobiao/DOC/森大2.0/7.项目管理/CRM2.0开发资源及森大业务员访销方案_v0.6.pptx")
prs = Presentation(ref_path)

# Remove existing slides
while len(prs.slides) > 0:
    rId = prs.slides._sldIdLst[0].rId
    prs.part.drop_rel(rId)
    del prs.slides._sldIdLst[0]

print(f"Remaining slides: {len(prs.slides)}")

# Add slide with Layout 2 (Cover)
slide1 = prs.slides.add_slide(prs.slide_layouts[2])
print(f"Slide 1 created with Layout 2 (Cover).")

# Add slide with Layout 0 (Title only)
slide2 = prs.slides.add_slide(prs.slide_layouts[0])
print(f"Slide 2 created with Layout 0 (Content).")

test_out = Path("/Users/guobiao/PRO/me/yoloExample/.tmp/test_out.pptx")
test_out.parent.mkdir(parents=True, exist_ok=True)
prs.save(test_out)
print(f"Saved test presentation to {test_out}")
