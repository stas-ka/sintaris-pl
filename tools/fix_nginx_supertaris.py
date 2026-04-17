# Update VPS nginx: remove sub_filter + proxy_redirect for /supertaris/ (app handles root_path now)
CONF = "/etc/nginx/sites-enabled/agents.sintaris.net.conf"

with open(CONF) as f:
    content = f.read()

# Remove the sub_filter block for /supertaris/ and its proxy_redirect
# Keep proxy_redirect for http://127.0.0.1:8086/ → /supertaris/ (rewrites full URLs in Location)
old = """        sub_filter 'href="/'      'href="/supertaris/';
        sub_filter 'src="/'       'src="/supertaris/';
        sub_filter 'action="/'    'action="/supertaris/';
        sub_filter 'hx-get="/'    'hx-get="/supertaris/';
        sub_filter 'hx-post="/'   'hx-post="/supertaris/';
        sub_filter 'hx-put="/'    'hx-put="/supertaris/';
        sub_filter 'hx-delete="/' 'hx-delete="/supertaris/';
        sub_filter_once     off;
        sub_filter_types    text/html;
        proxy_redirect      http://127.0.0.1:8086/ /supertaris/;
        proxy_redirect      /                       /supertaris/;"""
new = """        # App handles ROOT_PATH prefix in templates and Location headers (no sub_filter needed)
        proxy_redirect      off;"""

if old in content:
    content = content.replace(old, new)
    with open(CONF, "w") as f:
        f.write(content)
    print("Updated - sub_filter removed for /supertaris/")
else:
    print("Pattern not found - check manually")
    # Show context around line 163
    for i, line in enumerate(content.split("\n")[155:175], 156):
        print(f"{i}: {line}")
