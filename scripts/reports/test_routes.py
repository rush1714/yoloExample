import requests

for url in [
    "https://ai-exchange.sunda.com/api/v1/exchange/health",
    "http://ai-exchange.sunda.com/api/v1/exchange/health",
    "http://127.0.0.1:4000/health",
    "http://127.0.0.1:11434/api/tags"
]:
    try:
        r = requests.get(url, timeout=3)
        print(url, "->", r.status_code, r.text[:100])
    except Exception as e:
        print(url, "-> Error:", e)

