"""Read-only: list Ollama models on VPS host + docker proxy."""

from __future__ import annotations

import json
import os
import sys

import paramiko


def run(client: paramiko.SSHClient, cmd: str) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return (out + (("\n" + err) if err.strip() else "")).strip()


def main() -> int:
    password = os.environ.get("SALLY_VPS_PASS", "").strip()
    host = os.environ.get("SALLY_VPS_HOST", "2.24.91.218").strip()
    user = os.environ.get("SALLY_VPS_USER", "root").strip()
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

    print("=== VPS host ollama list ===")
    print(run(client, "ollama list"))

    print("\n=== VPS host API 127.0.0.1:11434 ===")
    raw = run(client, "curl -s http://127.0.0.1:11434/api/tags")
    try:
        data = json.loads(raw)
        for m in data.get("models") or []:
            print(f"{m.get('name')}\tsize={m.get('size')}")
    except Exception:
        print(raw[:500])

    print("\n=== VPS docker ollama container ports ===")
    print(run(client, "docker ps --format '{{.Names}} {{.Ports}}' | grep -i ollama || true"))

    print("\n=== VPS docker-mapped API 127.0.0.1:32768 ===")
    raw2 = run(client, "curl -s http://127.0.0.1:32768/api/tags")
    try:
        data2 = json.loads(raw2)
        for m in data2.get("models") or []:
            print(f"{m.get('name')}\tsize={m.get('size')}")
    except Exception:
        print(raw2[:500])

    print("\n=== docker exec ollama list (if container) ===")
    print(
        run(
            client,
            "docker exec ollama-eqoj-ollama-1 ollama list 2>/dev/null || true",
        )
    )

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
