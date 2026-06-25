# PPGCC/UFPI — Projeto de Redes de Computadores 2026-1
## Fases 1 e 2: TCP vs. R-UDP/GBN + Modelagem Estocástica (SimPy)

**Aluno:** Arthur Sabino Santos  
**Matrícula:** 20261005029  
**Disciplina:** Projeto de Redes de Computadores  
**Professor:** Rayner Gomes Sousa

## Links de Entrega

| Recurso | Link |
|---------|------|
| 📁 Repositório GitHub | https://github.com/Espctos/ppgcc-redes-fase1 |
| 📊 Google Colab — Fase 1 | https://colab.research.google.com/drive/1HWf3P__ADtXFDSOxaJB1Ba_m5-DqDNkv?usp=sharing |
| 💾 Google Drive (PCAPs) | https://drive.google.com/file/d/1_tPRM87EihzD0UE5tKY-g80yRTOlFOAG/view?usp=sharing |
| 📓 Google Colab — Fase 2 (SimPy) | `analysis/analysis_fase2.ipynb` (abrir no Colab pelo GitHub) |

> **Fase 1** — Entregue em 29/05/2026  
> **Fase 2** — Entregue em 25/06/2026

> **Dados de captura:** Os arquivos `.pcap` não estão no GitHub por excederem 100 MB.
> Estão disponíveis no Google Drive (link acima). Os CSVs exportados estão em `data/csv/`.

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Fase 2 — SimPy](#fase-2--simpy)
3. [Pré-requisitos](#pré-requisitos)
4. [Estrutura do Projeto](#estrutura-do-projeto)
5. [Executando os Testes (Fase 1)](#executando-os-testes)
6. [Executando a Simulação (Fase 2)](#executando-a-simulação-fase-2)
7. [Verificando o X-Custom-Auth no PCAP](#verificando-o-x-custom-auth)
8. [Protocolo R-UDP/GBN — Detalhes Técnicos](#protocolo-r-udpgbn)

---

## Visão Geral

Este projeto implementa transferência de arquivos via **TCP** e **R-UDP com Go-Back-N**
em contêineres Docker Ubuntu 22.04 (**Fase 1**) e um simulador de eventos discretos
SimPy que espelha o protocolo R-UDP/GBN (**Fase 2**).

---

## Fase 2 — SimPy

### Executando a Simulação

```bash
# Instalar dependências
pip install simpy numpy matplotlib seaborn scipy

# Demo rápida (uma execução por cenário)
python simulation/run_simulation.py --demo

# IC 95% com 30 execuções por cenário
python simulation/run_simulation.py --ci

# Todas as 10 tarefas + gráficos em simulation/plots/
python simulation/run_simulation.py --all
```

### 10 Tarefas de Validação

| Tarefa | Descrição |
|--------|-----------|
| 1 | Modelagem de Atraso — Distribuição Normal |
| 2 | Modelo de Perda de Bernoulli |
| 3 | Simulação de Timeout (retransmissões) |
| 4 | Curva de Vazão (1MB–100MB) |
| 5 | Sensibilidade da Janela W |
| 6 | Validação de RTT |
| 7 | Impacto do Jitter |
| 8 | Cenário de Estresse (25% perda) |
| 9 | Análise de Eficiência |
| 10 | Convergência Estatística (IC 95%, 30 runs) |

---

**Diferenças em relação ao Selective Repeat:**

| Característica     | Selective Repeat       | **Go-Back-N (este projeto)** |
|--------------------|------------------------|------------------------------|
| Retransmissão      | Apenas pacote perdido  | **Toda a janela**            |
| Buffer no receptor | Sim (fora de ordem)    | **Não (descarta out-of-order)** |
| Cabeçalho          | MD5 (16B) — 21B total  | **CRC32 (4B) — 13B total**  |
| Janela             | W = 16                 | **W = 8**                    |
| Timeout            | 0,5 s                  | **0,3 s**                    |
| Portas             | TCP 5001, UDP 5002     | **TCP 5003, UDP 5004**       |
| Subnet Docker      | 172.20.0.0/24          | **172.21.0.0/24**            |

---

## Pré-requisitos

- Docker Desktop (Windows/Mac) ou Docker Engine (Linux)
- Docker Compose v2
- Python 3.10+ (apenas para rodar a análise fora do contêiner)

---

## Configuração Rápida

**Antes de tudo**, edite `src/config.py` e troque os placeholders:

```python
MATRICULA = "20261XXXXXX"          # ← sua matrícula
NOME      = "Seu Nome Completo"    # ← seu nome
```

Isso propagará para todos os logs, cabeçalhos `X-Custom-Auth` e PCAPs.

---

## Estrutura do Projeto

```
ppgcc-redes-fase1/
├── src/
│   ├── config.py          # Parâmetros globais (matrícula, portas, janela)
│   ├── server.py          # Servidor TCP + R-UDP/GBN
│   └── client.py          # Cliente TCP + R-UDP/GBN
├── docker/
│   ├── Dockerfile         # Ubuntu 22.04 + Python + iproute2 + tcpdump
│   └── docker-compose.yml # Rede 172.21.0.0/24
├── scripts/
│   ├── run_tests.sh       # Orquestra os 3 cenários com tcpdump
│   ├── pcap_to_csv.py     # Converte .pcap → .csv via Scapy
│   └── verify_auth.sh     # Verifica X-Custom-Auth nos PCAPs
├── simulation/            # [FASE 2] Simulador SimPy
│   ├── simulator.py       # Núcleo GBN SimPy (modelo de canal + eventos)
│   ├── tasks.py           # 10 tarefas de validação + gráficos
│   ├── run_simulation.py  # Entry point (--demo, --ci, --all)
│   └── plots/             # Gráficos gerados pela Fase 2
├── analysis/
│   ├── analysis.py            # Gráficos Fase 1 (Plotly + Seaborn)
│   ├── analysis_colab.ipynb   # Notebook Colab — Fase 1
│   └── analysis_fase2.ipynb   # Notebook Colab — Fase 2 (SimPy)
├── data/
│   ├── logs/              # .jsonl métricas de aplicação
│   ├── csv/               # CSVs dos PCAPs
│   └── plots/             # Gráficos Fase 1
├── relatorio/
│   └── main.tex           # Artigo LaTeX (template SBC) — Fases 1 e 2
├── run_all.sh
└── requirements.txt
```

---

## Executando os Testes

### Opção A — Pipeline automático (recomendado)

Na raiz do projeto (máquina host):

```bash
chmod +x run_all.sh
bash run_all.sh 5      # 5 repetições por cenário/protocolo
```

Isso irá:
1. Fazer `docker compose build`
2. Subir os contêineres (`server` + `client`)
3. Executar `run_tests.sh` dentro do client
4. Executar `analysis.py` e gerar gráficos em `data/plots/`

---

### Opção B — Passo a passo manual

#### 1. Build e subida dos contêineres

```bash
cd docker
docker compose up -d --build
```

#### 2. Verificar se o servidor subiu

```bash
docker logs gbn_server
# Esperado:
# ... TCP server ouvindo em 0.0.0.0:5003
# ... R-UDP (GBN) server ouvindo em 0.0.0.0:5004
```

#### 3. Executar os testes (dentro do client)

```bash
docker exec -it gbn_client bash /scripts/run_tests.sh both 10 5
```

Argumentos: `[tcp|rudp|both]  [filesize_MB]  [repetitions]`

O script automaticamente:
- Aplica cada cenário via `tc qdisc`
- Inicia `tcpdump` em background antes de cada transferência
- Para o `tcpdump` após a transferência e exporta CSV

#### 4. Acompanhar logs em tempo real

```bash
# Logs do servidor (em outro terminal):
docker logs -f gbn_server

# Logs do cliente:
docker exec gbn_client tail -f /data/logs/client.log
```

#### 5. Parar os contêineres

```bash
docker compose -f docker/docker-compose.yml down
```

---

## Verificando o X-Custom-Auth

```bash
# Dentro do contêiner client:
docker exec gbn_client bash /scripts/verify_auth.sh 20261005029

# Saída esperada:
# [OK] /data/pcap/scenario_A_tcp_rep1.pcap
# [OK] /data/pcap/scenario_A_rudp_rep1.pcap
# ...
```

Ou inspecione diretamente com tcpdump:

```bash
docker exec gbn_client \
  tcpdump -r /data/pcap/scenario_A_rudp_rep1.pcap -A 2>/dev/null | grep -a "X-Custom-Auth"
```

---

## Gerando os Gráficos

### Dentro do contêiner (após os testes)

```bash
docker exec gbn_client python3 /analysis/analysis.py
# Gráficos salvos em /data/plots/ (montado em ./data/plots/ no host)
```

### Na máquina host (fora do Docker)

```bash
pip install -r requirements.txt
LOG_DIR=./data/logs CSV_DIR=./data/csv PLOT_DIR=./data/plots \
  python3 analysis/analysis.py
```

**Gráficos gerados:**

| Arquivo                       | Conteúdo                                      |
|-------------------------------|-----------------------------------------------|
| `throughput.html/.png`        | Throughput médio (Plotly)                     |
| `throughput_seaborn.png`      | Throughput médio (Seaborn)                    |
| `transfer_time.html/.png`     | Tempo de transferência                        |
| `retransmissions.html/.png`   | Retransmissões R-UDP/GBN por cenário          |
| `cross_validation.html/.png`  | App vs. TCPDump (bytes + overhead %)          |
| `cross_validation_table.csv`  | Tabela numérica da validação cruzada          |
| `heatmap.png`                 | Heatmap comparativo throughput/tempo          |

---

## Protocolo R-UDP/GBN

### Formato do pacote (13 bytes de cabeçalho)

```
 0               1               2               3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Número de Sequência (32 bits)           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Flags (8b)  |              Window Base (32 bits)             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|              Window Base cont. (16b)  |    CRC32 (início)     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       CRC32 cont. (32 bits)                   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Payload (≤ 1400 bytes)                  |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

**Flags:** `DATA=0x01`, `ACK=0x02`, `FIN=0x04`, `NAK=0x08`

### Comportamento Go-Back-N

- Emissor mantém **timer único** para o pacote `base` (mais antigo sem ACK)
- Expirado o timer → retransmite **toda a janela** `[base, next_seq-1]`
- Receptor descarta **qualquer pacote fora de ordem** → envia NAK com `expected-1`
- NAK dispara retransmissão imediata da janela (sem aguardar timeout)

---

## Resultados Esperados

### Throughput (arquivo 10 MB)

| Cenário          | TCP (estimado) | R-UDP/GBN (estimado) |
|------------------|---------------|----------------------|
| A (0%/10ms)      | 200–600 Mbps  | ~10–20 Mbps          |
| B (10%/50ms)     | 0,5–2 Mbps    | 0,2–0,8 Mbps         |
| C (20%/100ms)    | 0,1–0,5 Mbps  | 0,1–0,4 Mbps         |

### Overhead de Protocolo (validação cruzada)

| Protocolo   | Overhead esperado |
|-------------|-------------------|
| R-UDP/GBN   | +13–17% (cabeçalhos + ACKs + retransmissões) |
| TCP         | +4–8% nos cenários B/C; negativo aparente no A (coalescing) |

---

**Repositório:** `https://github.com/arthur-sabino/ppgcc-redes-fase1`
