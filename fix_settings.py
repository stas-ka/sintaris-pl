import json, urllib.request, os

n8n_base = "https://automata.dev2null.de/api/v1"
key = ""
with open(".env") as f:
    for line in f:
        if line.startswith("VPS_N8N_API_KEY="):
            key = line.strip().split("=",1)[1]

headers = {"X-N8N-API-KEY": key, "Content-Type": "application/json"}

req = urllib.request.Request(f"{n8n_base}/workflows/AjIB5izjiCunMcp6", headers=headers)
with urllib.request.urlopen(req) as r:
    wf = json.loads(r.read())

# Add execution save settings
wf["settings"]["saveDataSuccessExecution"] = "all"
wf["settings"]["saveDataErrorExecution"] = "all" 
wf["settings"]["saveManualExecutions"] = True
wf["settings"]["saveExecutionProgress"] = True

body = json.dumps(wf, ensure_ascii=False).encode()
req2 = urllib.request.Request(f"{n8n_base}/workflows/AjIB5izjiCunMcp6", 
    data=body, headers=headers, method="PUT")
try:
    with urllib.request.urlopen(req2) as r:
        res = json.loads(r.read())
        print("Settings:", res["settings"])
except Exception as e:
    print("Error:", e.read().decode() if hasattr(e,'read') else e)
