#!/bin/bash
# verify_auth.sh — Verifica presença do X-Custom-Auth nos PCAPs
# Uso: bash /scripts/verify_auth.sh <matricula>
#
# Exemplo: bash /scripts/verify_auth.sh SUA_MATRICULA

MATRICULA=${1:-20261005029}
PCAP_DIR="/data/pcap"

echo "Buscando '$MATRICULA' nos arquivos pcap..."
for pcap in "$PCAP_DIR"/*.pcap; do
    [ -f "$pcap" ] || continue
    if strings "$pcap" | grep -q "$MATRICULA"; then
        echo "  [OK] $pcap"
    else
        echo "  [--] $pcap (não encontrado)"
    fi
done
