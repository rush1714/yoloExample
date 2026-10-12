import os
import requests

key = os.environ.get("LITELLM_MASTER_KEY", "sk-1234")
resp = requests.get("http://127.0.0.1:4000/models", headers={"Authorization": f"Bearer {key}"}, timeout=5)
print("LiteLLM /models:", resp.status_code, resp.text[:400])

resp_ollama = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
print("Ollama /api/tags:", resp_ollama.status_code, resp_ollama.text[:400])
