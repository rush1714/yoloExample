import json
import csv
from pathlib import Path

predict_dir = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100")
summary_csv = predict_dir / "summary.csv"

pred_rows = []
with open(summary_csv, 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        pred_rows.append(r)

# Map predict images by hash
# local_image: /home/ec2-user/yoloExample/outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100/images/000001_082891b3bb197aa89d7fdcc1fa140dba.webp
# source: https://uat-smdp4cust-cdn.globaltradecoo.com/CustomerComponent/082891b3bb197aa89d7fdcc1fa140dba.webp
pred_by_hash = {}
for r in pred_rows:
    p = Path(r['local_image'])
    img_hash = p.stem.split('_')[-1]
    pred_by_hash[img_hash] = r

print(f"Total predict images: {len(pred_rows)}, unique hashes: {len(pred_by_hash)}")

# Now let's check various annotation sources
# 1. label_studio_export.json in v2026-09-20
ls_20 = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")
if ls_20.exists():
    data = json.loads(ls_20.read_text())
    ls_hashes = {}
    for t in data:
        img_url = t.get("data", {}).get("image", "")
        # extract hash from filename
        fn = Path(img_url.split("?d=")[-1] if "?d=" in img_url else img_url).name
        # hash is usually after rowXXXXX_ or before ext
        # e.g. row00073_082891b3bb197aa89d7fdcc1fa140dba.webp -> 082891b3bb197aa89d7fdcc1fa140dba
        parts = fn.split('.')[0].split('_')
        h = parts[-1]
        has_annos = len(t.get("annotations", [])) > 0
        boxes = []
        for a in t.get("annotations", []):
            for res in a.get("result", []):
                if res.get("type") == "rectanglelabels":
                    boxes.append(res)
        ls_hashes[h] = {"task": t, "has_annos": has_annos, "box_count": len(boxes), "filename": fn}

    overlap = set(pred_by_hash.keys()).intersection(set(ls_hashes.keys()))
    overlap_annotated = set(pred_by_hash.keys()).intersection(set(h for h, v in ls_hashes.items() if v['has_annos']))
    overlap_with_boxes = set(pred_by_hash.keys()).intersection(set(h for h, v in ls_hashes.items() if v['box_count'] > 0))
    print(f"LS 2026-09-20 total tasks: {len(ls_hashes)}")
    print(f"  Overlap with predict: {len(overlap)}")
    print(f"  Overlap with annotations: {len(overlap_annotated)}")
    print(f"  Overlap with boxes > 0: {len(overlap_with_boxes)}")

# Check project 29 in database
import subprocess
try:
    res = subprocess.check_output([
        "psql", "-U", "guobiao", "-d", "labelstudio", "-t", "-A", "-c",
        "SELECT count(*) FROM task_completion tc JOIN task t ON t.id = tc.task_id WHERE t.project_id = 29;"
    ]).decode().strip()
    print("Database project 29 completions count:", res)
except Exception as e:
    print("DB query failed:", e)

