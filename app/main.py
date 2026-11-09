"""FastAPI entrypoint for the AI Ops Log Assistant."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.config import settings
from app.llm import LLMError, analyze_with_llm
from app.metrics import LLM_ERRORS, REDACTIONS, REQUEST_COUNT, REQUEST_LATENCY
from app.redaction import redact
from app.rules import classify
from app.schemas import AnalyzeRequest, AnalyzeResponse, HealthResponse

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("aiops")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "Starting %s v%s — LLM=%s model=%s",
        settings.app_name,
        __version__,
        settings.llm_base_url,
        settings.llm_model,
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title="AI Ops Log Assistant",
    description=(
        "Reference learning project: analyze ops logs/alerts with an "
        "OpenAI-compatible LLM, with PII redaction and rule-based fallback."
    ),
    version=__version__,
    lifespan=lifespan,
)


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        llm_configured=bool(settings.llm_base_url),
    )


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    started = time.perf_counter()
    source = "rule_fallback"
    status = "ok"

    try:
        raw, input_kind = req.payload_text()

        redaction_counts: dict[str, int] = {}
        if settings.enable_redaction:
            scrubbed, redaction_counts = redact(raw)
            for category, count in redaction_counts.items():
                if count:
                    REDACTIONS.labels(category=category).inc(count)
        else:
            scrubbed = raw

        if req.force_fallback:
            result = classify(scrubbed)
            source = "rule_fallback"
        else:
            try:
                result = await analyze_with_llm(
                    scrubbed,
                    input_kind=input_kind,
                    context=req.context or "",
                )
                source = "llm"
            except LLMError as exc:
                logger.warning("LLM failed (%s); using rule fallback", exc)
                LLM_ERRORS.labels(reason=type(exc).__name__).inc()
                if not settings.enable_rule_fallback:
                    status = "error"
                    raise HTTPException(
                        status_code=502,
                        detail=f"LLM unavailable and fallback disabled: {exc}",
                    ) from exc
                result = classify(scrubbed)
                source = "rule_fallback"

        preview = scrubbed[:500] if scrubbed else ""
        response = AnalyzeResponse(
            summary=result["summary"],
            probable_root_cause=result["probable_root_cause"],
            severity=result["severity"],
            troubleshooting_steps=result["troubleshooting_steps"],
            confidence=float(result["confidence"]),
            analysis_source=source,  # type: ignore[arg-type]
            matched_rule=result.get("matched_rule"),
            redaction_counts=redaction_counts,
            redacted_preview=preview,
        )
        return response
    except HTTPException:
        status = "error"
        raise
    except ValueError as exc:
        status = "error"
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        status = "error"
        logger.exception("Unexpected analyze failure")
        raise HTTPException(status_code=500, detail="internal error") from exc
    finally:
        elapsed = time.perf_counter() - started
        REQUEST_LATENCY.observe(elapsed)
        REQUEST_COUNT.labels(status=status, source=source).inc()
