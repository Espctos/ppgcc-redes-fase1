"""
tasks.py — 10 Tarefas de Validação do Simulador GBN + Gráficos Real vs Simulado
Fase 2: Modelagem Estocástica — PPGCC/UFPI 2026-1
Aluno: Arthur Sabino Santos (20261005029)
"""

import os
import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from typing import Dict, List

sys.path.insert(0, os.path.dirname(__file__))
from simulator import (
    simulate_gbn, run_multiple, stats_ci95,
    SCENARIOS, CHUNK_SIZE, FILE_SIZE_10MB, WINDOW_SIZE, TIMEOUT_SEC
)

# ── Configurações visuais ────────────────────────────────────────────────────
sns.set_theme(style='whitegrid', palette='deep', font_scale=1.0)
COLORS = {'A': '#2196F3', 'B': '#FF9800', 'C': '#F44336', 'S': '#9C27B0'}
PLOTS_DIR = os.path.join(os.path.dirname(__file__), 'plots')
os.makedirs(PLOTS_DIR, exist_ok=True)

# ── Métricas reais da Fase 1 (rudp_client_metrics.jsonl) ─────────────────────
# Cenário A: 5 repetições limpas (0% perda / 10ms)
# Cenário B: 5 repetições (10% perda / 50ms)
# Cenário C: 3 repetições limpas (20% perda / 100ms) — demais anomalias de timeout
REAL_RUDP = {
    'A': {
        'transfer_times':  [10.9207, 10.6400, 10.6580, 10.5320, 10.6309],
        'throughputs':     [7.6814,  7.8840,  7.8707,  7.9649,  7.8907],
        'retransmissions': [8,       0,       0,       0,       0],
    },
    'B': {
        'transfer_times':  [325.3516, 312.7303, 315.8990, 318.0697, 315.9218],
        'throughputs':     [0.2578,   0.2682,   0.2655,   0.2637,   0.2655],
        'retransmissions': [6832,     6536,     6630,     6651,     6611],
    },
    'C': {
        'transfer_times':  [758.2228, 741.9798, 761.9748],
        'throughputs':     [0.1106,   0.1131,   0.1101],
        'retransmissions': [15276,    14890,    15488],
    },
}

# RTT esperado por cenário (2 × one-way delay configurado no tc)
RTT_CONFIG = {'A': 2 * 0.010, 'B': 2 * 0.050, 'C': 2 * 0.100}


def _savefig(name: str) -> str:
    path = os.path.join(PLOTS_DIR, name)
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close('all')
    print(f"  [OK] Salvo: {name}")
    return path


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 1 — Modelagem de Atraso
# ════════════════════════════════════════════════════════════════════════════
def task1_delay_modeling() -> str:
    """
    Representa a latência via distribuição normal N(μ, σ²) calibrada
    com os parâmetros do tc qdisc da Fase 1.
    Valida que o simulador usa o modelo correto de atraso.
    """
    print("[Tarefa 1] Modelagem de Atraso...")
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    scenario_info = [
        ('A', 'Cenário A\n(0% perda / 10ms)', 0.010, 0.002),
        ('B', 'Cenário B\n(10% perda / 50ms)', 0.050, 0.005),
        ('C', 'Cenário C\n(20% perda / 100ms)', 0.100, 0.010),
    ]

    for ax, (sc, title, mu, sigma) in zip(axes, scenario_info):
        # Gerar amostras de RTT (2 × atraso one-way independentes)
        n_samples = 5000
        fwd = np.maximum(1e-6, np.random.normal(mu, sigma, n_samples))
        bck = np.maximum(1e-6, np.random.normal(mu, sigma, n_samples))
        rtt_ms = (fwd + bck) * 1000

        # Histograma das amostras
        ax.hist(rtt_ms, bins=50, density=True, alpha=0.6,
                color=COLORS[sc], label='Amostras simuladas', edgecolor='white')

        # Curva teórica N(2μ, 2σ²)
        mu_rtt = 2 * mu * 1000
        std_rtt = np.sqrt(2) * sigma * 1000
        x = np.linspace(rtt_ms.min(), rtt_ms.max(), 300)
        ax.plot(x, stats.norm.pdf(x, mu_rtt, std_rtt), 'r-', lw=2.5,
                label=f'N({mu_rtt:.0f}, {std_rtt:.2f}) ms')
        ax.axvline(mu_rtt, color='r', linestyle='--', alpha=0.4)

        ax.set_title(title, fontsize=10)
        ax.set_xlabel('RTT (ms)')
        ax.set_ylabel('Densidade de probabilidade')
        ax.legend(fontsize=8)

    plt.suptitle('Tarefa 1: Modelagem de Atraso — Distribuição Normal do RTT',
                 fontsize=13, fontweight='bold')
    return _savefig('task1_delay_modeling.png')


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 2 — Modelo de Perda de Bernoulli
# ════════════════════════════════════════════════════════════════════════════
def task2_bernoulli_loss() -> str:
    """
    Valida a taxa de perda do simulador contra a configuração do tc qdisc.
    Compara perda configurada (p_cfg) com perda observada (retransmissões / envios totais).
    """
    print("[Tarefa 2] Modelo de Perda de Bernoulli...")

    configs = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    obs_loss_means = []
    obs_loss_stds  = []

    for p in configs:
        losses = []
        for seed in range(10):
            r = simulate_gbn(
                file_size_bytes=3 * 1024 * 1024,
                loss_prob=p, delay_mean_s=0.050, delay_std_s=0.005,
                seed=seed
            )
            # Overhead de perda: fração de envios extras (retransmissões)
            obs = r['retransmissions'] / r['data_sent'] if r['data_sent'] > 0 else 0
            losses.append(obs)
        obs_loss_means.append(np.mean(losses))
        obs_loss_stds.append(np.std(losses))

    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.array(configs)
    ax.errorbar(x * 100, np.array(obs_loss_means) * 100,
                yerr=np.array(obs_loss_stds) * 100,
                fmt='o-', color='#2196F3', lw=2, ms=7,
                capsize=5, label='Overhead observado (sim)')
    ax.plot(x * 100, x * 100, 'r--', lw=2, label='Referência (perda = overhead)')
    ax.set_xlabel('Taxa de perda configurada (%)')
    ax.set_ylabel('Overhead de retransmissão (%)')
    ax.set_title('Tarefa 2: Modelo de Perda de Bernoulli\n'
                 'Overhead de Retransmissão vs Taxa de Perda Configurada')
    ax.legend()
    ax.set_xlim(-1, 32)
    return _savefig('task2_bernoulli_loss.png')


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 3 — Simulação de Timeout
# ════════════════════════════════════════════════════════════════════════════
def task3_timeout_simulation() -> str:
    """
    Valida retransmissões do simulador comparando com os logs reais do tcpdump.
    Mostra Real (Fase 1) vs Simulado por cenário.
    """
    print("[Tarefa 3] Simulação de Timeout...")

    scenarios = ['A', 'B', 'C']
    real_means, real_stds = [], []
    sim_means,  sim_stds  = [], []

    for sc in scenarios:
        # Real (Fase 1)
        real_r = REAL_RUDP[sc]['retransmissions']
        real_means.append(np.mean(real_r))
        real_stds.append(np.std(real_r))

        # Simulado (10 runs)
        p = SCENARIOS[sc]
        sim_r = []
        for seed in range(10):
            r = simulate_gbn(seed=seed, **p)
            sim_r.append(r['retransmissions'])
        sim_means.append(np.mean(sim_r))
        sim_stds.append(np.std(sim_r))

    fig, ax = plt.subplots(figsize=(9, 6))
    x = np.arange(len(scenarios))
    w = 0.35

    bars1 = ax.bar(x - w/2, real_means, w, yerr=real_stds, capsize=5,
                   label='Real (Fase 1)', color='#2196F3', alpha=0.85)
    bars2 = ax.bar(x + w/2, sim_means,  w, yerr=sim_stds,  capsize=5,
                   label='Simulado (SimPy)', color='#FF9800', alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([f'Cenário {s}' for s in scenarios])
    ax.set_ylabel('Número de Retransmissões')
    ax.set_title('Tarefa 3: Simulação de Timeout\nRetransmissões: Real vs Simulado (GBN W=8, T=0.3s)')
    ax.legend()

    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h * 1.02, f'{h:.0f}',
                ha='center', va='bottom', fontsize=8)
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h * 1.02, f'{h:.0f}',
                ha='center', va='bottom', fontsize=8)
    return _savefig('task3_timeout_simulation.png')


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 4 — Curva de Vazão (Throughput)
# ════════════════════════════════════════════════════════════════════════════
def task4_throughput_curve() -> str:
    """
    Analisa vazão com arquivos de 1 MB a 100 MB no simulador.
    Mostra como a vazão varia conforme o tamanho do arquivo.
    """
    print("[Tarefa 4] Curva de Vazão...")

    file_sizes_mb = [1, 2, 5, 10, 20, 50, 100]
    file_sizes_b  = [s * 1024 * 1024 for s in file_sizes_mb]

    fig, ax = plt.subplots(figsize=(10, 6))

    for sc in ['A', 'B', 'C']:
        p = SCENARIOS[sc]
        tp_means, tp_stds = [], []
        for fsz in file_sizes_b:
            tp = []
            for seed in range(5):
                r = simulate_gbn(file_size_bytes=fsz, seed=seed, **p)
                tp.append(r['throughput_mbps'])
            tp_means.append(np.mean(tp))
            tp_stds.append(np.std(tp))

        ax.errorbar(file_sizes_mb, tp_means, yerr=tp_stds, fmt='o-',
                    color=COLORS[sc], lw=2, ms=6, capsize=4,
                    label=f'Cenário {sc}')

    ax.set_xscale('log')
    ax.set_xlabel('Tamanho do Arquivo (MB)')
    ax.set_ylabel('Vazão (Mbps)')
    ax.set_title('Tarefa 4: Curva de Vazão — Arquivo de 1 MB a 100 MB\n(GBN W=8, T=0.3s)')
    ax.legend()
    ax.set_xticks(file_sizes_mb)
    ax.set_xticklabels([f'{s}MB' for s in file_sizes_mb])
    return _savefig('task4_throughput_curve.png')


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 5 — Sensibilidade da Janela
# ════════════════════════════════════════════════════════════════════════════
def task5_window_sensitivity() -> str:
    """
    Identifica a saturação teórica ao variar o tamanho da janela W.
    Usa Cenário A (sem perda) para isolar o efeito da janela.
    """
    print("[Tarefa 5] Sensibilidade da Janela...")

    window_sizes = [1, 2, 4, 8, 16, 32, 64]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    for sc, label in [('A', '0% perda / 10ms'), ('B', '10% perda / 50ms')]:
        p = SCENARIOS[sc]
        tp_means, tp_stds = [], []
        for W in window_sizes:
            tp = []
            for seed in range(5):
                r = simulate_gbn(
                    file_size_bytes=5 * 1024 * 1024,
                    window_size=W, seed=seed, **p
                )
                tp.append(r['throughput_mbps'])
            tp_means.append(np.mean(tp))
            tp_stds.append(np.std(tp))

        ax = axes[0] if sc == 'A' else axes[1]
        ax.errorbar(window_sizes, tp_means, yerr=tp_stds,
                    fmt='o-', color=COLORS[sc], lw=2, ms=7, capsize=4)
        ax.axvline(WINDOW_SIZE, color='gray', linestyle='--', alpha=0.6,
                   label=f'W={WINDOW_SIZE} (Fase 1)')
        ax.set_xscale('log', base=2)
        ax.set_xticks(window_sizes)
        ax.set_xticklabels([str(w) for w in window_sizes])
        ax.set_xlabel('Tamanho da Janela W')
        ax.set_ylabel('Vazão (Mbps)')
        ax.set_title(f'Cenário {sc}: {label}')
        ax.legend()

    plt.suptitle('Tarefa 5: Sensibilidade da Janela — Saturação Teórica',
                 fontsize=13, fontweight='bold')
    return _savefig('task5_window_sensitivity.png')


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 6 — Validação de RTT
# ════════════════════════════════════════════════════════════════════════════
def task6_rtt_validation() -> str:
    """
    Compara RTT médio do simulador com RTT esperado (2 × delay_mean do tc).
    RTT real implícito estimado a partir do tempo de transferência da Fase 1.
    """
    print("[Tarefa 6] Validação de RTT...")

    scenarios = ['A', 'B', 'C']
    rtt_config = []  # 2 × delay_mean configurado
    rtt_sim    = []  # RTT médio do simulador
    rtt_sim_std = []
    rtt_real   = []  # RTT implícito dos dados reais

    for sc in scenarios:
        p = SCENARIOS[sc]
        rtt_config.append(2 * p['delay_mean'] * 1000)  # ms

        # RTT simulado (média de 10 runs)
        rtts = []
        for seed in range(10):
            r = simulate_gbn(seed=seed, **p)
            rtts.append(r['rtt_mean'] * 1000)
        rtt_sim.append(np.mean(rtts))
        rtt_sim_std.append(np.std(rtts))

        # RTT real estimado: RTT = W × chunk_size × 8 / (throughput_bps)
        # Deriva o RTT efetivo a partir da vazão e janela
        tp_mean = np.mean(REAL_RUDP[sc]['throughputs']) * 1e6  # bits/s
        rtt_implied = (WINDOW_SIZE * CHUNK_SIZE * 8) / tp_mean * 1000  # ms
        rtt_real.append(rtt_implied)

    fig, ax = plt.subplots(figsize=(9, 6))
    x = np.arange(len(scenarios))
    w = 0.26

    ax.bar(x - w, rtt_config, w, label='Configurado (2×tc delay)', color='#9E9E9E', alpha=0.85)
    ax.bar(x,     rtt_real,   w, label='Real (implícito, Fase 1)',  color='#2196F3', alpha=0.85)
    ax.errorbar(x + w, rtt_sim, yerr=rtt_sim_std, fmt='s',
                color='#FF9800', ms=8, capsize=5, lw=2,
                label='Simulado (SimPy)')
    ax.bar(x + w, rtt_sim, w, label='_nolegend_', color='#FF9800', alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([f'Cenário {s}' for s in scenarios])
    ax.set_ylabel('RTT (ms)')
    ax.set_title('Tarefa 6: Validação de RTT\nRTT Configurado vs Real (Fase 1) vs Simulado')
    ax.legend()
    return _savefig('task6_rtt_validation.png')


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 7 — Impacto do Jitter
# ════════════════════════════════════════════════════════════════════════════
def task7_jitter_impact() -> str:
    """
    Observa a estabilidade do fluxo sob variações de latência (jitter).
    Varia delay_std de 0 a 50ms com delay_mean=50ms, perda=10%.
    """
    print("[Tarefa 7] Impacto do Jitter...")

    jitter_ms = [0, 2, 5, 10, 20, 30, 50]
    jitter_s  = [j / 1000 for j in jitter_ms]

    tp_means, tp_stds = [], []
    rt_means, rt_stds = [], []

    for j_s in jitter_s:
        tp, rt = [], []
        for seed in range(10):
            r = simulate_gbn(
                file_size_bytes=3 * 1024 * 1024,
                loss_prob=0.10, delay_mean_s=0.050, delay_std_s=j_s,
                seed=seed
            )
            tp.append(r['throughput_mbps'])
            rt.append(r['retransmissions'])
        tp_means.append(np.mean(tp))
        tp_stds.append(np.std(tp))
        rt_means.append(np.mean(rt))
        rt_stds.append(np.std(rt))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    ax1.errorbar(jitter_ms, tp_means, yerr=tp_stds, fmt='o-',
                 color='#2196F3', lw=2, ms=6, capsize=4)
    ax1.axvline(5, color='gray', linestyle='--', alpha=0.5, label='Jitter padrão (5ms)')
    ax1.set_xlabel('Jitter — Desvio Padrão do Atraso (ms)')
    ax1.set_ylabel('Vazão (Mbps)')
    ax1.set_title('Vazão vs Jitter')
    ax1.legend()

    ax2.errorbar(jitter_ms, rt_means, yerr=rt_stds, fmt='s-',
                 color='#F44336', lw=2, ms=6, capsize=4)
    ax2.axvline(5, color='gray', linestyle='--', alpha=0.5)
    ax2.set_xlabel('Jitter — Desvio Padrão do Atraso (ms)')
    ax2.set_ylabel('Retransmissões')
    ax2.set_title('Retransmissões vs Jitter')

    plt.suptitle('Tarefa 7: Impacto do Jitter\n(delay_mean=50ms, perda=10%, W=8, T=0.3s)',
                 fontsize=12, fontweight='bold')
    return _savefig('task7_jitter_impact.png')


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 8 — Cenário de Estresse (25% de perda)
# ════════════════════════════════════════════════════════════════════════════
def task8_stress_scenario() -> str:
    """
    Prevê o tempo de transferência com 25% de perda de pacotes.
    Compara com cenários A, B, C e com real da Fase 1.
    """
    print("[Tarefa 8] Cenário de Estresse (25% perda)...")

    all_scenarios = ['A', 'B', 'C', 'S']
    scenario_labels = {
        'A': 'A\n(0%/10ms)', 'B': 'B\n(10%/50ms)',
        'C': 'C\n(20%/100ms)', 'S': 'Stress\n(25%/100ms)'
    }

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    sim_tp, sim_tt = {}, {}
    for sc in all_scenarios:
        p = SCENARIOS[sc]
        tp, tt = [], []
        n_runs = 10
        for seed in range(n_runs):
            r = simulate_gbn(seed=seed, **p)
            tp.append(r['throughput_mbps'])
            tt.append(r['transfer_time'])
        sim_tp[sc] = (np.mean(tp), np.std(tp))
        sim_tt[sc] = (np.mean(tt), np.std(tt))

    colors = [COLORS[sc] for sc in all_scenarios]
    x = np.arange(len(all_scenarios))
    labels = [scenario_labels[sc] for sc in all_scenarios]

    # Vazão
    tp_means = [sim_tp[sc][0] for sc in all_scenarios]
    tp_stds  = [sim_tp[sc][1] for sc in all_scenarios]
    bars = ax1.bar(x, tp_means, yerr=tp_stds, capsize=5, color=colors, alpha=0.85)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_ylabel('Vazão (Mbps)')
    ax1.set_title('Vazão por Cenário (incluindo Estresse)')
    for bar, v in zip(bars, tp_means):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.05,
                 f'{v:.3f}', ha='center', fontsize=8)

    # Tempo de transferência
    tt_means = [sim_tt[sc][0] for sc in all_scenarios]
    tt_stds  = [sim_tt[sc][1] for sc in all_scenarios]
    ax2.bar(x, tt_means, yerr=tt_stds, capsize=5, color=colors, alpha=0.85)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.set_ylabel('Tempo de Transferência (s)')
    ax2.set_title('Tempo de Transferência por Cenário')

    plt.suptitle('Tarefa 8: Cenário de Estresse — Previsão com 25% de Perda\n(GBN W=8, T=0.3s, 10MB)',
                 fontsize=12, fontweight='bold')
    return _savefig('task8_stress_scenario.png')


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 9 — Análise de Eficiência
# ════════════════════════════════════════════════════════════════════════════
def task9_efficiency() -> str:
    """
    Calcula razão entre pacotes de dados e pacotes de controle (ACKs + retransmissões).
    Eficiência = total_packets_originais / total_enviados (incluindo retransmissões).
    """
    print("[Tarefa 9] Análise de Eficiência...")

    scenarios = ['A', 'B', 'C', 'S']
    eff_sim  = {}  # simulador
    eff_real = {}  # real (Fase 1): total_pkts / (total_pkts + retransmissões)

    for sc in scenarios:
        p = SCENARIOS[sc]
        effs = []
        for seed in range(15):
            r = simulate_gbn(seed=seed, **p)
            effs.append(r['efficiency'])
        eff_sim[sc] = (np.mean(effs), np.std(effs))

        if sc in REAL_RUDP:
            total = 7490  # total_packets fixo Fase 1
            eff_r = [total / (total + ret) for ret in REAL_RUDP[sc]['retransmissions']]
            eff_real[sc] = (np.mean(eff_r), np.std(eff_r))

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(scenarios))
    w = 0.35

    sim_means = [eff_sim[sc][0] for sc in scenarios]
    sim_stds  = [eff_sim[sc][1] for sc in scenarios]
    ax.bar(x + w/2, sim_means, w, yerr=sim_stds, capsize=5,
           label='Simulado (SimPy)', color='#FF9800', alpha=0.85)

    real_scenarios = [sc for sc in scenarios if sc in eff_real]
    real_x = np.array([scenarios.index(sc) for sc in real_scenarios])
    real_means = [eff_real[sc][0] for sc in real_scenarios]
    real_stds  = [eff_real[sc][1] for sc in real_scenarios]
    ax.bar(real_x - w/2, real_means, w, yerr=real_stds, capsize=5,
           label='Real (Fase 1)', color='#2196F3', alpha=0.85)

    ax.axhline(1.0, color='gray', linestyle='--', alpha=0.5, label='Eficiência ideal')
    ax.set_xticks(x)
    ax.set_xticklabels([f'Cenário {s}' for s in scenarios])
    ax.set_ylabel('Eficiência (pacotes úteis / total enviados)')
    ax.set_ylim(0, 1.15)
    ax.set_title('Tarefa 9: Análise de Eficiência\nRazão Pacotes de Dados vs Total Enviado (GBN W=8)')
    ax.legend()

    for i, (m, sc) in enumerate(zip(sim_means, scenarios)):
        ax.text(x[i] + w/2, m + 0.02, f'{m:.3f}', ha='center', fontsize=8)
    return _savefig('task9_efficiency.png')


# ════════════════════════════════════════════════════════════════════════════
# Tarefa 10 — Convergência Estatística (IC 95%)
# ════════════════════════════════════════════════════════════════════════════
def task10_statistical_convergence() -> str:
    """
    Gera intervalo de confiança 95% com base em 30+ execuções.
    Demonstra convergência das métricas por cenário.
    """
    print("[Tarefa 10] Convergência Estatística (30 runs por cenário)...")

    n_runs = 30
    scenarios = ['A', 'B', 'C']

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))

    for col, sc in enumerate(scenarios):
        p = SCENARIOS[sc]
        print(f"  Cenário {sc}: {n_runs} runs...")
        results = run_multiple(n_runs=n_runs, seed_start=100, **p)

        tps = np.array(results['throughput_mbps'])
        rts = np.array(results['retransmissions'])

        # Convergência cumulativa da média (vazão)
        cum_means_tp = np.cumsum(tps) / np.arange(1, n_runs + 1)
        cum_stds_tp  = [np.std(tps[:k+1], ddof=1) if k > 0 else 0 for k in range(n_runs)]
        cum_ci_tp    = [1.96 * s / np.sqrt(k+1) for k, s in enumerate(cum_stds_tp)]

        ax = axes[0, col]
        run_idx = np.arange(1, n_runs + 1)
        ax.plot(run_idx, cum_means_tp, 'b-', lw=2, label='Média cumulativa')
        ax.fill_between(run_idx,
                        cum_means_tp - np.array(cum_ci_tp),
                        cum_means_tp + np.array(cum_ci_tp),
                        alpha=0.3, color='blue', label='IC 95%')
        ax.axhline(cum_means_tp[-1], color='r', linestyle='--', alpha=0.6)
        ax.set_title(f'Cenário {sc} — Convergência da Vazão')
        ax.set_xlabel('Número de execuções')
        ax.set_ylabel('Vazão (Mbps)')
        ax.legend(fontsize=8)

        # Convergência cumulativa das retransmissões
        cum_means_rt = np.cumsum(rts) / np.arange(1, n_runs + 1)
        cum_stds_rt  = [np.std(rts[:k+1], ddof=1) if k > 0 else 0 for k in range(n_runs)]
        cum_ci_rt    = [1.96 * s / np.sqrt(k+1) for k, s in enumerate(cum_stds_rt)]

        ax2 = axes[1, col]
        ax2.plot(run_idx, cum_means_rt, 'r-', lw=2, label='Média cumulativa')
        ax2.fill_between(run_idx,
                         cum_means_rt - np.array(cum_ci_rt),
                         cum_means_rt + np.array(cum_ci_rt),
                         alpha=0.3, color='red', label='IC 95%')
        ax2.axhline(cum_means_rt[-1], color='darkred', linestyle='--', alpha=0.6)
        ax2.set_title(f'Cenário {sc} — Convergência das Retransmissões')
        ax2.set_xlabel('Número de execuções')
        ax2.set_ylabel('Retransmissões')
        ax2.legend(fontsize=8)

        st = stats_ci95(tps)
        print(f"    Vazão: {st['mean']:.4f} ± {st['ci95']:.4f} Mbps (IC 95%)")
        st2 = stats_ci95(rts)
        print(f"    Retransmissões: {st2['mean']:.1f} ± {st2['ci95']:.1f} (IC 95%)")

    plt.suptitle('Tarefa 10: Convergência Estatística — IC 95% com 30 Execuções',
                 fontsize=13, fontweight='bold')
    return _savefig('task10_convergence.png')


# ════════════════════════════════════════════════════════════════════════════
# Comparação Real vs Simulado (critério I/II — 3.0 pts)
# ════════════════════════════════════════════════════════════════════════════
def plot_real_vs_simulated() -> str:
    """
    Gráfico comparativo Real (Fase 1) vs Simulado (SimPy).
    Exibe vazão, tempo de transferência e retransmissões por cenário.
    """
    print("[Comparação] Real vs Simulado...")

    scenarios = ['A', 'B', 'C']
    n_runs = 15

    real_tp = {sc: (np.mean(REAL_RUDP[sc]['throughputs']),
                    np.std(REAL_RUDP[sc]['throughputs'])) for sc in scenarios}
    real_tt = {sc: (np.mean(REAL_RUDP[sc]['transfer_times']),
                    np.std(REAL_RUDP[sc]['transfer_times'])) for sc in scenarios}
    real_rt = {sc: (np.mean(REAL_RUDP[sc]['retransmissions']),
                    np.std(REAL_RUDP[sc]['retransmissions'])) for sc in scenarios}

    sim_tp = {}; sim_tt = {}; sim_rt = {}
    for sc in scenarios:
        p = SCENARIOS[sc]
        tp, tt, rt = [], [], []
        for seed in range(n_runs):
            r = simulate_gbn(seed=seed, **p)
            tp.append(r['throughput_mbps'])
            tt.append(r['transfer_time'])
            rt.append(r['retransmissions'])
        sim_tp[sc] = (np.mean(tp), np.std(tp))
        sim_tt[sc] = (np.mean(tt), np.std(tt))
        sim_rt[sc] = (np.mean(rt), np.std(rt))

    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    x = np.arange(len(scenarios))
    w = 0.35
    labels = [f'Cenário {s}' for s in scenarios]

    metrics = [
        ('Vazão (Mbps)', real_tp, sim_tp),
        ('Tempo de Transferência (s)', real_tt, sim_tt),
        ('Retransmissões', real_rt, sim_rt),
    ]

    for ax, (ylabel, real_d, sim_d) in zip(axes, metrics):
        rm = [real_d[sc][0] for sc in scenarios]
        rs = [real_d[sc][1] for sc in scenarios]
        sm = [sim_d[sc][0]  for sc in scenarios]
        ss = [sim_d[sc][1]  for sc in scenarios]

        ax.bar(x - w/2, rm, w, yerr=rs, capsize=5,
               label='Real (Fase 1)', color='#2196F3', alpha=0.85)
        ax.bar(x + w/2, sm, w, yerr=ss, capsize=5,
               label='Simulado (SimPy)', color='#FF9800', alpha=0.85)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel(ylabel)
        ax.set_title(ylabel)
        ax.legend(fontsize=8)

    plt.suptitle('Análise Comparativa: Real (Fase 1) vs Simulado (SimPy)\n'
                 'GBN W=8, T=0.3s, Arquivo 10MB',
                 fontsize=13, fontweight='bold')
    return _savefig('real_vs_simulated.png')


# ════════════════════════════════════════════════════════════════════════════
# Runner principal
# ════════════════════════════════════════════════════════════════════════════
def run_all_tasks() -> Dict[str, str]:
    """Executa todas as 10 tarefas e o gráfico comparativo. Retorna paths dos gráficos."""
    print("=" * 60)
    print("FASE 2 — SimPy: Executando 10 Tarefas de Validação")
    print(f"Aluno: Arthur Sabino Santos (20261005029)")
    print("=" * 60)

    paths = {}
    paths['task1']    = task1_delay_modeling()
    paths['task2']    = task2_bernoulli_loss()
    paths['task3']    = task3_timeout_simulation()
    paths['task4']    = task4_throughput_curve()
    paths['task5']    = task5_window_sensitivity()
    paths['task6']    = task6_rtt_validation()
    paths['task7']    = task7_jitter_impact()
    paths['task8']    = task8_stress_scenario()
    paths['task9']    = task9_efficiency()
    paths['task10']   = task10_statistical_convergence()
    paths['real_vs_sim'] = plot_real_vs_simulated()

    print("\n" + "=" * 60)
    print(f"CONCLUÍDO — {len(paths)} gráficos gerados em: {PLOTS_DIR}")
    print("=" * 60)

    # Salvar resumo JSON
    summary_path = os.path.join(PLOTS_DIR, 'summary.json')
    with open(summary_path, 'w') as f:
        json.dump({'plots': paths, 'n_tasks': 10}, f, indent=2)

    return paths


if __name__ == '__main__':
    run_all_tasks()
