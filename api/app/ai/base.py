"""AI provider abstraction. The rest of the app depends ONLY on this module + the registry,
never on a specific vendor. Adding a provider = one class implementing `VisionProvider`.
"""
from typing import Protocol

from pydantic import BaseModel, Field


class PodExtraction(BaseModel):
    """What a vision model reads off the photo. The image stays the source of truth;
    humans may correct these fields in the review queue."""

    is_document: bool = Field(description="Photo shows a lorry receipt / proof of delivery paper")
    readable: bool = Field(description="Text is sharp enough to read")
    lr_no: str | None = None
    consignee_stamp_present: bool = False
    signature_present: bool = False
    delivery_date: str | None = Field(default=None, description="ISO yyyy-mm-dd if visible")
    quantity_received: str | None = None
    remarks: str | None = Field(default=None, description="Handwritten remarks, verbatim")
    shortage_or_damage: bool = Field(default=False, description="Remarks mention shortage/damage/leakage/broken")
    confidence: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list)


class ProviderError(Exception):
    """Provider failed (network, quota, bad output). The registry falls back to the next provider."""


class VisionProvider(Protocol):
    name: str

    async def extract(self, image: bytes, mime: str, expected_lr_no: str) -> PodExtraction: ...
