#!/bin/bash
# run_all.sh — Orquestra build, subida dos containers, testes e análise
# Execute na raiz do projeto (fora dos containers), na máquina host

set -euo pipefail

REPS=${1:-5}
echo "============================================================"
echo " PPGCC/UFPI — Pipeline Completo"
echo " Repetições por cenário/protocolo: $REPS"
echo "============================================================"

# 1. Cria diretórios de dados
mkdir -p data/{logs,pcap,csv,plots}

# 2. Build e sobe os containers
docker compose -f docker/docker-compose.yml up -d --build
echo "[docker] Aguardando servidor inicializar..."
sleep 5

# 3. Executa os testes dentro do container client
docker exec gbn_client bash /scripts/run_tests.sh both 10 "$REPS"

# 4. Executa análise dentro do container client
docker exec gbn_client python3 /app/../analysis/analysis.py \
    || docker exec gbn_client python3 /scripts/../analysis/analysis.py || true

echo ""
echo "============================================================"
echo " Concluído! Resultados em ./data/"
echo "============================================================"
