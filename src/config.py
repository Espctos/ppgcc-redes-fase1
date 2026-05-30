# config.py — Configurações globais
# PPGCC/UFPI — Projeto de Redes de Computadores 2026-1

MATRICULA = "20261005029"
NOME      = "Arthur Sabino Santos"
X_CUSTOM_AUTH = f"{MATRICULA}:{NOME}"

# Rede
SERVER_HOST      = "0.0.0.0"
SERVER_PORT_TCP  = 5003
SERVER_PORT_RUDP = 5004

# R-UDP — Go-Back-N
CHUNK_SIZE   = 1400   # bytes por segmento de dados
WINDOW_SIZE  = 8      # tamanho da janela GBN
TIMEOUT_SEC  = 0.3    # timeout de retransmissão (s)
MAX_RETRIES  = 30     # máximo de tentativas por janela

# Arquivo de teste
TEST_FILE_PATH = "/tmp/testfile.bin"
TEST_FILE_SIZE = 10 * 1024 * 1024   # 10 MB

# Diretórios dentro do contêiner
LOG_DIR  = "/data/logs"
PCAP_DIR = "/data/pcap"
CSV_DIR  = "/data/csv"
