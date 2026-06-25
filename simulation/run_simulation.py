"""
run_simulation.py — Ponto de entrada da Fase 2
Fase 2: Modelagem Estocástica — PPGCC/UFPI 2026-1

Uso:
    python simulation/run_simulation.py

Requer: pip install simpy numpy matplotlib seaborn scipy
"""

import sys
import os

# Adicionar diretório da simulação ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulator import simulate_gbn, run_multiple, stats_ci95, SCENARIOS
from tasks import run_all_tasks


def demo_single_run():
    """Demonstra uma única execução do simulador para cada cenário."""
    print("\n── Demo: Execução Única por Cenário ──")
    print(f"{'Cenário':<10} {'Vazão (Mbps)':<15} {'Tempo (s)':<12} "
          f"{'Retransmissões':<18} {'Eficiência':<12}")
    print("-" * 67)
    for sc, p in SCENARIOS.items():
        r = simulate_gbn(seed=42, **p)
        print(f"  {sc:<8} {r['throughput_mbps']:>12.4f}   {r['transfer_time']:>10.2f}   "
              f"{r['retransmissions']:>16}   {r['efficiency']:>10.4f}")


def demo_confidence_intervals():
    """Mostra IC 95% para cada cenário com 30 execuções."""
    print("\n── IC 95% — 30 Execuções por Cenário ──")
    for sc, p in [('A', SCENARIOS['A']), ('B', SCENARIOS['B']), ('C', SCENARIOS['C'])]:
        print(f"\nCenário {sc} ({p['loss_prob']*100:.0f}% perda / {p['delay_mean_s']*1000:.0f}ms):")
        res = run_multiple(n_runs=30, seed_start=0, **p)
        for metric in ['throughput_mbps', 'retransmissions', 'rtt_mean']:
            st = stats_ci95(res[metric])
            unit = 'Mbps' if 'throughput' in metric else ('s' if 'rtt' in metric else '')
            print(f"  {metric:<22}: {st['mean']:.4f} ± {st['ci95']:.4f} {unit}  "
                  f"(σ={st['std']:.4f})")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Fase 2 — SimPy GBN Simulator')
    parser.add_argument('--demo', action='store_true', help='Executa demo rápida')
    parser.add_argument('--ci',   action='store_true', help='Calcula IC 95% (30 runs)')
    parser.add_argument('--all',  action='store_true', help='Executa todas as 10 tarefas')
    args = parser.parse_args()

    if args.demo or not any([args.demo, args.ci, args.all]):
        demo_single_run()

    if args.ci:
        demo_confidence_intervals()

    if args.all:
        run_all_tasks()
    elif not args.ci:
        print("\nDica: use --all para gerar todos os gráficos das 10 tarefas.")
        print("      use --ci  para calcular intervalos de confiança.")
