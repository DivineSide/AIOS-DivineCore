# -*- coding: utf-8 -*-
"""Shared LLM client + provider routing for the pipeline.

Two providers, with automatic failover:

    PRIMARY  = OpenAI (GPT)      — used for all TEXT calls while credits last
    FALLBACK = Anthropic (Claude) — used automatically when an OpenAI call hits a
               quota / rate / auth error (e.g. 429 insufficient_quota)

The doctrine (LLM-core routing): one place decides the provider + model; every
script calls complete()/complete_vision() and never touches an SDK directly.

Why text-only failover: the extraction/solution prompts + JSON parsing were
tuned to be provider-agnostic (plain text in, JSON out), so GPT and Claude are
interchangeable there. VISION is Claude-first (the message shape differs across
SDKs); it falls back to Claude only — see complete_vision().

Env:
    OPENAI_API_KEY      enables the OpenAI primary (else we start on Claude)
    ANTHROPIC_API_KEY   the Claude fallback (and the vision path)
    LLM_PRIMARY         override: "openai" | "anthropic"  (default "openai")
"""
import base64
import json
import os
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

# ── model registry (per provider, per tier) ─────────────────────────────────
# FAST  = mechanical work (extraction, GK explanations) — cheap models.
# SMART = vision + reasoning/maths — capable models.
MODELS = {
    "openai":    {"fast": "gpt-4o-mini", "smart": "gpt-4o"},
    "anthropic": {"fast": "claude-haiku-4-5-20251001", "smart": "claude-sonnet-4-6"},
}

# Back-compat aliases — older imports expect these names. They now mean a TIER,
# resolved to the active provider's model at call time. Pass "fast"/"smart" (or a
# raw model id) as the `model` arg to complete().
MODEL_FAST  = "fast"
MODEL_SMART = "smart"
MODEL = MODEL_FAST


def _primary() -> str:
    p = (os.environ.get("LLM_PRIMARY") or "openai").lower()
    # If OpenAI is requested but no key is present, start on Anthropic.
    if p == "openai" and not os.environ.get("OPENAI_API_KEY"):
        return "anthropic"
    return p


def load_keys() -> None:
    """Populate API keys from the repo-root .env if not already in the env."""
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PRIMARY"):
        if os.environ.get(key):
            continue
        env = BASE.parent.parent / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{key}="):
                    os.environ[key] = line.split("=", 1)[1].strip()
                    break


# ── lazy SDK clients ──────────────────────────────────────────────────────────
_openai = None
_anthropic = None


def _openai_client():
    global _openai
    if _openai is None:
        load_keys()
        import openai
        _openai = openai.OpenAI()
    return _openai


def _anthropic_client():
    global _anthropic
    if _anthropic is None:
        load_keys()
        import anthropic
        _anthropic = anthropic.Anthropic()
    return _anthropic


# Back-compat: extract_vision.py / generate_solutions.py call client() expecting
# an Anthropic client (vision + the web_search tool are Anthropic-specific).
def client():
    return _anthropic_client()


def _resolve_model(provider: str, model: str) -> str:
    """Map a tier ("fast"/"smart") to the provider's concrete model id; pass any
    other string through unchanged (lets callers pin an exact model)."""
    if model in ("fast", "smart"):
        return MODELS[provider][model]
    return model


def _is_quota_error(exc: Exception) -> bool:
    """True when an OpenAI/Anthropic error means 'out of credits / rate limited /
    auth' — i.e. we should fail over to the other provider."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    signals = ("insufficient_quota", "rate_limit", "ratelimit", "quota",
               "billing", "credit", "authentication", "permission",
               "429", "401", "403")
    return any(s in name or s in msg for s in signals)


# ── the one call everyone uses (text) ────────────────────────────────────────

def complete(system: str, user: str, model: str = "fast",
             max_tokens: int = 4096) -> str:
    """Text completion with automatic OpenAI→Claude failover.

    `model` is a tier ("fast"|"smart") or a concrete model id. Tries the primary
    provider; on a quota/auth/rate error, retries the SAME tier on the fallback.
    Returns the assistant's text.
    """
    load_keys()
    primary = _primary()
    fallback = "anthropic" if primary == "openai" else "openai"

    for provider in (primary, fallback):
        if provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            continue
        if provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
            continue
        try:
            return _complete_one(provider, system, user,
                                 _resolve_model(provider, model), max_tokens)
        except Exception as e:
            if provider == fallback or not _is_quota_error(e):
                raise
            # quota/auth error on primary -> fall through to fallback
            print(f"  [llm] {provider} failed ({type(e).__name__}); "
                  f"falling back to {fallback}", flush=True)
    raise RuntimeError("No usable LLM provider (missing keys?).")


def _complete_one(provider: str, system: str, user: str, model: str,
                  max_tokens: int) -> str:
    if provider == "openai":
        resp = _openai_client().chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""
    # anthropic
    msg = _anthropic_client().messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message_text(msg)


# ── vision (Claude-first; image message shapes differ across SDKs) ───────────

def complete_vision(system: str, user_text: str, images: list[bytes],
                    model: str = "smart", max_tokens: int = 8192) -> str:
    """Vision completion. Starts on Anthropic (the path the extractor was tuned
    on); falls back to OpenAI vision on a quota error. `images` are raw PNG bytes."""
    load_keys()
    primary = _primary()
    # Vision quality is known on Claude — prefer Anthropic regardless of text primary,
    # unless the operator explicitly forces openai primary AND has no anthropic key.
    order = ["anthropic", "openai"] if os.environ.get("ANTHROPIC_API_KEY") else ["openai"]

    last = None
    for provider in order:
        if provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            continue
        try:
            return _vision_one(provider, system, user_text, images,
                               _resolve_model(provider, model), max_tokens)
        except Exception as e:
            last = e
            if not _is_quota_error(e):
                raise
            print(f"  [llm] vision {provider} failed; trying next", flush=True)
    raise last or RuntimeError("No usable vision provider.")


def _vision_one(provider, system, user_text, images, model, max_tokens) -> str:
    if provider == "anthropic":
        content = [{"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.standard_b64encode(img).decode()}} for img in images]
        content.append({"type": "text", "text": user_text})
        msg = _anthropic_client().messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": content}],
        )
        return message_text(msg)
    # openai
    content = [{"type": "image_url", "image_url": {
        "url": "data:image/png;base64," +
               base64.standard_b64encode(img).decode()}} for img in images]
    content.append({"type": "text", "text": user_text})
    resp = _openai_client().chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": content}],
    )
    return resp.choices[0].message.content or ""


# ── helpers (unchanged) ───────────────────────────────────────────────────────

def message_text(msg) -> str:
    """Join all text blocks of an Anthropic message response."""
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def parse_json(text: str):
    """Pull the first JSON object/array out of a model response.

    Tolerates ```json fences and leading prose. Returns the parsed value or
    raises ValueError with the offending text for a clear failure.
    """
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    if not m:
        raise ValueError(f"No JSON found in model output:\n{text[:500]}")
    return json.loads(m.group(0))


# Back-compat shim retained for any caller still importing load_key (singular).
def load_key() -> None:
    load_keys()
