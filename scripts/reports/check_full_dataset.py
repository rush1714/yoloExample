import json
from pathlib import Path

export_json_path = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")
llm_images_dir = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/llm/images")

with open(export_json_path, "r", encoding="utf-8") as f:
    ls_data = json.load(f)

gt_annotations = {}
for task in ls_data:
    img_path_str = task.get("data", {}).get("image", "")
    filename = Path(img_path_str.split("?d=")[-1]).name
    annotations = task.get("annotations", [])
    boxes = []
    for ann in annotations:
        for res in ann.get("result", []):
            val = res.get("value", {})
            labels = val.get("rectanglelabels", [])
            for label in labels:
                boxes.append({
                    "label": label,
                    "x": round(val.get("x", 0), 2),
                    "y": round(val.get("y", 0), 2),
                    "width": round(val.get("width", 0), 2),
                    "height": round(val.get("height", 0), 2)
                })
    gt_annotations[filename] = boxes

all_imgs = sorted([p.name for p in llm_images_dir.glob("*.*") if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]])
print(f"Total images in llm/images: {len(all_imgs)}")
matched_count = sum(1 for img in all_imgs if img in gt_annotations)
print(f"Total matched in GT annotations: {matched_count}")

# Check boxes distribution
imgs_with_boxes = [img for img in all_imgs if len(gt_annotations.get(img, [])) > 0]
print(f"Images with at least 1 GT box: {len(imgs_with_boxes)}")
print(f"Images with 0 GT boxes (background): {len(all_imgs) - len(imgs_with_boxes)}")

