import urllib.request
import ssl

ctx = ssl.create_default_context()
req = urllib.request.Request(
    "https://minutes.qwennote.cn/mcp",
    headers={"Accept": "text/event-stream"}
)

try:
    with urllib.request.urlopen(req, context=ctx) as resp:
        print("Status:", resp.status)
        print("Headers:", dict(resp.headers))
        print("Read 200 bytes:", resp.read(200))
except Exception as e:
    print("Error:", e)
