"""Print node summary of all N8N workflow JSON files."""
import json, glob, os, sys

patterns = sys.argv[1:] if len(sys.argv) > 1 else ['src/n8n/workflows/*.json']
files = []
for p in patterns:
    files.extend(glob.glob(p))

if not files:
    # try with spaces
    import glob as g
    files = g.glob('src/n8n/workflows/*.json')

for fpath in sorted(files):
    with open(fpath, encoding='utf-8') as f:
        w = json.load(f)
    wname = w.get('name', os.path.basename(fpath))
    wid = w.get('id', '?')
    nodes = w.get('nodes', [])
    conns = w.get('connections', {})
    print(f"\n=== {fpath} ===")
    print(f"Name: {wname}  ID: {wid}  nodes: {len(nodes)}")
    for n in nodes:
        oe = n.get('onError', '-')
        ntype = n['type'].split('.')[-1]
        pos = n.get('position', [0,0])
        print(f"  [{n['name']}] {ntype}  onError={oe}  pos={pos}")
    print("Connections:")
    for src, data in conns.items():
        for targets in data.get('main', []):
            for t in targets:
                print(f"  {src} -> {t['node']}")
