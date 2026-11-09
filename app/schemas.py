"""Pydantic request / response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AnalyzeRequest(BaseModel):
    """Accept either free-form log text or a structured alert JSON blob."""

    text: str | None = Field(
        default=None,
        description="Raw log text to analyze",
    )
    alert: dict[str, Any] | None = Field(
        default=None,
        description="Structured alert payload (e.g. Alertmanager-like JSON)",
    )
    context: str | None = Field(
        default=None,
        description="Optional hint: service name, recent deploy, etc.",
    )
    force_fallback: bool = Field(
        default=False,
        description="Skip LLM and use rule-based classifier (for demos/tests)",
    )

    @model_validator(mode="after")
    def require_payload(self) -> AnalyzeRequest:
        if not self.text and not self.alert:
            raise ValueError("Provide either 'text' or 'alert'")
        return self

    def payload_text(self) -> tuple[str, str]:
        """Return (payload_string, input_kind)."""
        if self.text:
            return self.text, "logs"
        # alert path
        import json

        return json.dumps(self.alert, ensure_ascii=False, indent=2), "alert JSON"


class AnalyzeResponse(BaseModel):
    summary: str
    probable_root_cause: str
    severity: Literal["critical", "high", "medium", "low", "unknown"]
    troubleshooting_steps: list[str]
    confidence: float
    analysis_source: Literal["llm", "rule_fallback"]
    matched_rule: str | None = None
    redaction_counts: dict[str, int] = Field(default_factory=dict)
    redacted_preview: str | None = Field(
        default=None,
        description="First 500 chars of redacted input (for debugging demos)",
    )


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_configured: bool
