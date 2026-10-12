import csv
import json
from pathlib import Path

predict_dir = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100")
summary_csv = predict_dir / "summary.csv"

rows = list(csv.DictReader(open(summary_csv)))
print(f"Total rows: {len(rows)}")

# check errors
errors = [r for r in rows if r['error']]
print(f"Errors count: {len(errors)}")

# check row index counts
by_row = {}
for r in rows:
    by_row.setdefault(r['row_index'], []).append(r)

print(f"Total distinct row_index: {len(by_row)}")

# In the 379 rows, check total_count distribution
counts = [int(r['total_count']) for r in rows]
from collections import Counter
print("Predicted counts distribution:", Counter(counts))

# Check how many images have detections:
has_det = [r for r in rows if int(r['total_count']) > 0]
print(f"Images with at least 1 detection: {len(has_det)}")
print(f"Images with 0 detection: {len(rows) - len(has_det)}")

