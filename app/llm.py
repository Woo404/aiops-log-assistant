"""OpenAI-compatible LLM client with structured JSON analysis prompt."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an experienced Site Reliability / DevOps engineer.
Analyze the provided infrastructure logs or alerts and return ONLY valid JSON
with these exact keys:
{
  "summary": "one or two sentence plain-English summary",
  "probable_root_cause": "most likely root cause",
  "severity": "critical|high|medium|low|unknown",
  "troubleshooting_steps": ["step 1", "step 2", "step 3"],
  "confidence": 0.0
}

Rules:
- confidence is a float from 0.0 to 1.0
- troubleshooting_steps: 3 to 6 concrete, actionable steps
- Do NOT invent hostnames, IPs, or credentials that are not in the input
- If the input was redacted (placeholders like [REDACTED_IP]), reason about
  the pattern without trying to recover the original values
- If evidence is weak, lower confidence and say so in summary
- Prefer operational root causes over vague statements
- Output JSON only — no markdown fences, no commentary
"""

USER_PROMPT_TEMPLATE = """Analyze the following {input_kind}.
Context hint (optional): {context}

----- BEGIN LOGS/ALERT -----
{payload}
----- END LOGS/ALERT -----

Return JSON only.
"""


class LLMError(Exception):
    """Raised when the LLM call fails or returns unusable output."""


def _extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from model output, tolerating accidental markdown fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    # Fallback: first {...} block
    if not text.startswith("{"):
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise LLMError("LLM JSON root is not an object")
    return data


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure required keys exist with sane types."""
    severity = str(data.get("severity", "unknown")).lower()
    if severity not in {"critical", "high", "medium", "low", "unknown"}:
        severity = "unknown"

    steps = data.get("troubleshooting_steps") or []
    if isinstance(steps, str):
        steps = [steps]
    steps = [str(s) for s in steps][:8]

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    return {
        "summary": str(data.get("summary") or "No summary provided."),
        "probable_root_cause": str(data.get("probable_root_cause") or "Unspecified by model."),
        "severity": severity,
        "troubleshooting_steps": steps or ["Collect more context and re-run analysis"],
        "confidence": confidence,
        "analysis_source": "llm",
    }


async def analyze_with_llm(
    payload: str,
    *,
    input_kind: str = "logs",
    context: str = "",
) -> dict[str, Any]:
    """Call an OpenAI-compatible chat completions endpoint."""
    if len(payload) > settings.llm_max_input_chars:
        payload = payload[: settings.llm_max_input_chars] + "\n...[truncated]..."

    user_content = USER_PROMPT_TEMPLATE.format(
        input_kind=input_kind,
        context=context or "(none)",
        payload=payload,
    )

    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
        "stream": False,
    }

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            result = resp.json()
    except httpx.TimeoutException as exc:
        raise LLMError(f"LLM timeout after {settings.llm_timeout_seconds}s") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM HTTP error: {exc}") from exc

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected LLM response shape: {result!r}") from exc

    try:
        parsed = _extract_json(content)
    except (json.JSONDecodeError, LLMError) as exc:
        raise LLMError(f"Failed to parse LLM JSON: {exc}") from exc

    return _normalize(parsed)
