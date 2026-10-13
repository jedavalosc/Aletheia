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


def complete(settings, system: str, user: str, json_mode: bool = True, max_tokens: int | None = None) -> Completion:
    key = settings.agent_api_key
    if not key:
        raise RuntimeError("No agent API key configured (AGENT_API_KEY / CHAT_API_KEY / ANTHROPIC_API_KEY)")
    mt = max_tokens or settings.agent_max_tokens
    if settings.agent_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(model=settings.agent_model, max_tokens=mt, system=system,
                                   messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return Completion(text, r.usage.input_tokens, r.usage.output_tokens, settings.agent_model)
    payload = {"model": settings.agent_model, "max_tokens": mt,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    last = None
    for attempt in range(4):
        r = httpx.post(settings.agent_base_url.rstrip("/") + "/chat/completions", json=payload, timeout=180,
                       headers={"Authorization": f"Bearer {key}"})
        if r.status_code == 200:
            d = r.json()
            u = d.get("usage") or {}
            return Completion(d["choices"][0]["message"].get("content") or "", u.get("prompt_tokens", 0),
                              u.get("completion_tokens", 0), d.get("model", settings.agent_model))
        last = f"{r.status_code}: {r.text[:300]}"
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Provider error: {last}")


def parse_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1])
