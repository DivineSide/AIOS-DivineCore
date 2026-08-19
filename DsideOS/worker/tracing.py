# -*- coding: utf-8 -*-
"""tracing — optional OpenTelemetry/Phoenix instrumentation bootstrap.

WHY: no eval/regression harness existed for this pipeline (see DsideOS/CLAUDE.md
"no structured evaluation harness" gap) — every threshold (topic-dedup cosine
cutoffs, grounding checks) was hand-tuned against a handful of real examples.
Phoenix (github.com/Arize-ai/phoenix, self-hosted, see .phoenix_data/) gives a
real trace of each generation call (embed -> retrieve -> draft -> grade) plus
a Datasets/Experiments mechanism to catch regressions when prompts/retrieval
change — this module is the wiring, not the eval harness itself (that's still
a separate, not-yet-built piece: saving real traces as a golden dataset).

OFF BY DEFAULT (PHOENIX_TRACING_ENABLED=0) — production must never silently
start shipping traces anywhere. Enable locally via .env for dev/debugging.

WHAT GETS TRACED:
  - OpenAI + Anthropic calls: auto-instrumented, zero code changes at the call
    site. This ALSO covers Sarvam — generate.py's Sarvam client is a real
    openai.OpenAI() instance pointed at Sarvam's OpenAI-compatible endpoint
    (see _sarvam_client()), so the OpenAI instrumentor patches the same
    .chat.completions.create() method Sarvam calls through. No separate
    Sarvam instrumentor exists or is needed.
  - Retrieval (rag/query.py's passage_lookup/pyq_rag_lookup): NOT auto-
    instrumentable (raw psycopg2, no SDK to patch) — wrapped manually as
    RETRIEVER-kind spans via manual_retriever_span() below.

CELERY GOTCHA (why this is called from worker_process_init, not import time):
Celery's default prefork pool forks worker processes AFTER the parent process
starts. Registering the OTel tracer provider at module-import time risks
double-registration or a provider bound to the pre-fork process instead of
the actual worker process that makes the calls. worker_process_init fires
once per real worker process, after the fork — the correct hook.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("dsideos.tracing")

_tracer = None


def is_enabled() -> bool:
    return os.environ.get("PHOENIX_TRACING_ENABLED", "0") == "1"


def init_tracing(project_name: str = "dsideos-worker") -> None:
    """Call once per worker process (see module docstring — Celery
    worker_process_init, not import time). No-op if PHOENIX_TRACING_ENABLED
    is unset/0, so this is always safe to call unconditionally at startup."""
    global _tracer
    if not is_enabled():
        logger.info("tracing disabled (PHOENIX_TRACING_ENABLED=0)")
        return
    if _tracer is not None:
        return  # already initialized in this process

    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
    from phoenix.otel import register

    tracer_provider = register(
        endpoint=f"{endpoint}/v1/traces",
        project_name=project_name,
        batch=True,          # don't block the calling coroutine on export
        set_global_tracer_provider=True,
    )

    # Auto-instrumentation: OpenAI covers Anthropic-compatible... no — OpenAI
    # covers OpenAI's own SDK (used directly by _draft_anthropic's sibling
    # Sarvam path AND by rag/query.py's _embed/_hyde_expand), Anthropic covers
    # anthropic.Anthropic() (generate.py's _client()/_draft_anthropic path).
    from openinference.instrumentation.openai import OpenAIInstrumentor
    from openinference.instrumentation.anthropic import AnthropicInstrumentor

    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)

    _tracer = tracer_provider.get_tracer(__name__)
    logger.info("tracing enabled: project=%s endpoint=%s", project_name, endpoint)


def get_tracer():
    """Returns the tracer for manual spans (retrieval), or None if tracing
    is disabled — every call site must handle None (see manual_retriever_span)
    so instrumentation is genuinely opt-in, never a hard dependency."""
    return _tracer
