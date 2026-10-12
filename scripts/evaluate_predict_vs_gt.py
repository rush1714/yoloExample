import json
import csv
from pathlib import Path

# Paths
predict_dir = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100")
summary_csv = predict_dir / "summary.csv"
ls_export_json = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")

# 1. Load Ground Truth from Label Studio Export
ls_data = json.loads(ls_export_json.read_text(encoding="utf-8"))
gt_by_hash = {}
for task in ls_data:
    img_url = task.get("data", {}).get("image", "")
    fn = Path(img_url.split("?d=")[-1] if "?d=" in img_url else img_url).name
    h = fn.split('.')[0].split('_')[-1]
    
    boxes = []
    for anno in task.get("annotations", []):
        for res in anno.get("result", []):
            if res.get("type") == "rectanglelabels":
                val = res.get("value", {})
                labels = val.get("rectanglelabels", [])
                for l in labels:
                    boxes.append({
                        "label": l,
                        # Label Studio stores percentages (0-100)
                        "x": val.get("x", 0),
                        "y": val.get("y", 0),
                        "w": val.get("width", 0),
                        "h": val.get("height", 0)
                    })
    gt_by_hash[h] = {
        "filename": fn,
        "boxes": boxes,
        "task_id": task.get("id")
    }

print(f"Total tasks in GT: {len(gt_by_hash)}")

# 2. Load Predictions from summary.csv & json/
preds_by_hash = {}
with open(summary_csv, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        img_name = Path(row['local_image']).name
        h = img_name.split('.')[0].split('_')[-1]
        
        # load json file
        jf = predict_dir / "json" / Path(row['json_file']).name
        boxes = []
        if jf.exists():
            jd = json.loads(jf.read_text(encoding='utf-8'))
            for det in jd.get("detections", []):
                # det format: {"class_id": 0, "class_name": "kleesoft_purple", "confidence": 0.8086, "xyxy": [x1, y1, x2, y2]}
                boxes.append(det)
        
        preds_by_hash[h] = {
            "row": row,
            "boxes": boxes,
            "total_count": int(row['total_count'])
        }

print(f"Total predict images: {len(preds_by_hash)}")

# 3. Match predict with GT
# Check box-level matching using count and IoU if possible
# Note: xyxy in predictions are absolute pixels or normalized?
# Let's inspect a prediction xyxy vs image width/height
sample_json = next((predict_dir / "json").glob("*.json"))
print("Sample prediction JSON:", sample_json.read_text()[:400])

