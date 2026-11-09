"""Prometheus metrics for the analysis service."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "aiops_analyze_requests_total",
    "Total /analyze requests",
    ["status", "source"],
)

REQUEST_LATENCY = Histogram(
    "aiops_analyze_latency_seconds",
    "Latency of /analyze requests",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

LLM_ERRORS = Counter(
    "aiops_llm_errors_total",
    "LLM call failures",
    ["reason"],
)

REDACTIONS = Counter(
    "aiops_redactions_total",
    "PII redaction replacements applied",
    ["category"],
)
