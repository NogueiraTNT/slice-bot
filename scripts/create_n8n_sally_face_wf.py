"""Create Sally Face webhook workflow on n8n (does not modify existing WFs)."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.getenv("SALLY_N8N_BASE", "https://n8n.srv1660520.hstgr.cloud").rstrip("/")
EMAIL = os.getenv("SALLY_N8N_EMAIL", "").strip()
PASSWORD = os.getenv("SALLY_N8N_PASSWORD", "").strip()


def req(method: str, path: str, body: dict | None = None, cookie: str | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        set_cookie = resp.headers.get("Set-Cookie")
        return resp.status, json.loads(raw) if raw else {}, set_cookie


def main() -> int:
    if not EMAIL or not PASSWORD:
        print("Set SALLY_N8N_EMAIL and SALLY_N8N_PASSWORD")
        return 2
    status, login, set_cookie = req(
        "POST",
        "/rest/login",
        {"emailOrLdapLoginId": EMAIL, "password": PASSWORD},
    )
    cookie = ""
    if set_cookie:
        cookie = set_cookie.split(";")[0]
    # Also pull from login payload if needed
    print("login", status, login.get("data", {}).get("email"))

    wf = {
        "name": "Sally Face — Webhook Clima",
        "settings": {"executionOrder": "v1"},
        "nodes": [
            {
                "id": "wh-sally-face-01",
                "name": "Webhook Sally",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2.1,
                "position": [0, 0],
                "webhookId": "sally-face-webhook",
                "parameters": {
                    "httpMethod": "POST",
                    "path": "sally-face",
                    "responseMode": "responseNode",
                    "options": {},
                },
            },
            {
                "id": "code-parse-01",
                "name": "Parse Text",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [260, 0],
                "parameters": {
                    "jsCode": (
                        "const body = $input.first().json.body || $input.first().json;\n"
                        "const text = String(body.text || body.message || body.query || '').trim();\n"
                        "const lower = text.toLowerCase();\n"
                        "const isWeather = /(chover|chuva|clima|tempo|weather|previs[aã]o|umidade|temperatura|vai\\s+fazer)/i.test(lower);\n"
                        "return [{ json: { text, isWeather, city: body.city || 'Sao Paulo' } }];\n"
                    )
                },
            },
            {
                "id": "if-weather-01",
                "name": "E clima?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [500, 0],
                "parameters": {
                    "conditions": {
                        "options": {
                            "caseSensitive": True,
                            "leftValue": "",
                            "typeValidation": "strict",
                            "version": 2,
                        },
                        "conditions": [
                            {
                                "id": "cond-weather",
                                "leftValue": "={{ $json.isWeather }}",
                                "rightValue": True,
                                "operator": {
                                    "type": "boolean",
                                    "operation": "true",
                                    "singleValue": True,
                                },
                            }
                        ],
                        "combinator": "and",
                    },
                    "options": {},
                },
            },
            {
                "id": "http-meteo-01",
                "name": "Open-Meteo",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [760, -120],
                "parameters": {
                    "method": "GET",
                    "url": "https://api.open-meteo.com/v1/forecast",
                    "sendQuery": True,
                    "queryParameters": {
                        "parameters": [
                            {"name": "latitude", "value": "-23.55"},
                            {"name": "longitude", "value": "-46.63"},
                            {
                                "name": "current",
                                "value": "temperature_2m,precipitation,rain,weather_code",
                            },
                            {
                                "name": "daily",
                                "value": "precipitation_sum,precipitation_probability_max,weather_code",
                            },
                            {"name": "timezone", "value": "America/Sao_Paulo"},
                            {"name": "forecast_days", "value": "1"},
                        ]
                    },
                    "options": {},
                },
            },
            {
                "id": "code-weather-reply-01",
                "name": "Resposta Clima",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1020, -120],
                "parameters": {
                    "jsCode": (
                        "const meteo = $input.first().json;\n"
                        "const text = $('Parse Text').first().json.text;\n"
                        "const cur = meteo.current || {};\n"
                        "const daily = meteo.daily || {};\n"
                        "const temp = cur.temperature_2m;\n"
                        "const rainNow = Number(cur.precipitation || cur.rain || 0);\n"
                        "const prob = Array.isArray(daily.precipitation_probability_max)\n"
                        "  ? daily.precipitation_probability_max[0] : null;\n"
                        "const sum = Array.isArray(daily.precipitation_sum) ? daily.precipitation_sum[0] : null;\n"
                        "const code = cur.weather_code;\n"
                        "const wetCodes = new Set([51,53,55,56,57,61,63,65,66,67,80,81,82,95,96,99]);\n"
                        "const raining = rainNow > 0.1 || wetCodes.has(Number(code));\n"
                        "let reply;\n"
                        "if (raining) {\n"
                        "  reply = `Sim, parece chover em São Paulo agora (${temp}°C). Probabilidade hoje ~${prob ?? '?'}%.`;\n"
                        "} else if (prob != null && prob >= 50) {\n"
                        "  reply = `Pode chover em São Paulo hoje (probabilidade ~${prob}%, agora ${temp}°C, sem chuva forte no momento).`;\n"
                        "} else if (prob != null && prob >= 30) {\n"
                        "  reply = `Talvez. Em São Paulo a chance de chuva hoje é ~${prob}% (agora ${temp}°C).`;\n"
                        "} else {\n"
                        "  reply = `Não deve chover muito em São Paulo agora (${temp}°C). Chance de chuva hoje ~${prob ?? 0}%.`;\n"
                        "}\n"
                        "if (sum != null) reply += ` Previsão de precipitação: ${sum} mm.`;\n"
                        "return [{ json: { reply, text, source: 'open-meteo', temp, prob, rainNow } }];\n"
                    )
                },
            },
            {
                "id": "code-echo-01",
                "name": "Resposta Simples",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [760, 120],
                "parameters": {
                    "jsCode": (
                        "const text = $json.text || '';\n"
                        "const reply = text ? `Recebi: ${text}` : 'Não entendi o pedido. Tente de novo.';\n"
                        "return [{ json: { reply, text, source: 'echo' } }];\n"
                    )
                },
            },
            {
                "id": "respond-01",
                "name": "Respond to Webhook",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [1280, 0],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": "={{ { reply: $json.reply, text: $json.text, source: $json.source } }}",
                    "options": {},
                },
            },
        ],
        "connections": {
            "Webhook Sally": {
                "main": [[{"node": "Parse Text", "type": "main", "index": 0}]]
            },
            "Parse Text": {
                "main": [[{"node": "E clima?", "type": "main", "index": 0}]]
            },
            "E clima?": {
                "main": [
                    [{"node": "Open-Meteo", "type": "main", "index": 0}],
                    [{"node": "Resposta Simples", "type": "main", "index": 0}],
                ]
            },
            "Open-Meteo": {
                "main": [[{"node": "Resposta Clima", "type": "main", "index": 0}]]
            },
            "Resposta Clima": {
                "main": [[{"node": "Respond to Webhook", "type": "main", "index": 0}]]
            },
            "Resposta Simples": {
                "main": [[{"node": "Respond to Webhook", "type": "main", "index": 0}]]
            },
        },
    }

    status, created, _ = req("POST", "/rest/workflows", wf, cookie=cookie)
    data = created.get("data") or created
    wf_id = data.get("id")
    print("created", status, wf_id, data.get("name"))
    if not wf_id:
        print(json.dumps(created, indent=2)[:2000])
        return 1

    # Activate
    try:
        status, act, _ = req(
            "PATCH", f"/rest/workflows/{wf_id}", {"active": True}, cookie=cookie
        )
        print("activate patch", status, (act.get("data") or act).get("active"))
    except Exception as e:
        print("patch failed", e)
        try:
            status, act, _ = req("POST", f"/rest/workflows/{wf_id}/activate", {}, cookie=cookie)
            print("activate post", status, act)
        except Exception as e2:
            print("activate failed", e2)
            return 2

    print("WEBHOOK", f"{BASE}/webhook/sally-face")
    print("WF_ID", wf_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
