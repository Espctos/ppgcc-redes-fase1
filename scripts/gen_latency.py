import json, os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import seaborn as sns
import matplotlib.pyplot as plt

LOG_DIR  = "/data/logs"
PLOT_DIR = "/data/plots"
SCENARIOS = ["A", "B", "C"]
LABELS    = {"A": "A (0%/10ms)", "B": "B (10%/50ms)", "C": "C (20%/100ms)"}
TOTAL_PKT = 7490  # pacotes GBN por transferência
COLORS    = {"TCP": "#1f77b4", "R-UDP/GBN": "#d62728"}

def load_jsonl(path):
    recs = []
    if not os.path.exists(path): return recs
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try: recs.append(json.loads(line))
                except: pass
    return recs

tcp_recs  = load_jsonl(os.path.join(LOG_DIR, "tcp_client_metrics.jsonl"))
rudp_recs = load_jsonl(os.path.join(LOG_DIR, "rudp_client_metrics.jsonl"))

# Latência efetiva = tempo_total / num_pacotes * 1000 (ms por pacote)
rows = []
for proto, recs in [("TCP", tcp_recs), ("R-UDP/GBN", rudp_recs)]:
    for s in SCENARIOS:
        sub = [r for r in recs if r.get("scenario") == s]
        if not sub: continue
        times = [r.get("client_elapsed_sec") or r.get("elapsed_sec", 0) for r in sub]
        # Para TCP: estima nº de segmentos por bytes/MSS (1460B)
        if proto == "TCP":
            n_pkts = 10*1024*1024 / 1460
        else:
            n_pkts = TOTAL_PKT
        latencies = [(t / n_pkts) * 1000 for t in times]
        rows.append({
            "protocol": proto, "scenario": s, "label": LABELS[s],
            "lat_mean": np.mean(latencies),
            "lat_std":  np.std(latencies, ddof=1) if len(latencies)>1 else 0,
        })

df = pd.DataFrame(rows)

# --- Plotly ---
fig = go.Figure()
for proto in ["TCP", "R-UDP/GBN"]:
    sub = df[df["protocol"] == proto]
    fig.add_trace(go.Bar(
        name=proto,
        x=sub["label"].tolist(),
        y=sub["lat_mean"].tolist(),
        error_y=dict(type="data", array=sub["lat_std"].tolist()),
        marker_color=COLORS[proto]
    ))
fig.update_layout(
    title="Latência Efetiva por Pacote (ms) — TCP vs. R-UDP/GBN",
    xaxis_title="Cenário de Rede",
    yaxis_title="Latência por Pacote (ms)",
    barmode="group", template="plotly_white", legend_title="Protocolo"
)
fig.write_html(os.path.join(PLOT_DIR, "latency.html"))
fig.write_image(os.path.join(PLOT_DIR, "latency.png"), width=900, height=500)

# --- Seaborn ---
fig2, ax = plt.subplots(figsize=(9, 4))
sns.barplot(data=df, x="label", y="lat_mean", hue="protocol",
            errorbar=None, palette=COLORS, ax=ax)
ax.set_title("Latência Efetiva por Pacote — TCP vs. R-UDP/GBN (Seaborn)")
ax.set_xlabel("Cenário de Rede")
ax.set_ylabel("Latência por Pacote (ms)")
ax.legend(title="Protocolo")
plt.tight_layout()
fig2.savefig(os.path.join(PLOT_DIR, "latency_seaborn.png"), dpi=150)
plt.close(fig2)

print("Latências calculadas:")
print(df[["protocol","scenario","lat_mean","lat_std"]].to_string(index=False))
print("Graficos salvos: latency.png, latency_seaborn.png, latency.html")
