import json
import logging
import os
import re
from time import perf_counter
from typing import Any
from uuid import UUID

import ollama
from sqlalchemy.orm import Session

from core.config import DEFAULT_OLLAMA_EMBED_MODEL, DEFAULT_OLLAMA_MODEL
from core.models import LLMCallLog

logger = logging.getLogger(__name__)

# Hard ceiling for structured JSON retries (initial attempt + this many retries).
DEFAULT_JSON_MAX_RETRIES = 1
# Per-call wall-clock timeout for ollama.chat (seconds).
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 90


class LLMError(RuntimeError):
    """Ollama is missing, the model is missing, or the call failed. Fail the run, not the app."""


class LLMTimeoutError(LLMError):
    """Ollama chat exceeded the configured timeout."""


def ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL


def ollama_embed_model() -> str:
    return (
        os.getenv("OLLAMA_EMBED_MODEL", DEFAULT_OLLAMA_EMBED_MODEL).strip()
        or DEFAULT_OLLAMA_EMBED_MODEL
    )


def ollama_timeout_seconds() -> float:
    raw = os.getenv("OLLAMA_TIMEOUT_SECONDS", str(DEFAULT_OLLAMA_TIMEOUT_SECONDS)).strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return float(DEFAULT_OLLAMA_TIMEOUT_SECONDS)


def _list_model_names() -> list[str]:
    listing = ollama.list()
    models = listing.get("models") if isinstance(listing, dict) else getattr(listing, "models", [])
    names: list[str] = []
    for item in models or []:
        name = (
            item.get("model") or item.get("name")
            if isinstance(item, dict)
            else getattr(item, "model", None) or getattr(item, "name", "")
        )
        names.append(str(name))
    return names


def _model_present(wanted: str, names: list[str]) -> bool:
    return any(wanted == name or name.startswith(f"{wanted}:") or wanted in name for name in names)


def ollama_available() -> tuple[bool, str]:
    try:
        names = _list_model_names()
        chat = ollama_model()
        embed = ollama_embed_model()
        missing: list[str] = []
        if not _model_present(chat, names):
            missing.append(chat)
        if not _model_present(embed, names):
            missing.append(embed)
        if missing:
            if names:
                return False, (
                    f"Ollama is running but missing {missing}. "
                    f"Run: " + "; ".join(f"ollama pull {m}" for m in missing)
                )
            return False, f"Ollama is running but has no models. Run: ollama pull {chat}"
        return True, f"Ollama ready (chat={chat}, embed={embed})"
    except Exception as exc:
        return False, f"Cannot reach Ollama ({exc}). Start it with `ollama serve`."


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed one or more texts with the configured Ollama embedding model."""
    if not texts:
        return []
    ok, detail = ollama_available()
    if not ok:
        raise LLMError(detail)

    model = ollama_embed_model()
    vectors: list[list[float]] = []
    try:
        if hasattr(ollama, "embed"):
            response = ollama.embed(model=model, input=texts)
            embeddings = (
                response.get("embeddings")
                if isinstance(response, dict)
                else getattr(response, "embeddings", None)
            )
            if embeddings:
                return [list(map(float, row)) for row in embeddings]

        for text in texts:
            response = ollama.embeddings(model=model, prompt=text)
            emb = (
                response.get("embedding")
                if isinstance(response, dict)
                else getattr(response, "embedding", None)
            )
            if not emb:
                raise LLMError(f"Empty embedding from {model}")
            vectors.append([float(x) for x in emb])
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"Ollama embed failed: {exc}") from exc
    return vectors


def _chat_with_timeout(kwargs: dict[str, Any], timeout_seconds: float) -> Any:
    """Call ollama.chat with an HTTP-level timeout (cancels the request on expiry)."""
    # Prefer Client(timeout=...) so the underlying httpx request aborts instead of
    # leaving a zombie generation holding the GPU/CPU after a soft timeout.
    try:
        client = ollama.Client(timeout=timeout_seconds)
        return client.chat(**kwargs)
    except Exception as exc:
        name = type(exc).__name__
        msg = str(exc).lower()
        if "timeout" in name.lower() or "timeout" in msg or "timed out" in msg:
            raise LLMTimeoutError(
                f"Ollama chat timed out after {timeout_seconds:.0f}s "
                f"(model={kwargs.get('model')})"
            ) from exc
        raise


def call_llm(
    system: str,
    user_message: str,
    json_schema: dict[str, Any] | None = None,
    *,
    session: Session | None = None,
    research_run_id: UUID | None = None,
    stage: str | None = None,
    max_retries: int = DEFAULT_JSON_MAX_RETRIES,
    timeout_seconds: float | None = None,
    num_predict: int | None = None,
) -> dict[str, Any] | str:
    """Call local Ollama. If json_schema is set, return a parsed dict; otherwise return text.

    Structured calls retry at most ``max_retries`` times after the first attempt
    (hard-capped). Each attempt has a wall-clock timeout.
    """
    ok, detail = ollama_available()
    if not ok:
        raise LLMError(detail)

    # Hard cap: never more than 1 initial + 2 retries regardless of caller.
    retries = max(0, min(int(max_retries), 2))
    attempts = 1 + (retries if json_schema is not None else 0)
    timeout = float(timeout_seconds if timeout_seconds is not None else ollama_timeout_seconds())
    last_error: Exception | None = None

    for attempt in range(attempts):
        kwargs: dict[str, Any] = {
            "model": ollama_model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            # qwen3 spends many tokens in "thinking" otherwise; disable for speed/reliability.
            "think": False,
        }
        if num_predict is not None:
            kwargs["options"] = {"num_predict": int(num_predict)}
        if json_schema is not None:
            kwargs["format"] = json_schema
            if attempt > 0:
                kwargs["messages"] = [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": (
                            user_message
                            + "\n\nIMPORTANT: Your previous reply was invalid JSON. "
                            "Reply with a single valid JSON object only, matching the schema."
                        ),
                    },
                ]

        started = perf_counter()
        try:
            response = _chat_with_timeout(kwargs, timeout)
        except LLMTimeoutError as exc:
            last_error = exc
            logger.warning(
                "Ollama timeout attempt %s/%s stage=%s: %s",
                attempt + 1,
                attempts,
                stage,
                exc,
            )
            print(
                f"[llm] TIMEOUT attempt {attempt + 1}/{attempts} stage={stage}: {exc}",
                flush=True,
            )
            continue
        except Exception as exc:
            last_error = LLMError(f"Ollama chat failed: {exc}")
            logger.warning(
                "Ollama error attempt %s/%s stage=%s: %s",
                attempt + 1,
                attempts,
                stage,
                exc,
            )
            print(
                f"[llm] ERROR attempt {attempt + 1}/{attempts} stage={stage}: {exc}",
                flush=True,
            )
            continue
        latency_ms = int((perf_counter() - started) * 1000)

        message = response.get("message") if isinstance(response, dict) else getattr(response, "message", {})
        if isinstance(message, dict):
            content = str(message.get("content") or "")
        else:
            content = str(getattr(message, "content", "") or "")

        prompt_tokens = int(
            response.get("prompt_eval_count") or getattr(response, "prompt_eval_count", 0) or 0
        )
        completion_tokens = int(response.get("eval_count") or getattr(response, "eval_count", 0) or 0)
        model = str(response.get("model") or getattr(response, "model", None) or ollama_model())

        if session is not None and research_run_id is not None and stage:
            session.add(
                LLMCallLog(
                    research_run_id=research_run_id,
                    stage=stage,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    model=model,
                    estimated_cost_usd=0.0,
                )
            )
            session.flush()

        if json_schema is None:
            return content.strip()

        raw = content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_error = LLMError(f"Ollama did not return valid JSON: {exc}\nRaw: {raw[:500]}")
            logger.debug(
                "JSON parse fail attempt %s/%s stage=%s raw_len=%s",
                attempt + 1,
                attempts,
                stage,
                len(raw),
            )
            print(
                f"[llm] JSON parse fail attempt {attempt + 1}/{attempts} "
                f"stage={stage} raw_len={len(raw)}",
                flush=True,
            )
            continue
        if not isinstance(parsed, dict):
            last_error = LLMError("Ollama JSON was not an object.")
            continue
        return parsed

    raise last_error or LLMError("Ollama JSON call failed after retries.")
