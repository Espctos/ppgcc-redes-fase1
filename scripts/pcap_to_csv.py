#!/usr/bin/env python3
"""
pcap_to_csv.py — Converte .pcap para CSV usando Scapy
Uso: python3 pcap_to_csv.py <input.pcap> <output.csv>
"""

import sys
import csv
from scapy.all import rdpcap, IP, TCP, UDP

def pcap_to_csv(pcap_path: str, csv_path: str):
    pkts = rdpcap(pcap_path)
    rows = []
    for pkt in pkts:
        if not pkt.haslayer(IP):
            continue
        ip  = pkt[IP]
        proto = "other"
        sport = dport = 0
        if pkt.haslayer(TCP):
            proto = "TCP"
            sport = pkt[TCP].sport
            dport = pkt[TCP].dport
        elif pkt.haslayer(UDP):
            proto = "UDP"
            sport = pkt[UDP].sport
            dport = pkt[UDP].dport
        rows.append({
            "timestamp": float(pkt.time),
            "src": ip.src,
            "dst": ip.dst,
            "proto": proto,
            "sport": sport,
            "dport": dport,
            "length": len(pkt),
            "ip_len": ip.len,
        })

    if not rows:
        print(f"[pcap_to_csv] Nenhum pacote IP em {pcap_path}", file=sys.stderr)
        return

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    total_bytes  = sum(r["length"] for r in rows)
    total_pkts   = len(rows)
    duration     = rows[-1]["timestamp"] - rows[0]["timestamp"] if len(rows) > 1 else 0
    print(f"[pcap_to_csv] {total_pkts} pacotes | {total_bytes} bytes | {duration:.2f}s → {csv_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: pcap_to_csv.py <input.pcap> <output.csv>")
        sys.exit(1)
    pcap_to_csv(sys.argv[1], sys.argv[2])
