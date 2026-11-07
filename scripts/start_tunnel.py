#!/usr/bin/env python3
"""Túnel SSH local → Ollama na VPS (127.0.0.1:11434).

Não altera a VPS: só encaminha porta via SSH já existente.
Credenciais: SALLY_VPS_HOST / SALLY_VPS_USER / SALLY_VPS_PASS (env).
"""

from __future__ import annotations

import os
import select
import socket
import sys
import threading

import paramiko

LOCAL_PORT = int(os.environ.get("SALLY_TUNNEL_LOCAL_PORT", "11434"))
REMOTE_HOST = "127.0.0.1"
REMOTE_PORT = 11434


def _forward(chan: paramiko.Channel, peer: socket.socket) -> None:
    try:
        while True:
            r, _w, _x = select.select([chan, peer], [], [], 60)
            if chan in r:
                data = chan.recv(65535)
                if not data:
                    break
                peer.sendall(data)
            if peer in r:
                data = peer.recv(65535)
                if not data:
                    break
                chan.sendall(data)
    finally:
        try:
            chan.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            peer.close()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    host = os.environ.get("SALLY_VPS_HOST", "").strip()
    user = os.environ.get("SALLY_VPS_USER", "root").strip()
    password = os.environ.get("SALLY_VPS_PASS", "")
    if not host or not password:
        print("Defina SALLY_VPS_HOST e SALLY_VPS_PASS no ambiente.", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=user, password=password, timeout=30)
    transport = client.get_transport()
    assert transport is not None

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", LOCAL_PORT))
    server.listen(32)
    print(
        f"[tunnel] 127.0.0.1:{LOCAL_PORT} → {host}:{REMOTE_HOST}:{REMOTE_PORT} (Ctrl+C para parar)",
        flush=True,
    )

    try:
        while True:
            peer, addr = server.accept()
            try:
                chan = transport.open_channel(
                    "direct-tcpip",
                    (REMOTE_HOST, REMOTE_PORT),
                    addr,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[tunnel] falha canal: {exc}", file=sys.stderr)
                peer.close()
                continue
            threading.Thread(target=_forward, args=(chan, peer), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[tunnel] parado")
    finally:
        server.close()
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
