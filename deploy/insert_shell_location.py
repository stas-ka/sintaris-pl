#!/usr/bin/env python3
"""Insert /shell/ ttyd location block into agents.sintaris.net.conf"""
import re

conf = '/etc/nginx/sites-enabled/agents.sintaris.net.conf'

with open(conf, 'r', encoding='latin-1') as f:
    content = f.read()

# Remove any previously failed /shell/ block insertion
content = re.sub(
    r'\n[ \t]*# Web shell.*?proxy_send_timeout[^\n]*\n[ \t]*\}[ \t]*\n',
    '\n',
    content,
    flags=re.DOTALL
)

# Also remove broken lines from failed sed attempt
lines = content.splitlines()
clean_lines = []
skip = False
for line in lines:
    if '# Web shell' in line or '# Web shell (ttyd)' in line:
        skip = True
    if skip and line.strip() == '}':
        skip = False
        continue
    if not skip:
        clean_lines.append(line)
content = '\n'.join(clean_lines)

shell_block = '''
    # Web shell (ttyd) - password protected
    location /shell/ {
        auth_basic           "VPS Shell";
        auth_basic_user_file /etc/nginx/ttyd.htpasswd;
        proxy_pass           http://127.0.0.1:7681/;
        proxy_http_version   1.1;
        proxy_set_header     Upgrade $http_upgrade;
        proxy_set_header     Connection "upgrade";
        proxy_set_header     Host $host;
        proxy_read_timeout   3600s;
        proxy_send_timeout   3600s;
    }
'''

# Insert before last closing brace
last_brace = content.rfind('}')
if last_brace == -1:
    print("ERROR: no closing brace found")
    exit(1)

content = content[:last_brace] + shell_block + content[last_brace:]

with open('/tmp/agents_fixed.conf', 'w', encoding='latin-1') as f:
    f.write(content)

print('WRITTEN OK')
print(f'Total lines: {len(content.splitlines())}')
