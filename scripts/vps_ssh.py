#!/usr/bin/env python3
"""SSH helper para a VPS. Credenciais só via env (SALLY_VPS_*), nunca hardcode."""

from __future__ import annotations

import argparse
import os
import sys

import paramiko


def connect() -> paramiko.SSHClient:
    host = os.environ.get("SALLY_VPS_HOST", "").strip()
    user = os.environ.get("SALLY_VPS_USER", "root").strip()
    password = os.environ.get("SALLY_VPS_PASS", "")
    if not host or not password:
        raise SystemExit("Defina SALLY_VPS_HOST e SALLY_VPS_PASS no ambiente (não commitar).")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=user, password=password, timeout=30)
    return client


def run(cmd: str, timeout: int = 120) -> tuple[int, str, str]:
    client = connect()
    try:
        _stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return code, out, err
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="+", help="Comando remoto")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    cmd = " ".join(args.command)
    code, out, err = run(cmd, timeout=args.timeout)
    sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
