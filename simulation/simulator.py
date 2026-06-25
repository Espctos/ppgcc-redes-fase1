"""
simulator.py — Simulador de Eventos Discretos Go-Back-N com SimPy
Fase 2: Modelagem Estocástica — PPGCC/UFPI 2026-1
Aluno: Arthur Sabino Santos (20261005029)
Orientador: Prof. Rayner Gomes Sousa
"""

import simpy
import heapq
import random
import numpy as np
from typing import Dict, Any, List, Optional

# ── Constantes do protocolo (idênticas à Fase 1) ──────────────────────────────
CHUNK_SIZE     = 1400           # bytes por pacote (igual ao src/config.py)
WINDOW_SIZE    = 8              # janela GBN
TIMEOUT_SEC    = 0.3            # timeout de retransmissão (s)
FILE_SIZE_10MB = 10 * 1024 * 1024  # 10 MB (tamanho do arquivo de teste)

# ── Parâmetros dos cenários (espelham tc qdisc netem da Fase 1) ───────────────
SCENARIOS: Dict[str, Dict[str, float]] = {
    'A': {'loss_prob': 0.00, 'delay_mean': 0.010, 'delay_std': 0.002},  # 0%  / 10ms
    'B': {'loss_prob': 0.10, 'delay_mean': 0.050, 'delay_std': 0.005},  # 10% / 50ms
    'C': {'loss_prob': 0.20, 'delay_mean': 0.100, 'delay_std': 0.010},  # 20% / 100ms
    'S': {'loss_prob': 0.25, 'delay_mean': 0.100, 'delay_std': 0.010},  # Stress: 25%
}


def simulate_gbn(
    file_size_bytes: int = FILE_SIZE_10MB,
    loss_prob: float = 0.0,
    delay_mean_s: float = 0.010,
    delay_std_s: float = 0.002,
    window_size: int = WINDOW_SIZE,
    timeout_s: float = TIMEOUT_SEC,
    seed: Optional[int] = None,
    return_rtt_samples: bool = False,
) -> Dict[str, Any]:
    """
    Simulação GBN (Go-Back-N) via SimPy — eventos discretos.

    Modelo de canal:
    - Perda de Bernoulli: cada pacote é perdido independentemente com prob loss_prob
      (replica o modelo tc qdisc netem loss da Fase 1).
    - Atraso: one-way delay ~ N(delay_mean_s, delay_std_s²), truncado em 0.
    - Receptor GBN: descarta pacotes fora de ordem (apenas aceita seq == expected_seq).

    Comportamento GBN do emissor:
    - Mantém janela deslizante de tamanho window_size.
    - Em timeout (T = timeout_s): retransmite todos os pacotes [base, next_seq).
    - Em ACK recebido: avança base, recalcula janela.

    Returns
    -------
    dict com chaves:
        transfer_time    : tempo total de transferência (s)
        throughput_mbps  : vazão efetiva (Mbps)
        retransmissions  : total de retransmissões
        data_sent        : total de pacotes enviados (orig + retrans)
        acks_received    : total de ACKs recebidos
        rtt_mean         : RTT médio observado (s)
        rtt_std          : desvio padrão do RTT (s)
        total_packets    : pacotes de dados originais
        efficiency       : total_packets / data_sent
        rtt_samples      : lista de amostras RTT (somente se return_rtt_samples=True)
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    total_pkts = max(1, file_size_bytes // CHUNK_SIZE)
    env = simpy.Environment()

    # Estado compartilhado entre funções aninhadas
    st: Dict[str, Any] = {
        'base':              0,
        'next_seq':          0,
        'retransmissions':   0,
        'data_sent':         0,
        'acks_received':     0,
        'rtt_samples':       [],
        'ack_heap':          [],   # min-heap: (arrive_time, seq)
        'recv_expected':     0,    # próximo seq esperado pelo receptor GBN
    }

    # ── Funções auxiliares ────────────────────────────────────────────────────

    def one_way_delay() -> float:
        """Amostra atraso de propagação one-way de N(μ, σ²)."""
        d = random.gauss(delay_mean_s, max(1e-6, delay_std_s))
        return max(1e-6, d)

    def tx_packet(seq: int) -> None:
        """
        Transmite o pacote seq no instante env.now.

        Aplica modelo de canal:
        1. Perda de Bernoulli (mirrors tc qdisc netem loss).
        2. Receptor GBN descarta pacotes fora de ordem.
        3. Se aceito: agenda chegada do ACK no heap.
        """
        st['data_sent'] += 1

        # Modelo de perda de Bernoulli
        if random.random() < loss_prob:
            return  # pacote perdido no canal

        # Regra GBN: receptor aceita apenas seq == recv_expected
        if seq != st['recv_expected']:
            return  # pacote descartado (fora de ordem)

        # Pacote aceito → receptor avança e envia ACK cumulativo
        st['recv_expected'] += 1
        fwd = one_way_delay()          # atraso de ida (dados)
        bck = one_way_delay()          # atraso de volta (ACK)
        arrive_time = env.now + fwd + bck
        st['rtt_samples'].append(fwd + bck)
        heapq.heappush(st['ack_heap'], (arrive_time, seq))

    # ── Processo SimPy principal ──────────────────────────────────────────────

    def gbn_sender(env: simpy.Environment):
        """
        Processo SimPy do emissor GBN.
        Usa yield env.timeout() para avançar o relógio de simulação.
        """
        timer_start = env.now
        h = st['ack_heap']

        while st['base'] < total_pkts:

            # 1. Preencher a janela com novos pacotes
            while (st['next_seq'] < total_pkts and
                   st['next_seq'] < st['base'] + window_size):
                tx_packet(st['next_seq'])
                st['next_seq'] += 1

            # 2. Descartar ACKs obsoletos (seq < base já processados)
            while h and h[0][1] < st['base']:
                heapq.heappop(h)

            # 3. Determinar próximo evento: ACK ou timeout
            timeout_abs  = timer_start + timeout_s
            earliest_ack = h[0][0] if h else float('inf')
            next_event   = min(earliest_ack, timeout_abs)

            # 4. Avançar o relógio de simulação (SimPy yield)
            wait = max(0.0, next_event - env.now)
            yield env.timeout(wait)

            # 5a. ACK recebido antes do timeout → avança janela
            if earliest_ack <= timeout_abs and h:
                _, seq = heapq.heappop(h)

                # Coletar ACKs co-chegantes (mesmo instante)
                now = env.now
                arrived = {seq}
                stale = []
                while h and h[0][0] <= now:
                    t2, s2 = heapq.heappop(h)
                    if s2 >= st['base']:
                        arrived.add(s2)
                    else:
                        stale.append((t2, s2))
                for item in stale:
                    heapq.heappush(h, item)

                # Avançar base pelos ACKs cumulativos consecutivos
                while st['base'] in arrived and st['base'] < total_pkts:
                    st['base'] += 1
                    st['acks_received'] += 1
                timer_start = env.now

            # 5b. Timeout → Go-Back-N: retransmite toda a janela
            else:
                # Limpar ACKs pendentes da janela atual (ficaram obsoletos)
                st['ack_heap'] = [(t, s) for t, s in h if s < st['base']]
                heapq.heapify(st['ack_heap'])
                h = st['ack_heap']

                # Resetar estado do receptor para base (receptor GBN faz o mesmo)
                st['recv_expected'] = st['base']

                # Retransmitir pacotes [base, next_seq)
                for s in range(st['base'], st['next_seq']):
                    tx_packet(s)
                    st['retransmissions'] += 1

                timer_start = env.now

    # Registrar e executar processo SimPy
    env.process(gbn_sender(env))
    env.run()

    # ── Computar métricas finais ──────────────────────────────────────────────
    transfer_time   = env.now
    throughput_mbps = (file_size_bytes / transfer_time / 1e6) if transfer_time > 0 else 0.0
    rtt             = st['rtt_samples']

    result = {
        'transfer_time':   transfer_time,
        'throughput_mbps': throughput_mbps,
        'retransmissions': st['retransmissions'],
        'data_sent':       st['data_sent'],
        'acks_received':   st['acks_received'],
        'rtt_mean':        float(np.mean(rtt))   if rtt else 2.0 * delay_mean_s,
        'rtt_std':         float(np.std(rtt))    if len(rtt) > 1 else 0.0,
        'total_packets':   total_pkts,
        'efficiency':      total_pkts / st['data_sent'] if st['data_sent'] > 0 else 0.0,
    }
    if return_rtt_samples:
        result['rtt_samples'] = rtt
    return result


def run_multiple(
    n_runs: int = 30,
    seed_start: int = 42,
    **sim_kwargs
) -> Dict[str, List[float]]:
    """
    Executa n_runs simulações independentes com sementes diferentes.
    Retorna dicionário com listas de resultados por métrica.
    """
    keys = ['transfer_time', 'throughput_mbps', 'retransmissions',
            'data_sent', 'acks_received', 'rtt_mean', 'rtt_std',
            'total_packets', 'efficiency']
    results: Dict[str, List[float]] = {k: [] for k in keys}
    for i in range(n_runs):
        r = simulate_gbn(seed=seed_start + i, **sim_kwargs)
        for k in keys:
            results[k].append(float(r[k]))
    return results


def stats_ci95(values) -> Dict[str, float]:
    """Calcula média ± intervalo de confiança 95% para uma lista de valores."""
    arr = np.asarray(values, dtype=float)
    n   = len(arr)
    mu  = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    ci  = 1.96 * std / np.sqrt(n)   if n > 0 else 0.0
    return {'mean': mu, 'std': std, 'ci95': ci, 'n': n}
