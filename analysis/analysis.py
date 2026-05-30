#!/usr/bin/env python3
"""
analysis.py — Análise estatística e geração de gráficos
PPGCC/UFPI — Projeto de Redes de Computadores 2026-1

Gera:
  - throughput.html/png      (Plotly + Seaborn)
  - transfer_time.html/png
  - retransmissions.html/png
  - cross_validation.html/png
  - heatmap.png
  - cross_validation_table.csv
"""

import json
import os
import glob
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

LOG_DIR  = os.environ.get("LOG_DIR",  "/data/logs")
CSV_DIR  = os.environ.get("CSV_DIR",  "/data/csv")
PLOT_DIR = os.environ.get("PLOT_DIR", "/data/plots")
os.makedirs(PLOT_DIR, exist_ok=True)

SCENARIOS = ["A", "B", "C"]
SCENARIO_LABELS = {
    "A": "A (0%/10ms)",
    "B": "B (10%/50ms)",
    "C": "C (20%/100ms)",
}
FILE_SIZE_MB = 10.0


# ──────────────────────────────────────────────────────────
#  Carrega métricas dos arquivos JSONL
# ──────────────────────────────────────────────────────────
def load_metrics(filepath: str) -> list[dict]:
    records = []
    if not os.path.exists(filepath):
        return records
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


# ──────────────────────────────────────────────────────────
#  Carrega CSVs do tcpdump e agrega por cenário/protocolo
# ──────────────────────────────────────────────────────────
def load_tcpdump_stats() -> dict:
    """
    Retorna dict[scenario][protocol] = {bytes, duration, packets}
    """
    stats = {s: {"TCP": [], "RUDP": []} for s in SCENARIOS}

    for scenario in SCENARIOS:
        for proto_key, proto_label in [("tcp", "TCP"), ("rudp", "RUDP")]:
            pattern = os.path.join(CSV_DIR, f"scenario_{scenario}_{proto_key}_rep*.csv")
            for csv_file in sorted(glob.glob(pattern)):
                try:
                    df = pd.read_csv(csv_file)
                    if df.empty:
                        continue
                    total_bytes = df["length"].sum()
                    duration    = df["timestamp"].max() - df["timestamp"].min()
                    num_pkts    = len(df)
                    stats[scenario][proto_label].append({
                        "bytes": total_bytes,
                        "duration": duration,
                        "packets": num_pkts,
                    })
                except Exception as e:
                    print(f"[warn] {csv_file}: {e}")

    return stats


# ──────────────────────────────────────────────────────────
#  Constrói DataFrame consolidado com médias e desvios
# ──────────────────────────────────────────────────────────
def build_dataframe() -> pd.DataFrame:
    tcp_recs  = load_metrics(os.path.join(LOG_DIR, "tcp_client_metrics.jsonl"))
    rudp_recs = load_metrics(os.path.join(LOG_DIR, "rudp_client_metrics.jsonl"))

    rows = []
    for proto, records in [("TCP", tcp_recs), ("R-UDP/GBN", rudp_recs)]:
        for s in SCENARIOS:
            subset = [r for r in records if r.get("scenario") == s]
            if not subset:
                continue
            thr   = [r.get("client_throughput_mbps") or r.get("throughput_mbps", 0) for r in subset]
            times = [r.get("client_elapsed_sec") or r.get("elapsed_sec", 0) for r in subset]
            retx  = [r.get("retransmissions", 0) for r in subset]
            rows.append({
                "protocol": proto,
                "scenario": s,
                "scenario_label": SCENARIO_LABELS[s],
                "throughput_mean": np.mean(thr),
                "throughput_std":  np.std(thr, ddof=1) if len(thr) > 1 else 0,
                "time_mean":  np.mean(times),
                "time_std":   np.std(times, ddof=1) if len(times) > 1 else 0,
                "retx_mean":  np.mean(retx),
                "retx_std":   np.std(retx, ddof=1) if len(retx) > 1 else 0,
                "n": len(subset),
            })

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────
#  Gráfico 1 — Throughput (Plotly + Seaborn)
# ──────────────────────────────────────────────────────────
def plot_throughput(df: pd.DataFrame):
    fig = go.Figure()
    colors = {"TCP": "#1f77b4", "R-UDP/GBN": "#d62728"}

    for proto in ["TCP", "R-UDP/GBN"]:
        sub = df[df["protocol"] == proto]
        fig.add_trace(go.Bar(
            name=proto,
            x=sub["scenario_label"].tolist(),
            y=sub["throughput_mean"].tolist(),
            error_y=dict(type="data", array=sub["throughput_std"].tolist()),
            marker_color=colors[proto],
        ))

    fig.update_layout(
        title="Throughput Médio por Cenário — TCP vs. R-UDP/GBN",
        xaxis_title="Cenário de Rede",
        yaxis_title="Throughput (Mbps)",
        barmode="group",
        legend_title="Protocolo",
        template="plotly_white",
    )
    fig.write_html(os.path.join(PLOT_DIR, "throughput.html"))
    fig.write_image(os.path.join(PLOT_DIR, "throughput.png"), width=900, height=500)

    # Seaborn
    fig2, ax = plt.subplots(figsize=(8, 4))
    sns.barplot(data=df, x="scenario_label", y="throughput_mean",
                hue="protocol", errorbar=None,
                palette={"TCP": "#1f77b4", "R-UDP/GBN": "#d62728"}, ax=ax)
    for i, row in df.iterrows():
        col_idx = ["TCP", "R-UDP/GBN"].index(row["protocol"])
        ax.errorbar(
            x=i % len(SCENARIOS) + (col_idx - 0.5) * 0.4,
            y=row["throughput_mean"],
            yerr=row["throughput_std"],
            fmt="none", color="black", capsize=4,
        )
    ax.set_title("Throughput Médio (Seaborn) — TCP vs. R-UDP/GBN")
    ax.set_xlabel("Cenário de Rede")
    ax.set_ylabel("Throughput (Mbps)")
    plt.tight_layout()
    fig2.savefig(os.path.join(PLOT_DIR, "throughput_seaborn.png"), dpi=150)
    plt.close(fig2)
    print("[plot] throughput OK")


# ──────────────────────────────────────────────────────────
#  Gráfico 2 — Tempo de Transferência
# ──────────────────────────────────────────────────────────
def plot_transfer_time(df: pd.DataFrame):
    fig = go.Figure()
    colors = {"TCP": "#1f77b4", "R-UDP/GBN": "#d62728"}

    for proto in ["TCP", "R-UDP/GBN"]:
        sub = df[df["protocol"] == proto]
        fig.add_trace(go.Bar(
            name=proto,
            x=sub["scenario_label"].tolist(),
            y=sub["time_mean"].tolist(),
            error_y=dict(type="data", array=sub["time_std"].tolist()),
            marker_color=colors[proto],
        ))

    fig.update_layout(
        title="Tempo Médio de Transferência por Cenário",
        xaxis_title="Cenário de Rede",
        yaxis_title="Tempo (s)",
        barmode="group",
        template="plotly_white",
    )
    fig.write_html(os.path.join(PLOT_DIR, "transfer_time.html"))
    fig.write_image(os.path.join(PLOT_DIR, "transfer_time.png"), width=900, height=500)
    print("[plot] transfer_time OK")


# ──────────────────────────────────────────────────────────
#  Gráfico 3 — Retransmissões R-UDP/GBN
# ──────────────────────────────────────────────────────────
def plot_retransmissions(df: pd.DataFrame):
    sub = df[df["protocol"] == "R-UDP/GBN"]
    fig = go.Figure(go.Bar(
        x=sub["scenario_label"].tolist(),
        y=sub["retx_mean"].tolist(),
        error_y=dict(type="data", array=sub["retx_std"].tolist()),
        marker_color="#d62728",
        name="Retransmissões",
    ))
    fig.update_layout(
        title="Retransmissões Médias — R-UDP/GBN por Cenário",
        xaxis_title="Cenário de Rede",
        yaxis_title="Nº de Retransmissões",
        template="plotly_white",
    )
    fig.write_html(os.path.join(PLOT_DIR, "retransmissions.html"))
    fig.write_image(os.path.join(PLOT_DIR, "retransmissions.png"), width=900, height=500)
    print("[plot] retransmissions OK")


# ──────────────────────────────────────────────────────────
#  Gráfico 4 — Validação Cruzada (App vs TCPDump)
# ──────────────────────────────────────────────────────────
def plot_cross_validation(df: pd.DataFrame):
    tcpdump_stats = load_tcpdump_stats()
    app_bytes_mb  = FILE_SIZE_MB

    rows = []
    for proto_key, proto_label in [("TCP", "TCP"), ("RUDP", "R-UDP/GBN")]:
        for scenario in SCENARIOS:
            captures = tcpdump_stats[scenario][proto_key]
            if not captures:
                continue
            net_bytes_mb = np.mean([c["bytes"] for c in captures]) / 1e6
            overhead_pct = (net_bytes_mb - app_bytes_mb) / app_bytes_mb * 100
            rows.append({
                "scenario": SCENARIO_LABELS[scenario],
                "protocol": proto_label,
                "app_bytes_MB": app_bytes_mb,
                "net_bytes_MB": round(net_bytes_mb, 2),
                "overhead_pct": round(overhead_pct, 2),
            })

    if not rows:
        print("[warn] Sem dados de tcpdump para validação cruzada")
        return

    cv_df = pd.DataFrame(rows)
    cv_df.to_csv(os.path.join(PLOT_DIR, "cross_validation_table.csv"), index=False)

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=["Volume: App vs TCPDump (MB)", "Overhead de Rede (%)"])

    colors_proto = {"TCP": "#1f77b4", "R-UDP/GBN": "#d62728"}
    for proto in ["TCP", "R-UDP/GBN"]:
        sub = cv_df[cv_df["protocol"] == proto]
        fig.add_trace(go.Bar(
            name=f"{proto} — App",
            x=sub["scenario"].tolist(),
            y=sub["app_bytes_MB"].tolist(),
            marker_color=colors_proto[proto],
            opacity=0.5,
            showlegend=True,
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            name=f"{proto} — TCPDump",
            x=sub["scenario"].tolist(),
            y=sub["net_bytes_MB"].tolist(),
            marker_color=colors_proto[proto],
            opacity=1.0,
            showlegend=True,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            name=f"{proto} — Overhead",
            x=sub["scenario"].tolist(),
            y=sub["overhead_pct"].tolist(),
            mode="lines+markers",
            marker=dict(color=colors_proto[proto]),
            line=dict(color=colors_proto[proto]),
        ), row=1, col=2)

    fig.update_layout(
        title="Validação Cruzada: Aplicação vs. TCPDump",
        template="plotly_white",
        barmode="group",
    )
    fig.write_html(os.path.join(PLOT_DIR, "cross_validation.html"))
    fig.write_image(os.path.join(PLOT_DIR, "cross_validation.png"), width=1100, height=500)
    print("[plot] cross_validation OK")
    print(cv_df.to_string(index=False))


# ──────────────────────────────────────────────────────────
#  Gráfico 5 — Heatmap comparativo
# ──────────────────────────────────────────────────────────
def plot_heatmap(df: pd.DataFrame):
    pivot_thr  = df.pivot(index="protocol", columns="scenario", values="throughput_mean")
    pivot_time = df.pivot(index="protocol", columns="scenario", values="time_mean")

    fig, axes = plt.subplots(1, 2, figsize=(12, 3))
    for ax, data, title in [
        (axes[0], pivot_thr,  "Throughput Médio (Mbps)"),
        (axes[1], pivot_time, "Tempo Médio (s)"),
    ]:
        sns.heatmap(data, annot=True, fmt=".2f", cmap="YlOrRd",
                    linewidths=0.5, ax=ax, cbar=True)
        ax.set_title(title)
        ax.set_xlabel("Cenário")
        ax.set_ylabel("Protocolo")

    plt.suptitle("Comparação de Desempenho — TCP vs. R-UDP/GBN", fontsize=13)
    plt.tight_layout()
    fig.savefig(os.path.join(PLOT_DIR, "heatmap.png"), dpi=150)
    plt.close(fig)
    print("[plot] heatmap OK")


# ──────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Análise Estatística — PPGCC/UFPI ===\n")
    df = build_dataframe()
    if df.empty:
        print("[ERRO] Nenhuma métrica encontrada. Execute os testes primeiro.")
        raise SystemExit(1)

    print(df[["protocol", "scenario", "throughput_mean", "throughput_std",
              "time_mean", "time_std", "retx_mean", "n"]].to_string(index=False))
    print()

    plot_throughput(df)
    plot_transfer_time(df)
    plot_retransmissions(df)
    plot_cross_validation(df)
    plot_heatmap(df)

    print(f"\nGráficos salvos em: {PLOT_DIR}")
