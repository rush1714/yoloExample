import os
from pathlib import Path

# search for directories containing around 367 files
for root, dirs, files in os.walk("."):
    if ".git" in root or ".venv" in root: continue
    if len(files) in [366, 367, 368]:
        print(f"Directory with {len(files)} files: {root}")

# search for json files or csv files that mention 367
for p in Path(".").glob("**/*"):
    if p.is_file() and p.suffix in ['.json', '.csv', '.txt', '.md']:
        if ".git" in str(p) or ".venv" in str(p): continue
        try:
            content = p.read_text(errors='ignore')
            if "367" in content:
                print(f"File mentioning '367': {p}")
        except Exception:
            pass
