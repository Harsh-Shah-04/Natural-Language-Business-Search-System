"""
Minimal vendor-neutral chat client (M6.2).

Exists so app/intent.py can ask a language model a question without importing
a vendor SDK, and so swapping vendors is an environment change rather than a
code change. Deliberately small: one function, one response shape, no
streaming, no tools, no conversation state. The intent layer needs a single
constrained JSON answer, and nothing here should grow beyond that.

WHY httpx AND NOT A VENDOR SDK
------------------------------
httpx is already in the dependency tree (Starlette pulls it in), so this adds
no new dependency to a project that has kept them deliberately few. Both APIs
below are a single POST with a JSON body; an SDK would buy nothing here and
would couple the project to one vendor's release cadence.

CONFIGURATION -- see backend/.env.example
-----------------------------------------
  LLM_API_KEY           required; absent means "not configured", not an error
  LLM_PROVIDER          anthropic (default) | openai
  LLM_MODEL             defaults to a current Claude model for anthropic;
                        required explicitly for openai
  LLM_BASE_URL          override for gateways / OpenAI-compatible servers
  LLM_TIMEOUT_SECONDS   default 6 -- this call sits in an interactive search
  LLM_MAX_TOKENS        default 400

No key is ever hardcoded and none is logged; is_configured() is what callers
check, and the key itself never leaves this module.

FAILURE CONTRACT
----------------
Every failure -- missing key, timeout, connection error, non-2xx, unparseable
envelope -- raises LLMUnavailableError. Nothing here retries and nothing here
falls back: app/intent.py owns that policy, because only it knows whether
another provider can answer instead.
"""

import os

import httpx

# Provider defaults. The Anthropic default is a current model; override with
# LLM_MODEL. For lower latency in the search path, a smaller/faster model is a
# reasonable trade -- this call is on the interactive path.
_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-5"

_OPENAI_BASE_URL = "https://api.openai.com"

DEFAULT_TIMEOUT_SECONDS = 6.0
DEFAULT_MAX_TOKENS = 400


class LLMUnavailableError(Exception):
    """Raised for any reason the model did not produce usable text."""


def _provider() -> str:
    return os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()


def _api_key() -> str | None:
    key = os.environ.get("LLM_API_KEY", "").strip()
    return key or None


def _timeout() -> float:
    try:
        return float(os.environ.get("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _max_tokens() -> int:
    try:
        return int(os.environ.get("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS))
    except ValueError:
        return DEFAULT_MAX_TOKENS


def is_configured() -> bool:
    """Whether a call could be attempted at all.

    Checked before every call so an unconfigured deployment costs nothing --
    no network, no exception construction, no log noise. An absent key is a
    normal state (the classifier and fixture providers still work), not a
    misconfiguration to complain about.
    """
    if _api_key() is None:
        return False
    if _provider() == "openai" and not os.environ.get("LLM_MODEL", "").strip():
        return False
    return _provider() in ("anthropic", "openai")


def describe() -> str:
    """Provider/model for health reporting. Never includes the key."""
    provider = _provider()
    model = os.environ.get("LLM_MODEL", "").strip() or (
        _ANTHROPIC_DEFAULT_MODEL if provider == "anthropic" else "(unset)"
    )
    return f"{provider}:{model}"


def _anthropic_request(system: str, user: str, prefill: str) -> tuple[str, dict, dict]:
    base = os.environ.get("LLM_BASE_URL", "").strip() or _ANTHROPIC_BASE_URL
    model = os.environ.get("LLM_MODEL", "").strip() or _ANTHROPIC_DEFAULT_MODEL
    messages = [{"role": "user", "content": user}]
    if prefill:
        # Assistant prefill: the reply continues from `prefill` rather than
        # starting fresh, so a response that must be JSON cannot open with
        # "Here is the JSON:" or a markdown fence. Cheaper and more reliable
        # than parsing prose back out afterwards.
        messages.append({"role": "assistant", "content": prefill})
    return (
        f"{base}/v1/messages",
        {
            "x-api-key": _api_key() or "",
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        {
            "model": model,
            "max_tokens": _max_tokens(),
            "temperature": 0,
            "system": system,
            "messages": messages,
        },
    )


def _openai_request(system: str, user: str, prefill: str) -> tuple[str, dict, dict]:
    base = os.environ.get("LLM_BASE_URL", "").strip() or _OPENAI_BASE_URL
    model = os.environ.get("LLM_MODEL", "").strip()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if prefill:
        messages.append({"role": "assistant", "content": prefill})
    return (
        f"{base}/v1/chat/completions",
        {
            "Authorization": f"Bearer {_api_key() or ''}",
            "Content-Type": "application/json",
        },
        {
            "model": model,
            "max_tokens": _max_tokens(),
            "temperature": 0,
            "messages": messages,
        },
    )


def _extract(provider: str, payload: dict) -> str:
    if provider == "anthropic":
        blocks = payload.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    else:
        choices = payload.get("choices") or []
        text = (choices[0].get("message") or {}).get("content", "") if choices else ""
    if not text.strip():
        raise LLMUnavailableError("model returned no text")
    return text


def complete(system: str, user: str, prefill: str = "") -> str:
    """One completion, as raw text. Raises LLMUnavailableError on any failure.

    `prefill` seeds the assistant turn (see _anthropic_request). The caller is
    responsible for prepending it to the returned text if it needs the whole
    string back -- this function returns only what the model generated.
    """
    if not is_configured():
        raise LLMUnavailableError("LLM_API_KEY is not set")

    provider = _provider()
    build = _anthropic_request if provider == "anthropic" else _openai_request
    url, headers, body = build(system, user, prefill)

    try:
        response = httpx.post(url, headers=headers, json=body, timeout=_timeout())
    except httpx.TimeoutException as e:
        raise LLMUnavailableError(f"timed out after {_timeout()}s") from e
    except httpx.HTTPError as e:
        raise LLMUnavailableError(f"request failed: {type(e).__name__}") from e

    if response.status_code >= 400:
        # Status and provider only. A response body can echo the request, and
        # the request carries the user's query -- not something to put in a log
        # line by default.
        raise LLMUnavailableError(f"{provider} returned HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as e:
        raise LLMUnavailableError("response was not JSON") from e

    return _extract(provider, payload)
