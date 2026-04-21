"""LLM provider abstraction — returns (text, tokens_in, tokens_out) for billing."""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("cluezero.llm")


@dataclass
class LLMResult:
    text: str
    tokens_in: int
    tokens_out: int


class LLMProvider(abc.ABC):
    @abc.abstractmethod
    def analyze_image(self, image_b64: str, prompt: str) -> LLMResult: ...


# ── OpenAI (GPT-4o family) ────────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: Optional[str] = None):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def analyze_image(self, image_b64: str, prompt: str) -> LLMResult:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=4096,
        )
        usage = getattr(resp, "usage", None)
        tin = getattr(usage, "prompt_tokens", 0) or 0
        tout = getattr(usage, "completion_tokens", 0) or 0
        return LLMResult(text=resp.choices[0].message.content or "", tokens_in=tin, tokens_out=tout)


# ── Gemini ────────────────────────────────────────────────────────────────

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-pro"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
        self.model_name = model
        self.model = genai.GenerativeModel(model)

    def analyze_image(self, image_b64: str, prompt: str) -> LLMResult:
        from PIL import Image
        import io
        import base64

        image_data = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_data))
        response = self.model.generate_content([prompt, image])
        text = response.text or ""

        tin = 0
        tout = 0
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            tin = getattr(usage, "prompt_token_count", 0) or 0
            tout = getattr(usage, "candidates_token_count", 0) or 0
        return LLMResult(text=text, tokens_in=tin, tokens_out=tout)


# ── Factory ───────────────────────────────────────────────────────────────

_provider_cache: Optional[LLMProvider] = None


def get_provider() -> LLMProvider:
    global _provider_cache
    if _provider_cache is not None:
        return _provider_cache

    from app.config import settings

    keys = settings.llm_api_keys
    if not keys:
        raise RuntimeError("LLM_API_KEYS not set")

    if settings.llm_provider == "openai":
        _provider_cache = OpenAIProvider(
            api_key=keys.split(",")[0],
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    elif settings.llm_provider == "gemini":
        _provider_cache = GeminiProvider(
            api_key=keys.split(",")[0],
            model=settings.llm_model,
        )
    else:
        raise RuntimeError(f"Unknown LLM provider: {settings.llm_provider}")

    logger.info("LLM provider initialised: %s %s", settings.llm_provider, settings.llm_model)
    return _provider_cache
