"""AI provider abstraction. The rest of the app depends ONLY on this module + the registry,
never on a specific vendor. Adding a provider = one class implementing `VisionProvider`.
"""
from typing import Protocol

from pydantic import BaseModel, Field


class Box(BaseModel):
    """Where on the photo something was found. x, y, w, h are fractions of the image (0 to 1) measured from the top-left, so they
    stay right at any zoom. `field` is what it is (lr_no, stamp, signature, delivery_date, quantity_received, remarks)."""

    field: str
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0, le=1)
    h: float = Field(ge=0, le=1)
    text: str | None = None  # the words read inside the box, when there are any
    conf: float | None = Field(default=None, ge=0, le=1)
    source: str = "ocr"  # ocr: found by the text reader | vlm: pointed out by the vision model


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
    boxes: list[Box] = Field(default_factory=list, description="Where each detected field is on the photo (local reader only)")


class ProviderError(Exception):
    """Provider failed (network, quota, bad output). The registry falls back to the next provider."""


class VisionProvider(Protocol):
    name: str

    async def extract(self, image: bytes, mime: str, expected_lr_no: str) -> PodExtraction: ...
