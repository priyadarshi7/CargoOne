import asyncio
import base64
import json

import httpx

from app.ai.base import PodExtraction, ProviderError
from app.ai.prompt import POD_PROMPT

TRANSIENT = {429, 500, 502, 503, 504}  # worth a quick retry; anything else fails over immediately
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_s: float = 20.0,
                 transport: httpx.AsyncBaseTransport | None = None,
                 backoff_s: tuple[float, ...] = (0.7, 1.8)) -> None:
        self._backoff = backoff_s
        self._key = api_key
        self._model = model
        self._timeout = timeout_s
        self._transport = transport  # injectable for tests

    async def extract(self, image: bytes, mime: str, expected_lr_no: str) -> PodExtraction:
        if not self._key:
            raise ProviderError("GEMINI_API_KEY not configured")
        body = {
            "contents": [{"parts": [
                {"text": POD_PROMPT},
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}},
            ]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": _gemini_schema(),
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                for delay in (*self._backoff, None):  # retry transient overload, then give up (-> fallback)
                    res = await http.post(
                        ENDPOINT.format(model=self._model), json=body, headers={"x-goog-api-key": self._key}
                    )
                    if res.status_code not in TRANSIENT or delay is None:
                        break
                    await asyncio.sleep(delay)
            res.raise_for_status()
            text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            return PodExtraction.model_validate(json.loads(text))
        except httpx.HTTPStatusError as e:  # status code only - never the body (may echo document text)
            raise ProviderError(f"gemini http {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini network error: {type(e).__name__}") from e
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"gemini returned unusable output: {type(e).__name__}") from e


def _gemini_schema() -> dict:
    """Gemini accepts an OpenAPI-subset schema; derive it from the pydantic model."""
    props = {
        "is_document": {"type": "BOOLEAN"}, "readable": {"type": "BOOLEAN"},
        "lr_no": {"type": "STRING", "nullable": True},
        "consignee_stamp_present": {"type": "BOOLEAN"}, "signature_present": {"type": "BOOLEAN"},
        "delivery_date": {"type": "STRING", "nullable": True},
        "quantity_received": {"type": "STRING", "nullable": True},
        "items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "name": {"type": "STRING", "nullable": True}, "quantity": {"type": "NUMBER", "nullable": True}, "unit": {"type": "STRING", "nullable": True}}}},
        "total_quantity": {"type": "STRING", "nullable": True},
        "remarks": {"type": "STRING", "nullable": True},
        "shortage_or_damage": {"type": "BOOLEAN"}, "confidence": {"type": "NUMBER"},
        "issues": {"type": "ARRAY", "items": {"type": "STRING"}},
    }
    return {"type": "OBJECT", "properties": props,
            "required": ["is_document", "readable", "consignee_stamp_present", "signature_present",
                         "shortage_or_damage", "confidence"]}
