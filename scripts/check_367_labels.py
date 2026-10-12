import json
from pathlib import Path

for p in [
    Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json"),
    Path("datasets/GH/v2026-09-22/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")
]:
    if p.exists():
        data = json.loads(p.read_text())
        total_tasks = len(data)
        annotated_tasks = [t for t in data if t.get("annotations") and len(t["annotations"]) > 0]
        # check how many have actual results
        tasks_with_boxes = 0
        total_boxes = 0
        for t in annotated_tasks:
            boxes = []
            for a in t["annotations"]:
                for r in a.get("result", []):
                    if r.get("type") == "rectanglelabels":
                        boxes.append(r)
            if boxes:
                tasks_with_boxes += 1
                total_boxes += len(boxes)
        print(f"Path: {p}")
        print(f"  Total tasks: {total_tasks}, tasks with annotations: {len(annotated_tasks)}, tasks with boxes: {tasks_with_boxes}, total boxes: {total_boxes}")

