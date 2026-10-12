import json
from pathlib import Path

export_path = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")
data = json.loads(export_path.read_text(encoding="utf-8"))

llm_dir = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/llm/images")
llm_images = set(f.name for f in llm_dir.glob("*") if f.is_file())

gt_by_img = {}
for task in data:
    img_path_str = task.get("data", {}).get("image", "")
    img_name = Path(img_path_str.split("?d=")[-1] if "?d=" in img_path_str else img_path_str).name
    annos = task.get("annotations", [])
    boxes = []
    for a in annos:
        for r in a.get("result", []):
            val = r.get("value", {})
            labels = val.get("rectanglelabels", [])
            x = val.get("x")
            y = val.get("y")
            w = val.get("width")
            h = val.get("height")
            for l in labels:
                boxes.append({"label": l, "x": x, "y": y, "width": w, "height": h})
    if boxes:
        gt_by_img[img_name] = boxes

print(f"Total images with manual annotations in LS export: {len(gt_by_img)}")
llm_with_gt = set(gt_by_img.keys()).intersection(llm_images)
print(f"Images in llm/images that have Ground Truth in LS export: {len(llm_with_gt)}")

# Count labels in this overlap
overlap_labels = {}
for img in llm_with_gt:
    for b in gt_by_img[img]:
        l = b["label"]
        overlap_labels[l] = overlap_labels.get(l, 0) + 1
print("Labels in llm_images overlap:", overlap_labels)
