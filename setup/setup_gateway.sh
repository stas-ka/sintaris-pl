#!/bin/bash
# Install picoclaw-gateway as a systemd service

cat > /etc/systemd/system/picoclaw-gateway.service << 'EOF'
[Unit]
Description=picoclaw Telegram Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=stas
ExecStart=/usr/bin/picoclaw gateway
Restart=on-failure
RestartSec=10
WorkingDirectory=/home/stas

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable picoclaw-gateway
systemctl start picoclaw-gateway
sleep 4
systemctl status picoclaw-gateway --no-pager
