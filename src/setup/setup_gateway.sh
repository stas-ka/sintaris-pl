#!/bin/bash
# Install taris-gateway as a systemd service

cat > /etc/systemd/system/taris-gateway.service << 'EOF'
[Unit]
Description=taris Telegram Gateway
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
systemctl enable taris-gateway
systemctl start taris-gateway
sleep 4
systemctl status taris-gateway --no-pager
