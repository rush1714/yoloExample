import urllib.request
import json
import ssl

ctx = ssl.create_default_context()

url = "https://minutes.qwennote.cn/mcp"

req = urllib.request.Request(
    url,
    data=json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0.0"}
        }
    }).encode('utf-8'),
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req, context=ctx) as resp:
        print("Status:", resp.status)
        print("Headers:", dict(resp.headers))
        print("Body:", resp.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code, e.reason)
    print("Headers:", dict(e.headers))
    print("Body:", e.read().decode('utf-8'))
except Exception as e:
    print("Error:", e)
