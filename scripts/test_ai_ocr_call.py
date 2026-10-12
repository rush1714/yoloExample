import urllib.request
import json
import base64
from pathlib import Path

sample_img = next(Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/llm/images").glob("*.webp"))
print("Sample image:", sample_img.name)

b64_data = base64.b64encode(sample_img.read_bytes()).decode("utf-8")

payload = {
    "image": {
        "imageBase64": b64_data,
        "mimeType": "image/webp"
    },
    "prompt": "请识别图中的洗衣粉陈列商品。我们需要识别并区分两个品牌：1. allround_purple（紫色包装，品牌名为All Round / Allround）；2. kleesoft_purple（紫色包装，品牌名为Kleesoft）。请给出图中所有目标商品的数量、品牌分类以及大致位置（按 0-100 归一化坐标 [ymin, xmin, ymax, xmax]），以 JSON 返回：{ 'total_count': int, 'allround_purple_count': int, 'kleesoft_purple_count': int, 'detections': [{'brand': str, 'box_2d': [ymin, xmin, ymax, xmax]}] }。只返回 JSON，不要解释。"
}

req = urllib.request.Request(
    "https://ai-exchange.sunda.com/api/v1/exchange/ocr",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "X-API-Key": "ext-5558234175a044b5b7a7",
        "Content-Type": "application/json"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("Status:", res.get("status"))
        print("Parsed JSON:", res.get("data", {}).get("parsedJson"))
        print("Raw Content:", res.get("data", {}).get("content"))
except Exception as e:
    print("Error calling ai-ocr:", e)
