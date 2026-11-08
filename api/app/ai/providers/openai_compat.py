"""A vision model behind an OpenAI-style chat API (Groq today; xAI Grok, OpenRouter or Together use the same shape).

The photo goes in as a data URL, the answer comes back as JSON in the model's own words and is checked against `PodExtraction`:
a reply that is not valid JSON, or has the wrong shape, is a ProviderError, so the app falls back or sends the POD to a person. Only the
status code is ever put in an error (a body can echo document text)."""
import asyncio
import base64
import json
import re
from collections.abc import Callable

import httpx

from app.ai.base import PodExtraction, ProviderError
from app.ai.prompt import POD_PROMPT

TRANSIENT = {429, 500, 502, 503, 504}

SHAPE = """Reply with ONE JSON object and nothing else, with exactly these keys:
{"is_document": bool, "readable": bool, "lr_no": string|null, "consignee_stamp_present": bool, "signature_present": bool,
 "delivery_date": "yyyy-mm-dd"|null, "quantity_received": string|null,
 "items": [{"name": string|null, "quantity": number|null, "unit": string|null}], "total_quantity": string|null,
 "remarks": string|null, "shortage_or_damage": bool, "confidence": number 0..1, "issues": [string]}"""


def _json_in(text: str) -> dict:
    """The JSON object in a reply, also when a model wraps it in a code fence or adds a sentence before it."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start:end + 1])


class OpenAICompatProvider:
    def __init__(self, name: str, url: str, key: str, model: str, timeout_s: float = 60.0, transport: httpx.AsyncBaseTransport | None = None,
                 backoff_s: tuple[float, ...] = (4.0, 12.0, 30.0), ocr: Callable[[bytes], list] | None = None) -> None:
        self._ocr = ocr  # a document reader (glm-ocr): its text goes in the prompt beside the photo
        self.name, self._url, self._key, self._model, self._timeout, self._transport, self._backoff = name, url.rstrip("/"), key, model, timeout_s, transport, backoff_s

    async def extract(self, image: bytes, mime: str, expected_lr_no: str) -> PodExtraction:
        if not self._key:
            raise ProviderError(f"{self.name}: no API key configured")
        prompt = POD_PROMPT + "\n\n" + SHAPE
        if self._ocr is not None:
            lines = await asyncio.to_thread(self._ocr, image)
            prompt += ("\n\nA text reader already read this paper. Its lines, in page order (a goods-table row reads: no., good, printed packages, "
                       "printed weight, then what the receiver wrote):\n" + "\n".join(f"{ln.id}: {ln.text}" for ln in lines))
        body = {
            "model": self._model, "temperature": 0, "max_tokens": 1200, "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"}},
            ]}],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                for delay in (*self._backoff, None):  # a rate limit or an overloaded model is worth a short wait, then the next provider
                    res = await http.post(f"{self._url}/chat/completions", json=body, headers={"Authorization": f"Bearer {self._key}"})
                    if res.status_code not in TRANSIENT or delay is None:
                        break
                    try:  # a rate limit says how long to wait; use it (capped) instead of guessing
                        wait = min(float(res.headers["retry-after"]), 60.0) + 1.0 if res.status_code == 429 else delay
                    except (KeyError, ValueError):
                        wait = delay
                    await asyncio.sleep(wait)
            res.raise_for_status()
            try:
                return PodExtraction.model_validate(_json_in(res.json()["choices"][0]["message"]["content"]))
            except ValueError:  # a malformed answer is worth one more ask; the model is not deterministic at the edges
                async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                    again = await http.post(f"{self._url}/chat/completions", json=body, headers={"Authorization": f"Bearer {self._key}"})
                again.raise_for_status()
                return PodExtraction.model_validate(_json_in(again.json()["choices"][0]["message"]["content"]))
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"{self.name} http {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} network error: {type(e).__name__}") from e
        except (KeyError, IndexError, ValueError, TypeError) as e:  # ValueError covers bad JSON and a reply that fails validation
            raise ProviderError(f"{self.name} returned unusable output: {type(e).__name__}") from e
