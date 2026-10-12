import requests

resp = requests.get("https://ai-exchange.sunda.com/models", headers={"X-API-Key": "ext-5558234175a044b5b7a7"}, timeout=10)
print("GET /models:", resp.status_code, resp.text[:300])

resp2 = requests.get("https://ai-exchange.sunda.com/api/v1/exchange/models", headers={"X-API-Key": "ext-5558234175a044b5b7a7"}, timeout=10)
print("GET /api/v1/exchange/models:", resp2.status_code, resp2.text[:300])
