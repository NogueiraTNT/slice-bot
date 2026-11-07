"""Read-only: is Sally deployed on VPS yet?"""

from __future__ import annotations

import os
import sys

import paramiko


def main() -> int:
    host = os.environ.get("SALLY_VPS_HOST", "2.24.91.218")
    user = os.environ.get("SALLY_VPS_USER", "root")
    password = os.environ.get("SALLY_VPS_PASS", "")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        username=user,
        password=password,
        timeout=25,
        allow_agent=False,
        look_for_keys=False,
    )
    cmds = [
        "ls -ld /opt/sally-cibote 2>&1",
        "find /opt /home -maxdepth 2 -iname '*sally*' 2>/dev/null | head",
        "ss -lntp | grep -E ':(8765|8787)\\b' || echo NO_SALLY_LISTEN_PORT",
        "curl -s -m 3 http://127.0.0.1:8765/health || echo NO_HEALTH_8765",
        "pgrep -af 'brain_api|sally-cibote' || echo NO_SALLY_PROCESS",
        "systemctl is-active sally-brain 2>&1 || true",
        "docker ps --format '{{.Names}} {{.Ports}}' | grep -i ollama || true",
    ]
    for cmd in cmds:
        print(f"===== {cmd} =====")
        _, stdout, stderr = client.exec_command(cmd, timeout=40)
        sys.stdout.write(stdout.read().decode("utf-8", errors="replace"))
        err = stderr.read().decode("utf-8", errors="replace")
        if err.strip():
            sys.stdout.write(err)
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
