# Sally Cibote

Assistente de voz no **PC-Daniel** com cérebro **Ollama na VPS** (não no PC).

## Env

Copie `.env.example` → `.env` (gitignored). Variáveis principais:

- `SALLY_OLLAMA_BASE_URL` / `OLLAMA_HOST` — endpoint Ollama (via túnel: `http://127.0.0.1:11434`)
- `SALLY_OLLAMA_MODEL` — ex. `llama3.2:1b`

A porta `11434` na VPS escuta só em loopback. **Não abrir firewall sem OK do Daniel.** Use:

```powershell
$env:SALLY_VPS_HOST="…"
$env:SALLY_VPS_USER="root"
$env:SALLY_VPS_PASS="…"   # só na sessão; não commitar
py -3 scripts/start_tunnel.py
```

## Teste 5s

```powershell
py -3 -m pip install -e ".[voice]"
py -3 scripts/test_voice_5s.py
```

## Escopo

- Voz / Pipecat / Ollama remoto: sim  
- n8n / WhatsApp: não (ainda)  
- Pestinha: só inspiração LIF — não instalar/rodar daqui
