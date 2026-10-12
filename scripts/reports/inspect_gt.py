import json
from pathlib import Path

export_path = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")
data = json.loads(export_path.read_text(encoding="utf-8"))

print(f"Total tasks in LS export: {len(data)}")

label_counts = {}
sample_task = None
for task in data:
    img_name = Path(task.get("data", {}).get("image", "")).name
    annos = task.get("annotations", [])
    if not sample_task and annos:
        sample_task = task
    for a in annos:
        for r in a.get("result", []):
            labels = r.get("value", {}).get("rectanglelabels", [])
            for l in labels:
                label_counts[l] = label_counts.get(l, 0) + 1

print("Ground Truth label counts in Label Studio:", label_counts)

# Let's also check images in images/train, val, test
img_dirs = [
    Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/images/train"),
    Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/images/val"),
    Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/images/test"),
]

dataset_imgs = []
for d in img_dirs:
    dataset_imgs.extend([f.name for f in d.glob("*") if f.is_file()])

print(f"Total images in 350 dataset: {len(dataset_imgs)}")
llm_imgs = [f.name for f in Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/llm/images").glob("*") if f.is_file()]
print(f"Total images in llm/images: {len(llm_imgs)}")
overlap = set(dataset_imgs).intersection(set(llm_imgs))
print(f"Overlap between 350 dataset and llm/images: {len(overlap)}")

