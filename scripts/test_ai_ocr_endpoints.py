import urllib.request
import ssl

ctx = ssl.create_default_context()

endpoints = [
    "/api/v1/exchange/ocr",
    "/api/v1/ocr",
    "/api/v1/exchange/models",
    "/api/v1/models",
    "/models",
    "/health"
]

for ep in endpoints:
    url = f"https://ai-exchange.sunda.com{ep}"
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": "ext-5558234175a044b5b7a7"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            print(f"URL: {ep} -> Status {resp.status}, Content-Type: {resp.headers.get('Content-Type')}")
            print("  Body snippet:", resp.read(200).decode('utf-8', errors='ignore'))
    except urllib.error.HTTPError as e:
        print(f"URL: {ep} -> HTTPError {e.code} {e.reason}")
        print("  Body snippet:", e.read(200).decode('utf-8', errors='ignore'))
    except Exception as e:
        print(f"URL: {ep} -> Error: {e}")
