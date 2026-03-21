#!/bin/bash
# =============================================================================
# setup_ssl.sh — Generate self-signed TLS certificate for Taris Bot Web UI
# =============================================================================
# Creates ~/.taris/ssl/key.pem + cert.pem with correct Subject Alternative
# Names (SAN) so modern browsers accept the certificate without errors once
# the cert is imported into the OS/browser trusted root store.
#
# Why SAN matters: Chrome / Firefox ignore the CN field entirely and require
# a matching SAN entry. A cert with only CN=hostname but no SAN will always
# show "Not Secure" even after being trusted as a root CA.
#
# Usage (run on the Pi as the bot user):
#   bash setup_ssl.sh
#
# After running, download cert.pem to Windows and install as Trusted Root CA:
#   From Windows: pscp stas@<HOST>:/home/stas/.taris/ssl/cert.pem <hostname>.crt
#   Then: certutil -addstore -f "Root" <hostname>.crt
# =============================================================================

set -euo pipefail

SSL_DIR="/home/stas/.taris/ssl"
mkdir -p "$SSL_DIR"

HOSTNAME_SHORT=$(hostname -s)
HOSTNAME_FQDN=$(hostname -f 2>/dev/null || hostname)

# Collect all IP addresses (LAN + Tailscale)
IPSANS=""
while IFS= read -r ip; do
    ip=$(echo "$ip" | xargs)
    [[ -z "$ip" ]] && continue
    IPSANS="${IPSANS}IP:${ip},"
done < <(hostname -I | tr ' ' '\n')

# Tailscale IP (if available)
TS_IP=$(ip addr show tailscale0 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 || true)
if [[ -n "$TS_IP" ]]; then
    IPSANS="${IPSANS}IP:${TS_IP},"
fi

# Build full SAN string
SAN="DNS:${HOSTNAME_SHORT},DNS:${HOSTNAME_FQDN},DNS:localhost,IP:127.0.0.1,${IPSANS%,}"

echo "=============================================="
echo " Taris Bot — SSL Certificate Setup"
echo "=============================================="
echo "  Hostname : ${HOSTNAME_SHORT}"
echo "  FQDN     : ${HOSTNAME_FQDN}"
echo "  SAN      : ${SAN}"
echo "  Output   : ${SSL_DIR}/"
echo ""

# Generate private key + self-signed certificate (valid 10 years)
openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "${SSL_DIR}/key.pem" \
    -out    "${SSL_DIR}/cert.pem" \
    -days   3650 \
    -subj   "/CN=${HOSTNAME_SHORT}/O=PicoBot/OU=Local" \
    -addext "subjectAltName=${SAN}" \
    2>&1 | grep -v "^writing"

chmod 600 "${SSL_DIR}/key.pem"
chmod 644 "${SSL_DIR}/cert.pem"

# Print fingerprint for verification
FINGERPRINT=$(openssl x509 -noout -fingerprint -sha256 -in "${SSL_DIR}/cert.pem" | cut -d= -f2)

echo ""
echo " Certificate generated successfully."
echo "  Key        : ${SSL_DIR}/key.pem"
echo "  Cert       : ${SSL_DIR}/cert.pem"
echo "  Expires    : $(openssl x509 -noout -enddate -in "${SSL_DIR}/cert.pem" | cut -d= -f2)"
echo "  SHA-256    : ${FINGERPRINT}"
echo ""
echo " SAN entries:"
openssl x509 -noout -text -in "${SSL_DIR}/cert.pem" | grep -A1 "Subject Alternative Name" | tail -1 | sed 's/^[[:space:]]*/  /'
echo ""
echo "=============================================="
echo " NEXT STEP — Install cert as Trusted Root CA"
echo "=============================================="
echo ""
echo " On Windows, run these commands in an Admin CMD:"
echo ""
echo "   pscp -pw <pwd> stas@${HOSTNAME_SHORT}:${SSL_DIR}/cert.pem ${HOSTNAME_SHORT}.crt"
echo "   certutil -addstore -f \"Root\" ${HOSTNAME_SHORT}.crt"
echo ""
echo " Then restart Chrome/Edge and reload https://${HOSTNAME_SHORT}:8080"
echo "=============================================="
