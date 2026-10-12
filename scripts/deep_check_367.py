import json
import csv
from pathlib import Path

predict_dir = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100")
summary_csv = predict_dir / "summary.csv"

rows = []
with open(summary_csv) as f:
    rows = list(csv.DictReader(f))

print(f"Total rows in summary.csv: {len(rows)}")

# Check row indices and local_images
indices = []
for r in rows:
    # row index
    idx = int(r['row_index'])
    indices.append(idx)

print(f"Row indices range: min={min(indices)}, max={max(indices)}, count={len(indices)}")

# Check file names in json/
json_files = list((predict_dir / "json").glob("*.json"))
print(f"JSON files count: {len(json_files)}")

# Check file prefixes like 000001_... to 000379_...
prefixes = [int(p.name.split('_')[0]) for p in json_files if p.name.split('_')[0].isdigit()]
print(f"Prefixes range: min={min(prefixes)}, max={max(prefixes)}, total={len(prefixes)}")

# Are there missing numbers?
missing = set(range(1, max(prefixes) + 1)) - set(prefixes)
print("Missing prefix numbers:", missing)

# Now let's check label_studio_export.json in 2026-09-20
ls_path = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")
ls_data = json.loads(ls_path.read_text())
print(f"LS tasks: {len(ls_data)}")

# Map LS tasks by hash
ls_by_hash = {}
for t in ls_data:
    url = t.get("data", {}).get("image", "")
    fn = Path(url.split("?d=")[-1] if "?d=" in url else url).name
    h = fn.split('.')[0].split('_')[-1]
    ls_by_hash[h] = t

# For the 379 predict images, how many exist in LS tasks?
in_ls = sum(1 for r in rows if Path(r['local_image']).stem.split('_')[-1] in ls_by_hash)
print(f"Predict images found in LS tasks: {in_ls} / {len(rows)}")

# For those in LS, how many have:
# - annotations (completions)
# - was_cancelled
# - lead_time > 0
# - results
annotated_count = 0
cancelled_count = 0
boxes_count = 0
empty_annotated_count = 0

for r in rows:
    h = Path(r['local_image']).stem.split('_')[-1]
    if h in ls_by_hash:
        t = ls_by_hash[h]
        annos = t.get("annotations", [])
        if annos:
            annotated_count += 1
            res = annos[0].get("result", [])
            b = [x for x in res if x.get("type") == "rectanglelabels"]
            if b:
                boxes_count += 1
            else:
                empty_annotated_count += 1
            if annos[0].get("was_cancelled"):
                cancelled_count += 1

print(f"Of the 379 predict images:")
print(f"  Annotated in LS: {annotated_count}")
print(f"  With boxes > 0: {boxes_count}")
print(f"  Empty annotations (marked negative): {empty_annotated_count}")
print(f"  Cancelled: {cancelled_count}")

