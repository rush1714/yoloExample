import json
from pathlib import Path

for p in sorted(Path(".label-studio-data/export").glob("project-*.json")):
    if p.name.endswith("-info.json"): continue
    try:
        data = json.loads(p.read_text())
        annotated = sum(1 for t in data if t.get("annotations") and len(t["annotations"]) > 0)
        boxes = 0
        for t in data:
            for a in t.get("annotations", []):
                for r in a.get("result", []):
                    if r.get("type") == "rectanglelabels":
                        boxes += 1
        print(f"{p.name}: total tasks={len(data)}, annotated tasks={annotated}, total boxes={boxes}")
    except Exception as e:
        print(f"{p.name}: error {e}")
