"""Runtime configuration via environment variables."""

from __future__ import annotations

import os


class Settings:
    """Application settings loaded from environment."""

    app_name: str = os.getenv("APP_NAME", "aiops-log-assistant")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # OpenAI-compatible LLM endpoint (Ollama by default)
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://ollama:11434/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "ollama")
    llm_model: str = os.getenv("LLM_MODEL", "qwen2.5:7b")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    llm_max_input_chars: int = int(os.getenv("LLM_MAX_INPUT_CHARS", "8000"))

    # Responsible AI: redact PII before sending to LLM
    enable_redaction: bool = os.getenv("ENABLE_REDACTION", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # Fallback when LLM is unavailable
    enable_rule_fallback: bool = os.getenv("ENABLE_RULE_FALLBACK", "true").lower() in (
        "1",
        "true",
        "yes",
    )


settings = Settings()
