import re

with open("src/bot_web.py", "r", encoding="utf-8") as f:
    content = f.read()

def fix_hx_redirect(m):
    path = m.group(1)
    return f'"HX-Redirect": f"{{_ROOT_PATH}}{path}"'

content = re.sub(r'"HX-Redirect": "(/[^"]+)"', fix_hx_redirect, content)

with open("src/bot_web.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done - HX-Redirect fixed")
