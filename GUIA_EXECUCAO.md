# Guia de Execução — Fase 1
## PPGCC/UFPI — Projeto de Redes de Computadores 2026-1

**Aluno:** Arthur Sabino Santos  
**Matrícula:** 20261005029  
**Professor:** Rayner Gomes Sousa  

---

## Pré-requisitos do Avaliador

| Requisito | Versão mínima | Como verificar |
|-----------|--------------|----------------|
| Docker Desktop | 4.x | `docker --version` |
| Docker Compose | v2 | `docker compose version` |
| WSL2 (Windows) | — | Já incluído no Docker Desktop |
| Sistema operacional | Windows 10/11, Linux ou macOS | — |

> **Importante:** Todo o `tc qdisc`, `tcpdump` e Python rodam **dentro dos contêineres Docker**. Não é necessário instalar nada além do Docker na máquina host.

---

## Parte 1 — Preparação do Ambiente

### 1.1 Clonar/baixar o projeto

Se o repositório estiver no GitHub:
```bash
git clone https://github.com/arthur-sabino/ppgcc-redes-fase1.git
cd ppgcc-redes-fase1
```

Ou descompactar o ZIP entregue e navegar até a pasta:
```bash
cd ppgcc-redes-fase1
```

### 1.2 Criar os diretórios de dados

```bash
mkdir -p data/logs data/pcap data/csv data/plots
```

No Windows (PowerShell):
```powershell
New-Item -ItemType Directory -Force data/logs, data/pcap, data/csv, data/plots
```

### 1.3 Verificar o cabeçalho X-Custom-Auth

Confirme que `src/config.py` contém os dados corretos:
```python
MATRICULA = "20261005029"
NOME      = "Arthur Sabino Santos"
```

---

## Parte 2 — Build e Inicialização dos Contêineres

### 2.1 Construir as imagens Docker

```bash
docker compose -f docker/docker-compose.yml build
```

Isso instala no contêiner: Python 3, `iproute2` (tc), `tcpdump`, `scapy`, `plotly`, `seaborn`.

Saída esperada:
```
[+] Building ...
 => [server] FROM ubuntu:22.04
 => CACHED [server] RUN apt-get update ...
 => FINISHED
```

### 2.2 Subir os contêineres em background

```bash
docker compose -f docker/docker-compose.yml up -d
```

### 2.3 Verificar se o servidor está ativo

```bash
docker logs gbn_server
```

Saída esperada:
```
2026-05-29 ... [INFO] TCP server ouvindo em 0.0.0.0:5003
2026-05-29 ... [INFO] R-UDP (GBN) server ouvindo em 0.0.0.0:5004
2026-05-29 ... [INFO] Servidores ativos. Ctrl+C para encerrar.
```

---

## Parte 3 — Execução dos Testes

Os testes executam automaticamente os **3 cenários de rede** (A, B, C) com
**5 repetições** cada, para ambos os protocolos (TCP e R-UDP/GBN), totalizando
**30 transferências**. Cada transferência usa um arquivo de 10 MB.

### 3.1 Iniciar os testes completos

```bash
docker exec gbn_client bash /scripts/run_tests.sh both 10 5
```

Parâmetros: `[tcp|rudp|both]  [tamanho_MB]  [repetições]`

**O que acontece automaticamente em cada transferência:**

```
Para cada cenário em {A, B, C}:
  1. tc qdisc netem aplica perda + delay na interface eth0 do client
  2. tcpdump inicia captura em background → salva .pcap
  3. client.py executa a transferência (TCP ou R-UDP/GBN)
  4. tcpdump para → pcap_to_csv.py exporta .csv
  5. Métricas registradas em /data/logs/*.jsonl
```

**Tempo estimado total:**
- Cenário A (0%/10ms): ~2 min
- Cenário B (10%/50ms): ~25 min
- Cenário C (20%/100ms): ~50 min
- **Total: ~80 minutos**

> Deixe o terminal aberto. Pode acompanhar o progresso com:
> ```bash
> docker exec gbn_client tail -f /data/logs/client.log
> ```

### 3.2 O que cada cenário injeta na rede

| Cenário | Perda de Pacotes | Delay | Comando tc aplicado |
|---------|-----------------|-------|---------------------|
| A | 0% | 10 ms | `tc qdisc add dev eth0 root netem delay 10ms` |
| B | 10% | 50 ms | `tc qdisc add dev eth0 root netem delay 50ms loss 10%` |
| C | 20% | 100 ms | `tc qdisc add dev eth0 root netem delay 100ms loss 20%` |

### 3.3 Verificar os arquivos gerados após os testes

```bash
# PCAPs capturados (30 arquivos):
ls data/pcap/

# CSVs exportados (30 arquivos):
ls data/csv/

# Métricas de aplicação:
cat data/logs/tcp_client_metrics.jsonl
cat data/logs/rudp_client_metrics.jsonl
```

---

## Parte 4 — Validação do X-Custom-Auth no PCAP

Este passo **comprova que o cabeçalho com matrícula e nome está visível na captura de rede**.

### 4.1 Script automático

```bash
docker exec gbn_client bash /scripts/verify_auth.sh 20261005029
```

Saída esperada:
```
Buscando '20261005029' nos arquivos pcap...
  [OK] /data/pcap/scenario_A_tcp_rep1.pcap
  [OK] /data/pcap/scenario_A_rudp_rep1.pcap
  [OK] /data/pcap/scenario_B_tcp_rep1.pcap
  ...
```

### 4.2 Inspeção manual com tcpdump (para screenshot)

```bash
# Ver o cabeçalho X-Custom-Auth em texto claro:
docker exec gbn_client \
  tcpdump -r /data/pcap/scenario_A_rudp_rep1.pcap -A 2>/dev/null \
  | grep -a "20261005029"
```

Saída esperada (trecho):
```
...X-Custom-Auth...20261005029:Arthur Sabino Santos...
```

---

## Parte 5 — Geração dos Gráficos

### 5.1 Executar o script de análise dentro do contêiner

```bash
docker exec gbn_client \
  bash -c "LOG_DIR=/data/logs CSV_DIR=/data/csv PLOT_DIR=/data/plots \
           python3 /analysis/analysis.py"
```

### 5.2 Verificar os gráficos gerados

```bash
ls data/plots/
```

Arquivos gerados:

| Arquivo | Descrição |
|---------|-----------|
| `throughput.html` | Throughput interativo (Plotly) |
| `throughput.png` | Throughput (imagem para relatório) |
| `throughput_seaborn.png` | Throughput (Seaborn) |
| `transfer_time.html/.png` | Tempo de transferência |
| `retransmissions.html/.png` | Retransmissões R-UDP/GBN |
| `cross_validation.html/.png` | Validação cruzada App vs TCPDump |
| `cross_validation_table.csv` | Tabela numérica da validação cruzada |
| `heatmap.png` | Heatmap comparativo |

Os arquivos `.png` ficam em `data/plots/` na máquina host e são os mesmos usados no relatório LaTeX/Colab.

---

## Parte 6 — Notebook Google Colab

O notebook `analysis/analysis_colab.ipynb` contém toda a análise pronta para executar no Colab.

### 6.1 Subir os dados para o Google Drive

Faça upload da pasta `data/` (logs + csv + plots) para o Google Drive.

### 6.2 Abrir o notebook no Colab

1. Acesse [colab.research.google.com](https://colab.research.google.com)
2. **File → Upload notebook** → selecione `analysis/analysis_colab.ipynb`
3. Na primeira célula, monte o Drive:
   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   ```
4. Ajuste o caminho base para onde você fez upload dos dados
5. Execute todas as células (**Runtime → Run all**)

Os gráficos gerados no Colab são idênticos aos do relatório.

---

## Parte 7 — Encerrar os Contêineres

```bash
docker compose -f docker/docker-compose.yml down
```

---

## Parte 8 — Fase 2: Simulação Estocástica (SimPy)

A Fase 2 **não requer Docker**. É um simulador de eventos discretos em Python puro
que espelha o protocolo R-UDP/GBN da Fase 1 e executa as 10 tarefas de validação.

### 8.1 Instalar dependências (máquina host)

```bash
pip install simpy numpy matplotlib seaborn scipy
```

### 8.2 Executar a simulação

```bash
# Demonstração rápida — uma execução por cenário
python simulation/run_simulation.py --demo

# Intervalos de confiança 95% (30 execuções por cenário)
python simulation/run_simulation.py --ci

# TODAS as 10 tarefas + gráficos (salvos em simulation/plots/)
python simulation/run_simulation.py --all
```

> No Windows, se aparecer erro de acentuação no console, defina
> `set PYTHONIOENCODING=utf-8` (cmd) ou `$env:PYTHONIOENCODING="utf-8"` (PowerShell)
> antes de rodar.

### 8.3 As 10 Tarefas de Validação (gráficos gerados)

| Tarefa | Arquivo gerado | Descrição |
|--------|----------------|-----------|
| 1 | `task1_delay_modeling.png` | Modelagem de atraso N(μ,σ²) |
| 2 | `task2_bernoulli_loss.png` | Perda de Bernoulli vs tc |
| 3 | `task3_timeout_simulation.png` | Retransmissões Real vs Simulado |
| 4 | `task4_throughput_curve.png` | Curva de vazão 1MB–100MB |
| 5 | `task5_window_sensitivity.png` | Sensibilidade da janela W |
| 6 | `task6_rtt_validation.png` | Validação de RTT |
| 7 | `task7_jitter_impact.png` | Impacto do jitter |
| 8 | `task8_stress_scenario.png` | Cenário de estresse (25%) |
| 9 | `task9_efficiency.png` | Análise de eficiência |
| 10 | `task10_convergence.png` | Convergência IC 95% (30 runs) |
| — | `real_vs_simulated.png` | **Comparação Real vs Simulado** |

### 8.4 Notebook Colab da Fase 2

O notebook `analysis/analysis_fase2.ipynb` é autocontido (define o simulador e roda
todas as tarefas). Abra no Colab via **File → Upload notebook** e execute
**Runtime → Run all**. Não requer montar o Drive.

### 8.5 Principais resultados da validação

| Cenário | Vazão Real | Vazão Sim. | Retrans Real | Retrans Sim. |
|---------|-----------|-----------|--------------|--------------|
| A | 7,88 Mbps | 4,85 Mbps | ~2 | 0 |
| B | 0,26 Mbps | 0,22 Mbps | 6.652 | 6.689 |
| C | 0,11 Mbps | 0,09 Mbps | 15.218 | 15.000 |

O simulador reproduz as **retransmissões reais com erro < 1,5%** (Cenários B e C).
A subestimação de vazão (~1,2–1,6×) deve-se ao modelo de RTT bidirecional do
simulador vs. atraso unidirecional do `tc qdisc`.

---

## Parte 9 — Compilar o Relatório LaTeX (Overleaf)

1. Acesse [overleaf.com](https://overleaf.com) → **New Project → Blank Project**
2. Substitua o `main.tex` pelo conteúdo de `relatorio/main.tex`
3. Faça upload de **todos os `.png` da pasta `relatorio/`** (já contém imagens das Fases 1 e 2)
4. No LaTeX, os `\includegraphics` referenciam apenas o nome do arquivo:
   ```latex
   \includegraphics[width=0.85\textwidth]{throughput.png}
   ```
5. Clique em **Recompile**

> A pasta `relatorio/` já está pronta para o Overleaf: contém o `main.tex` e
> as 18 imagens (`.png`) referenciadas no documento.

---

## Resumo dos Comandos (Execução Rápida)

```bash
# 1. Criar diretórios
mkdir -p data/{logs,pcap,csv,plots}

# 2. Build + subir contêineres
docker compose -f docker/docker-compose.yml up -d --build

# 3. Aguardar servidor (5 segundos) e rodar todos os testes
sleep 5
docker exec gbn_client bash /scripts/run_tests.sh both 10 5

# 4. Verificar X-Custom-Auth
docker exec gbn_client bash /scripts/verify_auth.sh 20261005029

# 5. Gerar gráficos
docker exec gbn_client \
  bash -c "LOG_DIR=/data/logs CSV_DIR=/data/csv PLOT_DIR=/data/plots \
           python3 /analysis/analysis.py"

# 6. Encerrar
docker compose -f docker/docker-compose.yml down
```

---

## Solução de Problemas Comuns

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| `permission denied` em `tc qdisc` | Contêiner sem NET_ADMIN | Verifique `cap_add: NET_ADMIN` no docker-compose.yml |
| `gbn_server: No such container` | Contêineres não subiram | Rode `docker compose up -d` novamente |
| `tcpdump: eth0: No such device` | Interface diferente dentro do contêiner | Rode `docker exec gbn_client ip link` para ver o nome correto e ajuste `IFACE` em `run_tests.sh` |
| Gráficos não gerados | Testes não concluíram | Verifique `data/logs/` — deve haver linhas nos `.jsonl` |
| `ModuleNotFoundError: scapy` | Build incompleto | Rode `docker compose build --no-cache` |

---

## Estrutura Final dos Entregáveis

```
ppgcc-redes-fase1/
├── src/               ← Código-fonte Python (TCP + R-UDP/GBN)
├── docker/            ← Dockerfile + docker-compose.yml
├── scripts/           ← run_tests.sh, pcap_to_csv.py, verify_auth.sh
├── analysis/          ← analysis.py + analysis_colab.ipynb
├── data/
│   ├── logs/          ← Métricas (.jsonl) — geradas após execução
│   ├── pcap/          ← Capturas tcpdump (.pcap) — geradas após execução
│   ├── csv/           ← CSVs exportados — gerados após execução
│   └── plots/         ← Gráficos (.png/.html) — gerados após execução
├── relatorio/
│   └── main.tex       ← Artigo SBC (Overleaf)
├── GUIA_EXECUCAO.md   ← Este documento
└── README.md          ← Visão geral técnica
```
