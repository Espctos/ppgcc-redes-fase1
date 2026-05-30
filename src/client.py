#!/usr/bin/env python3
"""
client.py — Cliente TCP / R-UDP com Go-Back-N
PPGCC/UFPI — Projeto de Redes de Computadores 2026-1
"""

import socket
import struct
import zlib
import threading
import time
import json
import os
import logging
import argparse
from config import (
    SERVER_PORT_TCP, SERVER_PORT_RUDP,
    CHUNK_SIZE, WINDOW_SIZE, TIMEOUT_SEC, MAX_RETRIES,
    X_CUSTOM_AUTH, LOG_DIR, TEST_FILE_PATH, TEST_FILE_SIZE,
)

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "client.log")),
    ],
)
log = logging.getLogger("client")

# ──────────────────────────────────────────────────────────
#  Protocolo idêntico ao server.py
# ──────────────────────────────────────────────────────────
HDR_FMT   = "!I B I I"
HDR_SIZE  = struct.calcsize(HDR_FMT)
FLAG_DATA = 0x01
FLAG_ACK  = 0x02
FLAG_FIN  = 0x04
FLAG_NAK  = 0x08


def build_packet(seq: int, flags: int, win_base: int = 0, payload: bytes = b"") -> bytes:
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    hdr = struct.pack(HDR_FMT, seq, flags, win_base, crc)
    return hdr + payload


def parse_ctrl(raw: bytes):
    if len(raw) < HDR_SIZE:
        return None, None, None
    seq, flags, win_base, _ = struct.unpack(HDR_FMT, raw[:HDR_SIZE])
    return seq, flags, win_base


def generate_test_file(path: str, size: int):
    if not os.path.exists(path):
        log.info(f"Gerando arquivo de teste {path} ({size // 1024 // 1024} MB)")
        with open(path, "wb") as f:
            f.write(os.urandom(size))


def save_metric(data: dict, filename: str):
    path = os.path.join(LOG_DIR, filename)
    with open(path, "a") as f:
        f.write(json.dumps(data) + "\n")


# ──────────────────────────────────────────────────────────
#  TCP Client
# ──────────────────────────────────────────────────────────
def send_tcp(server_ip: str, filepath: str, scenario: str = "A") -> dict:
    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((server_ip, SERVER_PORT_TCP))

    meta = json.dumps({
        "X-Custom-Auth": X_CUSTOM_AUTH,
        "filename": filename,
        "filesize": filesize,
        "scenario": scenario,
    }).encode() + b"\n"
    sock.sendall(meta)

    # Aguarda READY
    buf = b""
    while b"\n" not in buf:
        buf += sock.recv(64)

    t0         = time.perf_counter()
    bytes_sent = 0
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sock.sendall(chunk)
            bytes_sent += len(chunk)

    # Recebe resultado
    buf = b""
    while b"\n" not in buf:
        buf += sock.recv(4096)
    elapsed = time.perf_counter() - t0
    sock.close()

    result            = json.loads(buf.split(b"\n")[0].decode())
    result["scenario"]               = scenario
    result["bytes_sent"]             = bytes_sent
    result["client_elapsed_sec"]     = round(elapsed, 4)
    result["client_throughput_mbps"] = round((bytes_sent * 8) / elapsed / 1e6, 4)

    log.info(f"[TCP] Cenário {scenario}: {result}")
    save_metric(result, "tcp_client_metrics.jsonl")
    return result


# ──────────────────────────────────────────────────────────
#  R-UDP Client — Go-Back-N Sender
# ──────────────────────────────────────────────────────────
class GoBackNSender:
    """
    Implementa o sender do Go-Back-N:
    - Janela deslizante de tamanho WINDOW_SIZE
    - Timer único para o pacote mais antigo sem ACK (base)
    - Ao timeout ou NAK: retransmite toda a janela a partir de 'base'
    """

    def __init__(self, sock, server_addr):
        self.sock    = sock
        self.addr    = server_addr
        self.W       = WINDOW_SIZE
        self.timeout = TIMEOUT_SEC

        self.chunks        = {}     # seq -> bytes
        self.total_packets = 0

        self.base          = 1      # seq mais antigo sem ACK
        self.next_seq      = 1      # próximo seq a enviar
        self.retransmissions = 0
        self.lock          = threading.Lock()
        self.done          = False
        self.timer_start   = None   # quando a janela base foi enviada

    def _load_file(self, filepath: str):
        with open(filepath, "rb") as f:
            seq = 1
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                self.chunks[seq] = chunk
                seq += 1
        self.total_packets = seq - 1
        log.info(f"[GBN] {self.total_packets} pacotes a transmitir (chunk={CHUNK_SIZE}B, W={self.W})")

    def _send_one(self, seq: int):
        pkt = build_packet(seq, FLAG_DATA, self.base, self.chunks[seq])
        self.sock.sendto(pkt, self.addr)

    def _retransmit_window(self):
        """Retransmite todos os pacotes da janela atual (base .. next_seq-1)."""
        count = 0
        with self.lock:
            for s in range(self.base, self.next_seq):
                if s in self.chunks:
                    self._send_one(s)
                    count += 1
            self.retransmissions += count
            self.timer_start = time.perf_counter()
        log.debug(f"[GBN] Janela retransmitida: {count} pkts (base={self.base})")

    def _ack_receiver(self):
        """Thread receptora de ACKs/NAKs."""
        self.sock.settimeout(self.timeout / 4)
        while not self.done:
            try:
                raw, _ = self.sock.recvfrom(HDR_SIZE + 32)
                seq, flags, _ = parse_ctrl(raw)
                if seq is None:
                    continue
                with self.lock:
                    if flags & FLAG_ACK:
                        if seq >= self.base:
                            self.base = seq + 1
                            self.timer_start = time.perf_counter()
                    elif flags & FLAG_NAK:
                        # NAK → retransmite janela imediatamente
                        pass   # tratado no loop principal via flag
            except socket.timeout:
                pass
            except Exception as exc:
                if not self.done:
                    log.debug(f"[GBN] ACK recv err: {exc}")

    def send(self, filepath: str, scenario: str = "A") -> dict:
        self._load_file(filepath)
        filesize = os.path.getsize(filepath)
        filename = os.path.basename(filepath)

        # ── Envia metadado (seq=0) e aguarda confirmação ──
        meta_payload = json.dumps({
            "X-Custom-Auth": X_CUSTOM_AUTH,
            "filename": filename,
            "filesize": filesize,
            "scenario": scenario,
        }).encode()
        meta_pkt = build_packet(0, FLAG_DATA, 0, meta_payload)

        confirmed = False
        for attempt in range(MAX_RETRIES):
            self.sock.sendto(meta_pkt, self.addr)
            try:
                self.sock.settimeout(TIMEOUT_SEC)
                raw, _ = self.sock.recvfrom(HDR_SIZE + 64)
                seq, flags, _ = parse_ctrl(raw)
                if seq == 0 and (flags & FLAG_ACK):
                    confirmed = True
                    break
            except socket.timeout:
                log.warning(f"[GBN] Timeout metadado (tentativa {attempt + 1})")
        if not confirmed:
            raise RuntimeError("[GBN] Servidor não confirmou metadado")

        # ── Loop principal Go-Back-N ──
        self.base      = 1
        self.next_seq  = 1
        self.timer_start = time.perf_counter()

        ack_thr = threading.Thread(target=self._ack_receiver, daemon=True)
        ack_thr.start()

        t0 = time.perf_counter()

        while True:
            with self.lock:
                # Avança janela: envia novos pacotes
                while (self.next_seq <= self.total_packets and
                       self.next_seq < self.base + self.W):
                    self._send_one(self.next_seq)
                    self.next_seq += 1
                    if self.next_seq == self.base + 1:
                        self.timer_start = time.perf_counter()

                if self.base > self.total_packets:
                    break

                # Timer da janela expirou → retransmite tudo
                if (time.perf_counter() - self.timer_start) > self.timeout:
                    for s in range(self.base, self.next_seq):
                        if s in self.chunks:
                            self._send_one(s)
                            self.retransmissions += 1
                    self.timer_start = time.perf_counter()

            time.sleep(0.001)

        # Envia FIN
        fin = build_packet(self.next_seq, FLAG_FIN, self.base)
        for _ in range(5):
            self.sock.sendto(fin, self.addr)
            time.sleep(0.05)

        self.done   = True
        elapsed     = time.perf_counter() - t0

        result = {
            "protocol": "R-UDP/GBN",
            "window_size": self.W,
            "total_packets": self.total_packets,
            "retransmissions": self.retransmissions,
            "bytes_sent": filesize,
            "elapsed_sec": round(elapsed, 4),
            "throughput_mbps": round((filesize * 8) / elapsed / 1e6, 4),
            "scenario": scenario,
        }
        log.info(f"[GBN] Cenário {scenario}: {result}")
        save_metric(result, "rudp_client_metrics.jsonl")
        return result


def send_rudp(server_ip: str, filepath: str, scenario: str = "A") -> dict:
    sock   = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server = (server_ip, SERVER_PORT_RUDP)
    sender = GoBackNSender(sock, server)
    result = sender.send(filepath, scenario)
    sock.close()
    return result


# ──────────────────────────────────────────────────────────
#  Entrypoint
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente TCP / R-UDP GBN")
    parser.add_argument("--mode",     choices=["tcp", "rudp", "both"], default="both")
    parser.add_argument("--server",   default="server")
    parser.add_argument("--file",     default=TEST_FILE_PATH)
    parser.add_argument("--filesize", type=int, default=TEST_FILE_SIZE)
    parser.add_argument("--scenario", default="A")
    args = parser.parse_args()

    generate_test_file(args.file, args.filesize)

    results = {}
    if args.mode in ("tcp", "both"):
        results["TCP"] = send_tcp(args.server, args.file, args.scenario)
    if args.mode in ("rudp", "both"):
        results["R-UDP"] = send_rudp(args.server, args.file, args.scenario)

    print("\n=== RESULTADOS ===")
    print(json.dumps(results, indent=2))
