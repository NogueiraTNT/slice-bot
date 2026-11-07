"""Hot-update Sally brain code on VPS without touching the memory DB.

Uploads src/sally_cibote only, restarts sally-brain.service.
Env: SALLY_VPS_HOST, SALLY_VPS_USER, SALLY_VPS_PASS
"""

from __future__ import annotations

import io
import os
import sys
import tarfile
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = "/opt/sally-cibote"


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=os.environ["SALLY_VPS_HOST"].strip(),
        username=os.environ.get("SALLY_VPS_USER", "root").strip(),
        password=os.environ["SALLY_VPS_PASS"],
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def main() -> int:
    for key in ("SALLY_VPS_HOST", "SALLY_VPS_PASS"):
        if not os.environ.get(key):
            print(f"missing {key}")
            return 2

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(ROOT / "src" / "sally_cibote", arcname="src/sally_cibote")
    tgz = buf.getvalue()

    client = connect()
    # Snapshot memory count before update
    _, before, _ = run(
        client,
        f"python3 -c \"import sqlite3; c=sqlite3.connect('{REMOTE_ROOT}/data/memory/sally_memory.db'); "
        f"print(c.execute('select count(*) from memories').fetchone()[0])\"",
    )
    print("memories_before", before.strip())

    sftp = client.open_sftp()
    remote_tgz = "/tmp/sally-cibote-src-update.tgz"
    with sftp.file(remote_tgz, "wb") as rf:
        rf.write(tgz)
    sftp.close()
    print(f"uploaded {len(tgz)} bytes")

    code, out, err = run(
        client,
        f"tar -xzf {remote_tgz} -C {REMOTE_ROOT} && "
        f"systemctl restart sally-brain && sleep 2 && "
        f"systemctl is-active sally-brain && curl -s http://127.0.0.1:8765/health && "
        f"python3 -c \"import sqlite3; c=sqlite3.connect('{REMOTE_ROOT}/data/memory/sally_memory.db'); "
        f"print('memories_after', c.execute('select count(*) from memories').fetchone()[0])\"",
    )
    print(out)
    if err.strip():
        print("stderr", err[-800:])
    client.close()
    if code != 0 or "active" not in out:
        print("UPDATE_FAIL", code)
        return 1
    print("UPDATE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
