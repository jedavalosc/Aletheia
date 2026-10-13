"""Provider-agnostic model calls for agents: Anthropic or any OpenAI-compatible API."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx


@dataclass
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model: str


def complete(settings, system: str, user: str, json_mode: bool = True, max_tokens: int | None = None,
             role: str = "agent") -> Completion:
    """role 'agent' uses AGENT_*; role 'verifier' uses VERIFIER_* (the independent checker)."""
    if role == "verifier":
        provider, model, base_url, key = (settings.verifier_provider, settings.verifier_model,
                                          settings.verifier_base_url, settings.verifier_api_key)
        thinking = settings.verifier_thinking
    else:
        provider, model, base_url, key = (settings.agent_provider, settings.agent_model,
                                          settings.agent_base_url, settings.agent_api_key)
        thinking = settings.agent_thinking
    if not key:
        raise RuntimeError(f"No API key configured for role {role}")
    mt = max_tokens or settings.agent_max_tokens
    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(model=model, max_tokens=mt, system=system,
                                   messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return Completion(text, r.usage.input_tokens, r.usage.output_tokens, model)
    payload = {"model": model, "max_tokens": mt,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if thinking:
        payload["thinking"] = {"type": thinking}
    last = None
    for attempt in range(4):
        try:
            r = httpx.post(base_url.rstrip("/") + "/chat/completions", json=payload, timeout=280,
                           headers={"Authorization": f"Bearer {key}"})
        except httpx.TransportError as e:  # dropped connection or timeout: retry like a 5xx
            last = f"{type(e).__name__}: {e}"
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            d = r.json()
            u = d.get("usage") or {}
            choice = d["choices"][0]
            text = choice["message"].get("content") or ""
            if not text and choice.get("finish_reason") == "length":
                raise RuntimeError(f"{model}: max_tokens={mt} exhausted before any answer (reasoning budget)")
            return Completion(text, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), d.get("model", model))
        if 400 <= r.status_code < 500 and r.status_code != 429:
            raise RuntimeError(f"Provider error {r.status_code}: {r.text[:300]}")
        last = f"{r.status_code}: {r.text[:300]}"
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Provider error: {last}")


def parse_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1])
