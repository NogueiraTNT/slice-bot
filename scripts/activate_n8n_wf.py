"""Activate an n8n workflow by id."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("SALLY_N8N_BASE", "https://n8n.srv1660520.hstgr.cloud").rstrip("/")
EMAIL = os.getenv("SALLY_N8N_EMAIL", "").strip()
PASSWORD = os.getenv("SALLY_N8N_PASSWORD", "").strip()
WF_ID = sys.argv[1] if len(sys.argv) > 1 else "27bsL7na7eCAftGo"


def call(method: str, path: str, body: dict | None, cookie: str):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Cookie": cookie,
    }
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, {"error": raw}


def main() -> int:
    if not EMAIL or not PASSWORD:
        print("Set SALLY_N8N_EMAIL and SALLY_N8N_PASSWORD")
        return 2
    status, login = call(
        "POST",
        "/rest/login",
        {"emailOrLdapLoginId": EMAIL, "password": PASSWORD},
        "",
    )
    # re-login capturing cookie properly
    data = json.dumps(
        {"emailOrLdapLoginId": EMAIL, "password": PASSWORD}
    ).encode("utf-8")
    r = urllib.request.Request(
        BASE + "/rest/login",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(r) as resp:
        cookie = (resp.headers.get("Set-Cookie") or "").split(";")[0]
        print("login", resp.status, cookie[:50])

    # Full update with active true — fetch first then put
    st, wf = call("GET", f"/rest/workflows/{WF_ID}", None, cookie)
    print("get", st, "active=", (wf.get("data") or {}).get("active"))
    payload = wf.get("data") or wf
    # n8n activate often wants POST /rest/workflows/:id/activate
    for method, path, body in [
        ("POST", f"/rest/workflows/{WF_ID}/activate", {}),
        ("PATCH", f"/rest/workflows/{WF_ID}", {"active": True}),
        (
            "PUT",
            f"/rest/workflows/{WF_ID}",
            {
                "name": payload.get("name"),
                "nodes": payload.get("nodes"),
                "connections": payload.get("connections"),
                "settings": payload.get("settings") or {},
                "active": True,
            },
        ),
    ]:
        st, out = call(method, path, body, cookie)
        d = out.get("data") if isinstance(out, dict) else out
        active = d.get("active") if isinstance(d, dict) else None
        print(method, path, st, "active=", active, "err=", (out.get("error") or "")[:200])

    st, wf2 = call("GET", f"/rest/workflows/{WF_ID}", None, cookie)
    print("final active", (wf2.get("data") or {}).get("active"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
