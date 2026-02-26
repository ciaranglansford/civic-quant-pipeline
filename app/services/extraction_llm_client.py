from __future__ import annotations

import json
from dataclasses import dataclass

import httpx


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class LlmResponse:
    model_name: str
    raw_text: str


class OpenAiExtractionClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        endpoint: str = "https://api.openai.com/v1/chat/completions",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.endpoint = endpoint

    def extract(self, prompt_text: str) -> LlmResponse:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "Return only strict JSON matching the requested schema."},
                {"role": "user", "content": prompt_text},
            ],
        }

        last_error: Exception | None = None
        for _ in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    r = client.post(self.endpoint, headers=headers, json=payload)
                r.raise_for_status()
                body = r.json()
                raw_text = body["choices"][0]["message"]["content"].strip()
                if not raw_text:
                    raise ProviderError("empty model response")
                return LlmResponse(model_name=self.model, raw_text=raw_text)
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ProviderError) as e:
                last_error = e
        raise ProviderError(f"openai request failed after retries: {type(last_error).__name__}")
