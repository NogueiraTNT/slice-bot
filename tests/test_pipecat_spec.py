from sally_cibote.config import load_settings
from sally_cibote.voice.pipecat_pipeline import build_ollama_spec


def test_remote_url_prefers_sally_env(monkeypatch):
    monkeypatch.setenv("SALLY_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setenv("SALLY_OLLAMA_MODEL", "llama3.2:1b")
    settings = load_settings()
    spec = build_ollama_spec(settings)
    assert settings.ollama.configured
    assert spec.openai_compat_base_url == "http://127.0.0.1:11434/v1"
    assert spec.model == "llama3.2:1b"
    assert "localhost" not in (settings.ollama.base_url or "") or settings.ollama.base_url.startswith(
        "http://127.0.0.1"
    )


def test_no_default_local_brain(monkeypatch):
    monkeypatch.delenv("SALLY_OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    settings = load_settings()
    assert settings.ollama.base_url == ""
    assert not settings.ollama.configured
