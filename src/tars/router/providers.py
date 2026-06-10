from __future__ import annotations

import time
from dataclasses import dataclass

import litellm

from tars.router.receipt import Receipt, estimate_cost_inr


@dataclass
class ModelResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    provider: str
    latency_ms: int
    receipt: Receipt


async def call_model(
    messages: list[dict],
    model: str,
    provider: str,
    tier: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    session_id: str | None = None,
    episode_id: str | None = None,
    task_class: str | None = None,
    stakes: str | None = None,
) -> ModelResponse:
    litellm_model = _resolve_litellm_model(provider, model)
    start = time.monotonic()

    response = await litellm.acompletion(
        model=litellm_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    elapsed_ms = int((time.monotonic() - start) * 1000)

    usage = response.usage
    prompt_tok = usage.prompt_tokens if usage else 0
    completion_tok = usage.completion_tokens if usage else 0
    total_tok = (usage.total_tokens if usage else 0) or (prompt_tok + completion_tok)

    content = response.choices[0].message.content or ""

    cost = estimate_cost_inr(model, prompt_tok, completion_tok)
    if provider == "ollama":
        cost = 0.0

    receipt = Receipt(
        session_id=session_id,
        episode_id=episode_id,
        tier=tier,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tok,
        completion_tokens=completion_tok,
        total_tokens=total_tok,
        cost_inr=cost,
        latency_ms=elapsed_ms,
        task_class=task_class,
        stakes=stakes,
    )

    return ModelResponse(
        content=content,
        prompt_tokens=prompt_tok,
        completion_tokens=completion_tok,
        total_tokens=total_tok,
        model=model,
        provider=provider,
        latency_ms=elapsed_ms,
        receipt=receipt,
    )


def _resolve_litellm_model(provider: str, model: str) -> str:
    if provider == "ollama":
        return f"ollama/{model}"
    if provider == "anthropic":
        return model
    if provider == "openai":
        return model
    return f"{provider}/{model}"
