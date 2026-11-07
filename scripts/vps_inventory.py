"""Inventory VPS services/files without changing anything."""

from __future__ import annotations

import os
import sys

import paramiko

CMDS = [
    ("uname", "uname -a"),
    ("uptime", "uptime"),
    ("disk", "df -h / /opt /var /home 2>/dev/null | head -n 20"),
    ("memory", "free -h"),
    ("listening", "ss -lntp 2>/dev/null || netstat -lntp"),
    ("docker_ps", "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' 2>/dev/null || echo NO_DOCKER"),
    ("docker_compose", "ls -la /opt /root /home 2>/dev/null | head -n 80"),
    ("ollama_bin", "command -v ollama; systemctl is-active ollama 2>/dev/null; systemctl status ollama --no-pager 2>/dev/null | head -n 15"),
    ("ollama_local_tags", "curl -s http://127.0.0.1:11434/api/tags | python3 -c 'import sys,json;d=json.load(sys.stdin);print([m[\"name\"] for m in d.get(\"models\",[])])' 2>/dev/null || echo OLLAMA_TAGS_FAIL"),
    ("ollama_env", "env | grep -i ollama || true; ls -la /usr/local/bin/ollama /usr/bin/ollama ~/.ollama 2>/dev/null; ls -la /usr/share/ollama /.ollama 2>/dev/null | head"),
    ("python", "python3 --version; which python3 pip3"),
    ("existing_sally", "ls -la /opt/sally* /opt/sally-cibote /home/*/sally* 2>/dev/null; find /opt /home /var/www -maxdepth 3 -iname '*sally*' 2>/dev/null | head"),
    ("sqlite_dbs", "find /opt /home /var/lib /root -name '*.db' 2>/dev/null | head -n 40"),
    ("systemd_units", "systemctl list-units --type=service --state=running --no-pager | head -n 60"),
    ("firewall", "ufw status 2>/dev/null || iptables -L INPUT -n 2>/dev/null | head -n 25 || true"),
    ("traefik_hint", "docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -iE 'traefik|n8n|ollama|whaticket|whatsapp' || true"),
    ("ports_conflict_check", "ss -lntp | grep -E ':(8765|8787|9000|11434|5678)\\b' || true"),
]


def main() -> int:
    host = os.environ.get("SALLY_VPS_HOST", "2.24.91.218").strip()
    user = os.environ.get("SALLY_VPS_USER", "root").strip()
    password = os.environ.get("SALLY_VPS_PASS", "").strip()
    if not password:
        print("Missing SALLY_VPS_PASS")
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        username=user,
        password=password,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    for name, cmd in CMDS:
        print(f"\n===== {name} =====")
        _, stdout, stderr = client.exec_command(cmd, timeout=90)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        sys.stdout.write(out)
        if err.strip():
            sys.stdout.write("[stderr] " + err)
    client.close()
    print("\n===== DONE =====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
