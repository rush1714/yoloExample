import json
from pathlib import Path

export_json_path = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")
llm_images_dir = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/llm/images")

with open(export_json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total tasks in label_studio_export.json: {len(data)}")

# Map filename to annotations
image_annotations = {}
class_counts = {}

for task in data:
    # get image filename
    img_path_str = task.get("data", {}).get("image", "")
    # could be local file or url
    filename = Path(img_path_str).name
    # if URL or query params
    if "?d=" in img_path_str:
        filename = Path(img_path_str.split("?d=")[-1]).name
    
    annotations = task.get("annotations", [])
    boxes = []
    for ann in annotations:
        for res in ann.get("result", []):
            val = res.get("value", {})
            labels = val.get("rectanglelabels", [])
            x = val.get("x")
            y = val.get("y")
            w = val.get("width")
            h = val.get("height")
            for label in labels:
                boxes.append({"label": label, "x": x, "y": y, "w": w, "h": h})
                class_counts[label] = class_counts.get(label, 0) + 1
    
    image_annotations[filename] = boxes

llm_images = sorted([p.name for p in llm_images_dir.glob("*.*") if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]])
print(f"Total images in llm/images: {len(llm_images)}")

matched_images = [img for img in llm_images if img in image_annotations]
print(f"Matched images in label studio export: {len(matched_images)}")
print(f"Total ground truth boxes by class in matched: {class_counts}")

# Check sample
sample_matched = matched_images[:5]
for img in sample_matched:
    print(f"Image: {img}, GT boxes: {len(image_annotations[img])}")
    for b in image_annotations[img]:
        print(f"   {b['label']}: x={b['x']:.1f}, y={b['y']:.1f}, w={b['w']:.1f}, h={b['h']:.1f}")

