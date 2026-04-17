CONF = "/etc/nginx/sites-available/agents.sintaris.net"

BLOCK = """    # -- SintAItion OpenClaw /supertaris/ -----------------------------------
    location = /supertaris { return 301 /supertaris/; }

    location /supertaris/ {
        proxy_pass            http://127.0.0.1:8086/;

        proxy_set_header      Host               $host;
        proxy_set_header      X-Real-IP          $remote_addr;
        proxy_set_header      X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header      X-Forwarded-Proto  $scheme;
        proxy_set_header      Accept-Encoding    "";

        proxy_http_version    1.1;
        proxy_set_header      Upgrade            $http_upgrade;
        proxy_set_header      Connection         $connection_upgrade;

        proxy_read_timeout    300s;
        proxy_send_timeout    300s;
        proxy_connect_timeout 10s;
        proxy_buffering       off;
        client_max_body_size  20m;

        proxy_redirect        off;
    }

"""

with open(CONF) as f:
    content = f.read()

if "/supertaris/" in content:
    print("Already present")
else:
    idx = content.rfind("}")
    content = content[:idx] + BLOCK + content[idx:]
    with open(CONF, "w") as f:
        f.write(content)
    print("Added /supertaris/ block")
