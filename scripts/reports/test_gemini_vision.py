import base64
import json
import requests
from pathlib import Path

sample_img = list(Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/llm/images").glob("*.webp"))[3]
print("Testing vision on:", sample_img.name)

with open(sample_img, "rb") as f:
    b64_data = base64.b64encode(f.read()).decode("utf-8")

payload = {
    "model": "gemini-3.7-flash",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "请仔细观察这张货架陈列图片，识别并检测图中的两种目标洗衣粉包装商品：\n"
                        "1. 'allround_purple': All Round 紫色包装洗衣粉\n"
                        "2. 'kleesoft_purple': Kleesoft 紫色包装洗衣粉 (商标 Logo 为 KLEESOFT 或 Keesoft)\n\n"
                        "请返回 JSON 格式，严格包含：\n"
                        "{\n"
                        "  \"detections\": [\n"
                        "    {\n"
                        "      \"label\": \"allround_purple\" 或 \"kleesoft_purple\",\n"
                        "      \"box_2d\": [ymin, xmin, ymax, xmax], (0-1000 归一化整数坐标)\n"
                        "      \"confidence\": 0.0-1.0,\n"
                        "      \"description\": \"外观与位置说明\"\n"
                        "    }\n"
                        "  ],\n"
                        "  \"counts\": {\n"
                        "    \"allround_purple\": 数量,\n"
                        "    \"kleesoft_purple\": 数量,\n"
                        "    \"total\": 总数\n"
                        "  }\n"
                        "}\n"
                        "只返回合法的 JSON。"
                    )
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/webp;base64,{b64_data}"
                    }
                }
            ]
        }
    ],
    "response_format": {"type": "json_object"},
    "temperature": 0.1
}

headers = {
    "Authorization": "Bearer sk-guobiao12312123",
    "Content-Type": "application/json"
}

resp = requests.post("http://127.0.0.1:4000/v1/chat/completions", json=payload, headers=headers, timeout=60)
print("Status:", resp.status_code)
if resp.status_code == 200:
    content = resp.json()["choices"][0]["message"]["content"]
    print("Result:")
    print(content)
else:
    print("Error:", resp.text)
