import json
from pathlib import Path

base_dir = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple")
train_imgs = sorted([p.name for p in (base_dir / "images/train").glob("*.*")])
val_imgs = sorted([p.name for p in (base_dir / "images/val").glob("*.*")])
test_imgs = sorted([p.name for p in (base_dir / "images/test").glob("*.*")])

all_350 = train_imgs + val_imgs + test_imgs
print(f"Train: {len(train_imgs)}, Val: {len(val_imgs)}, Test: {len(test_imgs)}, Total: {len(all_350)}")

# Check ground truth in labels
gt_counts = {"allround_purple": 0, "kleesoft_purple": 0}
img_gt_labels = {}

for split in ["train", "val", "test"]:
    label_dir = base_dir / f"labels/{split}"
    img_dir = base_dir / f"images/{split}"
    for p in img_dir.glob("*.*"):
        txt_path = label_dir / f"{p.stem}.txt"
        boxes = []
        if txt_path.is_file():
            with open(txt_path, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        cls_id = int(parts[0])
                        cls_name = "kleesoft_purple" if cls_id == 0 else "allround_purple"
                        gt_counts[cls_name] += 1
                        boxes.append({"cls_id": cls_id, "cls_name": cls_name, "box": [float(x) for x in parts[1:5]]})
        img_gt_labels[p.name] = boxes

print(f"Ground truth total counts in 350 images: {gt_counts}")
print(f"Images with at least 1 GT target: {sum(1 for v in img_gt_labels.values() if len(v) > 0)}")
print(f"Images with 0 targets (negative background samples): {sum(1 for v in img_gt_labels.values() if len(v) == 0)}")

