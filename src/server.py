#!/usr/bin/env python3
"""
server.py — Servidor TCP / R-UDP com Go-Back-N
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
    SERVER_HOST, SERVER_PORT_TCP, SERVER_PORT_RUDP,
    CHUNK_SIZE, WINDOW_SIZE, TIMEOUT_SEC,
    LOG_DIR,
)

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "server.log")),
    ],
)
log = logging.getLogger("server")

# ──────────────────────────────────────────────────────────
#  Protocolo R-UDP — formato do pacote Go-Back-N
#  | seq (4B) | flags (1B) | win_base (4B) | crc32 (4B) | payload |
#  flags: DATA=0x01  ACK=0x02  FIN=0x04  NAK=0x08
# ──────────────────────────────────────────────────────────
HDR_FMT  = "!I B I I"
HDR_SIZE = struct.calcsize(HDR_FMT)   # 13 bytes

FLAG_DATA = 0x01
FLAG_ACK  = 0x02
FLAG_FIN  = 0x04
FLAG_NAK  = 0x08


def build_packet(seq: int, flags: int, win_base: int = 0, payload: bytes = b"") -> bytes:
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    hdr = struct.pack(HDR_FMT, seq, flags, win_base, crc)
    return hdr + payload


def parse_packet(raw: bytes):
    if len(raw) < HDR_SIZE:
        return None, None, None, None, False
    seq, flags, win_base, crc = struct.unpack(HDR_FMT, raw[:HDR_SIZE])
    payload = raw[HDR_SIZE:]
    valid   = (zlib.crc32(payload) & 0xFFFFFFFF) == crc
    return seq, flags, win_base, payload, valid


def send_ack(sock, addr, seq: int, ok: bool, win_base: int = 0):
    flag = FLAG_ACK if ok else FLAG_NAK
    pkt  = build_packet(seq, flag, win_base)
    sock.sendto(pkt, addr)


# ──────────────────────────────────────────────────────────
#  TCP Server
# ──────────────────────────────────────────────────────────
class TCPServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((SERVER_HOST, SERVER_PORT_TCP))
        self.sock.listen(5)
        log.info(f"TCP server ouvindo em {SERVER_HOST}:{SERVER_PORT_TCP}")

    def _save(self, data: dict):
        path = os.path.join(LOG_DIR, "tcp_metrics.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(data) + "\n")

    def handle(self, conn, addr):
        log.info(f"[TCP] Conexão de {addr}")
        total = 0
        try:
            # Recebe metadados
            raw  = b""
            while b"\n" not in raw:
                raw += conn.recv(4096)
            meta     = json.loads(raw.split(b"\n")[0].decode())
            auth     = meta.get("X-Custom-Auth", "")
            filesize = int(meta.get("filesize", 0))
            filename = meta.get("filename", "recv_tcp.bin")
            log.info(f"[TCP] Auth={auth} | arquivo={filename} | tamanho={filesize}")
            conn.sendall(b"READY\n")

            dest  = f"/tmp/recv_tcp_{filename}"
            t0    = time.perf_counter()
            with open(dest, "wb") as f:
                while total < filesize:
                    chunk = conn.recv(min(65536, filesize - total))
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)

            elapsed    = time.perf_counter() - t0
            throughput = (total * 8) / elapsed / 1e6

            result = {
                "protocol": "TCP",
                "bytes_received": total,
                "elapsed_sec": round(elapsed, 4),
                "throughput_mbps": round(throughput, 4),
                "auth": auth,
            }
            log.info(f"[TCP] Concluído: {result}")
            conn.sendall((json.dumps(result) + "\n").encode())
            self._save(result)
        except Exception as exc:
            log.error(f"[TCP] Erro: {exc}")
        finally:
            conn.close()

    def run(self):
        while True:
            conn, addr = self.sock.accept()
            threading.Thread(target=self.handle, args=(conn, addr), daemon=True).start()


# ──────────────────────────────────────────────────────────
#  R-UDP Server — Go-Back-N receiver
# ──────────────────────────────────────────────────────────
class RUDPServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((SERVER_HOST, SERVER_PORT_RUDP))
        log.info(f"R-UDP (GBN) server ouvindo em {SERVER_HOST}:{SERVER_PORT_RUDP}")

    def _save(self, data: dict):
        path = os.path.join(LOG_DIR, "rudp_metrics.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(data) + "\n")

    def receive_file(self, client_addr: tuple, meta: dict):
        """
        Go-Back-N receiver: aceita apenas pacotes em ordem.
        Descarta out-of-order e envia NAK para disparar retransmissão da janela.
        """
        filename = meta.get("filename", "recv_rudp.bin")
        filesize = int(meta.get("filesize", 0))
        auth     = meta.get("X-Custom-Auth", "")
        log.info(f"[GBN] Transferência de {client_addr} | Auth={auth} | size={filesize}")

        expected    = 1
        total_bytes = 0
        corrupt     = 0
        nak_sent    = 0
        dest        = f"/tmp/recv_rudp_{filename}"

        self.sock.settimeout(TIMEOUT_SEC * 10)
        t0 = time.perf_counter()

        with open(dest, "wb") as f:
            while True:
                try:
                    raw, addr = self.sock.recvfrom(HDR_SIZE + CHUNK_SIZE + 64)
                except socket.timeout:
                    log.warning("[GBN] Timeout — assumindo FIN perdido")
                    break

                seq, flags, win_base, payload, valid = parse_packet(raw)
                if seq is None:
                    continue

                if flags & FLAG_FIN:
                    send_ack(self.sock, addr, seq, True, expected)
                    log.info(f"[GBN] FIN recebido (seq={seq})")
                    break

                if not valid:
                    corrupt += 1
                    send_ack(self.sock, addr, seq, False, expected)
                    nak_sent += 1
                    continue

                if seq == expected:
                    f.write(payload)
                    total_bytes += len(payload)
                    send_ack(self.sock, addr, seq, True, expected)
                    expected += 1
                else:
                    # Out-of-order: NAK com número do esperado (GBN retransmite janela)
                    send_ack(self.sock, addr, expected - 1, False, expected)
                    nak_sent += 1

        elapsed    = time.perf_counter() - t0
        throughput = (total_bytes * 8) / elapsed / 1e6 if elapsed > 0 else 0
        result = {
            "protocol": "R-UDP/GBN",
            "bytes_received": total_bytes,
            "elapsed_sec": round(elapsed, 4),
            "throughput_mbps": round(throughput, 4),
            "corrupt_packets": corrupt,
            "nak_sent": nak_sent,
            "auth": auth,
        }
        log.info(f"[GBN] Concluído: {result}")
        self._save(result)

    def run(self):
        while True:
            try:
                raw, addr = self.sock.recvfrom(4096)
                seq, flags, _, payload, valid = parse_packet(raw)
                if seq == 0 and valid:
                    meta = json.loads(payload.decode())
                    send_ack(self.sock, addr, 0, True)
                    self.receive_file(addr, meta)
            except Exception as exc:
                log.error(f"[GBN] Loop error: {exc}")


# ──────────────────────────────────────────────────────────
#  Entrypoint
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["tcp", "rudp", "both"], default="both")
    args = parser.parse_args()

    threads = []
    if args.mode in ("tcp", "both"):
        srv = TCPServer()
        threads.append(threading.Thread(target=srv.run, daemon=True))

    if args.mode in ("rudp", "both"):
        srv = RUDPServer()
        threads.append(threading.Thread(target=srv.run, daemon=True))

    for t in threads:
        t.start()

    log.info("Servidores ativos. Ctrl+C para encerrar.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Encerrando.")
