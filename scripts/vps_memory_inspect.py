"""Read-only: dump VPS sally_memory.db and reproduce prompt context query."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import paramiko

# local code for same search logic
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sally_cibote.memory.sqlite_store import LongTermMemory  # noqa: E402


def main() -> int:
    host = os.environ.get("SALLY_VPS_HOST", "2.24.91.218")
    user = os.environ.get("SALLY_VPS_USER", "root")
    password = os.environ.get("SALLY_VPS_PASS", "")
    remote_db = "/opt/sally-cibote/data/memory/sally_memory.db"

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

    # SQL dump via remote python (read-only)
    cmd = f"""python3 - <<'PY'
import sqlite3
c=sqlite3.connect('{remote_db}')
c.row_factory=sqlite3.Row
n=c.execute('select count(*) from memories').fetchone()[0]
print('COUNT', n)
print('---ALL---')
for r in c.execute('select id, timestamp, tag, content from memories order by id'):
    print(f"id={{r['id']}}\\ttag={{r['tag']}}\\tts={{r['timestamp']}}\\t{{r['content']}}")
print('---AMANHA/REUNIAO HITS---')
for r in c.execute(\"\"\"select id, tag, content from memories where lower(content) like '%amanh%' or lower(content) like '%reun%' or lower(content) like '%combinado%' order by id\"\"\"):
    print(f"id={{r['id']}}\\ttag={{r['tag']}}\\t{{r['content']}}")
PY"""
    _, stdout, stderr = client.exec_command(cmd, timeout=60)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR", err)

    # Download a copy for local search reproduction (read-only copy)
    sftp = client.open_sftp()
    with tempfile.TemporaryDirectory() as td:
        local = Path(td) / "sally_memory.db"
        sftp.get(remote_db, str(local))
        sftp.close()
        client.close()

        mem = LongTermMemory(local)
        query = "o que temos amanhã?"
        print("\n===== reproduce context_for_prompt =====")
        print("query:", query)
        print("tokens:", mem._tokens(query))
        print("--- search() ---")
        for row in mem.search(query, limit=8):
            print(f"id={row.id}\ttag={row.tag}\t{row.content}")
        print("--- recent(6) ---")
        for row in mem.recent(limit=6):
            print(f"id={row.id}\ttag={row.tag}\t{row.content}")
        print("--- context_for_prompt ---")
        print(mem.context_for_prompt(query, recent_n=6, relevant_n=6))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
