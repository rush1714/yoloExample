import csv
import json
from pathlib import Path

csv_path = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100/summary.csv")

rows = []
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

print(f"Total rows in summary.csv: {len(rows)}")

# Let's see the columns and first few rows
print("Columns:", list(rows[0].keys()) if rows else [])
print("Status counts:", set(r['status'] for r in rows))
total_detected = sum(int(r['total_count']) for r in rows if r['total_count'].isdigit())
print(f"Total objects detected across all {len(rows)} images: {total_detected}")

# check class counts
classes = {}
for r in rows:
    cc = r.get('class_counts', '{}')
    try:
        cd = json.loads(cc)
        for k, v in cd.items():
            classes[k] = classes.get(k, 0) + v
    except Exception:
        pass
print("Class counts detected:", classes)

# Let's inspect source URLs and filenames
# e.g. local_image or json_file
hashes = []
for r in rows:
    # local_image like 000001_082891b3bb197aa89d7fdcc1fa140dba.webp
    p = Path(r['local_image'])
    h = p.stem.split('_')[-1]
    hashes.append((h, p.name, r))

print("First 5 hashes:", [h[0] for h in hashes[:5]])

