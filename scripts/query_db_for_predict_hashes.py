import subprocess
import json
import csv
from pathlib import Path

# Load predict hashes
summary_csv = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100/summary.csv")
pred_rows = []
with open(summary_csv) as f:
    pred_rows = list(csv.DictReader(f))

hash_to_row = {}
for r in pred_rows:
    p = Path(r['local_image']).name
    h = p.split('.')[0].split('_')[-1]
    hash_to_row[h] = r

print(f"Total predict hashes: {len(hash_to_row)}")

# Query database for all tasks across all projects
cmd = """
SELECT t.project_id, p.title, t.id, t.data, tc.id as completion_id, tc.result, tc.was_cancelled
FROM task t
JOIN project p ON p.id = t.project_id
LEFT JOIN task_completion tc ON tc.task_id = t.id
WHERE tc.id IS NOT NULL;
"""
res = subprocess.check_output(["psql", "-U", "guobiao", "-d", "labelstudio", "-t", "-A", "-c", cmd]).decode()

# analyze
lines = [l for l in res.split('\n') if l.strip()]
print(f"Total completions in database across all projects: {len(lines)}")

# check which predict hashes have completions
matched_completions = {}
for line in lines:
    parts = line.split('|')
    if len(parts) >= 6:
        pid = parts[0]
        title = parts[1]
        data_str = parts[3]
        result_str = parts[5]
        # find hash in data_str
        for h in hash_to_row:
            if h in data_str:
                matched_completions.setdefault(h, []).append({
                    "project_id": pid,
                    "project_title": title,
                    "result": result_str
                })

print(f"Predict hashes that have completions in DB: {len(matched_completions)} / {len(hash_to_row)}")

# group by project_id
proj_counts = {}
for h, comps in matched_completions.items():
    for c in comps:
        p_info = f"Project {c['project_id']}: {c['project_title']}"
        proj_counts[p_info] = proj_counts.get(p_info, 0) + 1

for k, v in sorted(proj_counts.items(), key=lambda x: -x[1]):
    print(f"  {k} -> {v} images")

