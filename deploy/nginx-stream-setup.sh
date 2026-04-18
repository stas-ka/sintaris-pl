#!/bin/bash
set -e

echo '=== Step 4: Add stream block to nginx.conf ==='
if ! grep -q 'stream.d' /etc/nginx/nginx.conf; then
    printf '\nstream {\n    include /etc/nginx/stream.d/*.conf;\n}\n' >> /etc/nginx/nginx.conf
    echo 'stream block added'
else
    echo 'stream block already present'
fi
tail -5 /etc/nginx/nginx.conf

echo '=== Step 5: Change listen 443 -> 8443 in sites-enabled ==='
echo "Before: $(grep -r 'listen 443' /etc/nginx/sites-enabled/ 2>/dev/null | grep -c 'listen') listen 443 lines"

# IPv4: listen 443 -> listen 127.0.0.1:8443
sed -i 's/listen 443\([^0-9]\)/listen 127.0.0.1:8443\1/g' /etc/nginx/sites-enabled/*

# IPv6: listen [::]:443 -> comment out
sed -i 's/listen \[::\]:443/#listen [::]:443/g' /etc/nginx/sites-enabled/*

echo "After:  $(grep -r 'listen 443' /etc/nginx/sites-enabled/ 2>/dev/null | grep -c 'listen') listen 443 lines"
echo "8443 listeners: $(grep -r 'listen.*8443' /etc/nginx/sites-enabled/ | wc -l)"

echo '=== Step 6: Verify stream config ==='
cat /etc/nginx/stream.d/ssh-tunnel.conf

echo '=== Step 7: Test nginx config ==='
nginx -t 2>&1 && echo 'NGINX_TEST_OK' || echo 'NGINX_TEST_FAILED'
