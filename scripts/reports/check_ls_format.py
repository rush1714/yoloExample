import json
from pathlib import Path

export_json_path = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")

with open(export_json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Find first task with annotations
annotated_task = next(t for t in data if t.get("annotations"))
print("--- Annotated Task Sample ---")
print("Data:", json.dumps(annotated_task.get("data"), indent=2, ensure_ascii=False))
print("Annotations:", json.dumps(annotated_task.get("annotations")[:1], indent=2, ensure_ascii=False))

# Check predictions if any
pred_task = next((t for t in data if t.get("predictions")), None)
if pred_task:
    print("--- Pred Task Sample ---")
    print("Predictions:", json.dumps(pred_task.get("predictions")[:1], indent=2, ensure_ascii=False))
else:
    print("No predictions found in this export, only annotations.")
