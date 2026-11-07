"""Probe VPS SSH. Uses SALLY_VPS_HOST / USER / PASS."""

from __future__ import annotations

import os
import sys

import paramiko


def main() -> int:
    host = os.environ.get("SALLY_VPS_HOST", "2.24.91.218").strip()
    user = os.environ.get("SALLY_VPS_USER", "root").strip()
    password = os.environ.get("SALLY_VPS_PASS", "").strip()
    if not password:
        print("NO_PASS")
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            username=user,
            password=password,
            timeout=25,
            allow_agent=False,
            look_for_keys=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"SSH_FAIL {type(exc).__name__}: {exc}")
        return 1
    _, stdout, stderr = client.exec_command(
        "uname -a; curl -s http://127.0.0.1:11434/api/tags | head -c 400; echo; "
        "ss -lntp | head -n 30 || netstat -lntp | head -n 30",
        timeout=60,
    )
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err:
        print("STDERR", err)
    client.close()
    print("SSH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
