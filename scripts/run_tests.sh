#!/bin/bash
# run_tests.sh — Executa os 3 cenários (A, B, C) com tcpdump
# PPGCC/UFPI — Projeto de Redes de Computadores 2026-1
#
# Uso (dentro do contêiner client):
#   bash /scripts/run_tests.sh [tcp|rudp|both] [filesize_mb] [repetitions]
#   Exemplo: bash /scripts/run_tests.sh both 10 5

set -euo pipefail

MODE=${1:-both}
FILESIZE_MB=${2:-10}
REPS=${3:-5}
FILESIZE_BYTES=$((FILESIZE_MB * 1024 * 1024))
SERVER_IP="172.21.0.10"
IFACE="eth0"
DATA_DIR="/data"
PCAP_DIR="$DATA_DIR/pcap"
CSV_DIR="$DATA_DIR/csv"
LOG_DIR="$DATA_DIR/logs"

mkdir -p "$PCAP_DIR" "$CSV_DIR" "$LOG_DIR"

echo "================================================"
echo " PPGCC/UFPI — Testes de Rede — Go-Back-N"
echo " Modo=$MODE | Arquivo=${FILESIZE_MB}MB | Reps=$REPS"
echo "================================================"

# ────────────────────────────────────────────────
# Aplica cenário via tc qdisc netem
# ────────────────────────────────────────────────
apply_tc() {
    local scenario=$1 loss=$2 delay=$3
    echo "[tc] Cenário $scenario → loss=${loss}% delay=${delay}ms"
    tc qdisc del dev "$IFACE" root 2>/dev/null || true
    if [ "$loss" -eq 0 ]; then
        tc qdisc add dev "$IFACE" root netem delay "${delay}ms"
    else
        tc qdisc add dev "$IFACE" root netem delay "${delay}ms" loss "${loss}%"
    fi
    tc qdisc show dev "$IFACE"
}

# ────────────────────────────────────────────────
# Inicia tcpdump em background
# ────────────────────────────────────────────────
TCPDUMP_PID=""
start_tcpdump() {
    local pcap_file=$1
    pkill -f tcpdump 2>/dev/null || true
    sleep 0.3
    tcpdump -i "$IFACE" -w "$pcap_file" -s 0 \
        "host $SERVER_IP" &
    TCPDUMP_PID=$!
    echo "[tcpdump] PID=$TCPDUMP_PID → $pcap_file"
    sleep 1
}

stop_tcpdump() {
    local pcap_file=$1 csv_file=$2
    sleep 0.5
    kill "$TCPDUMP_PID" 2>/dev/null || true
    wait "$TCPDUMP_PID" 2>/dev/null || true
    python3 /scripts/pcap_to_csv.py "$pcap_file" "$csv_file" || true
}

# ────────────────────────────────────────────────
# Executa um teste individual
# ────────────────────────────────────────────────
run_one() {
    local scenario=$1 proto=$2 rep=$3
    local tag="scenario_${scenario}_${proto}_rep${rep}"
    local pcap="$PCAP_DIR/${tag}.pcap"
    local csv="$CSV_DIR/${tag}.csv"
    echo ""
    echo "--- Cenário $scenario | $proto | rep $rep/$REPS ---"
    start_tcpdump "$pcap"
    python3 /app/client.py \
        --mode "$proto" \
        --server "$SERVER_IP" \
        --file "/tmp/testfile.bin" \
        --filesize "$FILESIZE_BYTES" \
        --scenario "$scenario"
    stop_tcpdump "$pcap" "$csv"
}

# ────────────────────────────────────────────────
# Cenários
# ────────────────────────────────────────────────
declare -A LOSS=([A]=0  [B]=10 [C]=20)
declare -A DELAY=([A]=10 [B]=50 [C]=100)

for scenario in A B C; do
    apply_tc "$scenario" "${LOSS[$scenario]}" "${DELAY[$scenario]}"
    sleep 1
    for rep in $(seq 1 "$REPS"); do
        if [ "$MODE" = "both" ]; then
            run_one "$scenario" "tcp"  "$rep"
            sleep 2
            run_one "$scenario" "rudp" "$rep"
        else
            run_one "$scenario" "$MODE" "$rep"
        fi
        sleep 2
    done
done

# Remove regra tc ao terminar
tc qdisc del dev "$IFACE" root 2>/dev/null || true

echo ""
echo "================================================"
echo " Testes concluídos!"
echo " Logs : $LOG_DIR"
echo " PCAP : $PCAP_DIR"
echo " CSV  : $CSV_DIR"
echo "================================================"
