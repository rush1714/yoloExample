from pathlib import Path

f = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100/source_image_uris.txt")
lines = [l.strip() for l in f.read_text().splitlines() if l.strip()]

print(f"Total lines in source_image_uris.txt: {len(lines)}")
print(f"Unique lines: {len(set(lines))}")

# Check filenames (basename of url)
basenames = [Path(u).name for u in lines]
print(f"Unique basenames: {len(set(basenames))}")

# How many are in 350 dataset?
m_path = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/s3/metadata/ec2_image_manifest.csv")
import csv
with open(m_path) as mf:
    reader = csv.DictReader(mf)
    manifest_urls = [r['s3_uri'] for r in reader]

print(f"Manifest urls count: {len(manifest_urls)}")

# Check against local images in datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/raw/images
raw_imgs = list(Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/raw/images").glob("*"))
raw_hashes = set(p.stem.split('_')[-1] for p in raw_imgs)
print(f"Raw images count: {len(raw_imgs)}, unique hashes: {len(raw_hashes)}")

pred_hashes = set(Path(u).stem.split('_')[-1] for u in lines)
print(f"Predict hashes in raw images: {len(pred_hashes.intersection(raw_hashes))} / {len(pred_hashes)}")

