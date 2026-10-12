import json
import csv
from pathlib import Path

predict_dir = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100")
summary_csv = predict_dir / "summary.csv"

# Load predictions
preds = {}
with open(summary_csv, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        img_name = Path(row['local_image']).name
        # hash
        img_hash = img_name.split('.')[0].split('_')[-1]
        preds[img_hash] = {
            "image_name": img_name,
            "total_count": int(row['total_count']),
            "class_counts": json.loads(row['class_counts']),
            "json_file": row['json_file'],
            "source": row['source']
        }

print(f"Total predictions loaded: {len(preds)}")

# Check predictions detail (bounding boxes)
pred_boxes = {}
for h, p in preds.items():
    # read json file in predict_dir / json / ...
    jf = predict_dir / "json" / Path(p['json_file']).name
    if jf.exists():
        jd = json.loads(jf.read_text())
        # extract boxes
        # typical format: {"detections": [{"class_id": 0, "class_name": "allround_purple", "confidence": 0.85, "xyxy": [x1, y1, x2, y2]}]}
        boxes = []
        for det in jd.get("detections", []):
            boxes.append(det)
        pred_boxes[h] = boxes
    else:
        pred_boxes[h] = []

print(f"Total prediction boxes across all images: {sum(len(b) for b in pred_boxes.values())}")

# Now, where could the 367 manual annotations be?
# Let's inspect:
# 1. datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/labels (350 images)
# 2. datasets/GH/v2026-09-22/general_kleesoft_purple_allround_purple/labels (350 images)
# 3. What if there are 367 images in some Excel or CSV?
# Let's search all .xlsx or .csv files in the project or Downloads!

