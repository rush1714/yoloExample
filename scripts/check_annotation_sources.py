from pathlib import Path
import json
import csv

predict_dir = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100")
summary_csv = predict_dir / "summary.csv"

pred_hashes = set()
with open(summary_csv, 'r') as f:
    for row in csv.DictReader(f):
        img_name = Path(row['local_image']).name
        h = img_name.split('.')[0].split('_')[-1]
        pred_hashes.add(h)

print(f"Total predict hashes: {len(pred_hashes)}")

# Scan all txt label files in datasets
all_txt_labels = list(Path("datasets").glob("**/*.txt")) + list(Path("datasets_bak").glob("**/*.txt"))
txt_by_hash = {}
for p in all_txt_labels:
    if "metadata" in str(p) or "source" in str(p): continue
    h = p.stem.split('_')[-1]
    if len(h) == 32: # md5 hash
        txt_by_hash.setdefault(h, []).append(p)

print(f"Total md5 txt label hashes found: {len(txt_by_hash)}")
overlap_txt = pred_hashes.intersection(set(txt_by_hash.keys()))
print(f"Overlap with predict hashes: {len(overlap_txt)}")

# Group by parent directory of txt labels
parent_counts = {}
for h in overlap_txt:
    for p in txt_by_hash[h]:
        parent = str(p.parent)
        parent_counts[parent] = parent_counts.get(parent, 0) + 1
for k, v in sorted(parent_counts.items(), key=lambda x: -x[1])[:10]:
    print(f"  {k}: {v}")

