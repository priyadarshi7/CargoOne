"""Deterministic provider for dev/tests. Reads the ground-truth label that the synthetic POD
generator embeds in the PNG metadata, so the whole pipeline can be exercised without a real model."""
import io
import json

from PIL import Image

from app.ai.base import PodExtraction, ProviderError

LABEL_KEY = "cargoone_truth"


class MockProvider:
    name = "mock"

    async def extract(self, image: bytes, mime: str, expected_lr_no: str) -> PodExtraction:
        try:
            with Image.open(io.BytesIO(image)) as im:
                label = im.info.get(LABEL_KEY)
        except OSError as e:
            raise ProviderError("mock: not an image") from e
        if label is None:  # unlabeled photo: behave like a model that sees a poor/unknown image
            return PodExtraction(is_document=False, readable=False, confidence=0.2,
                                 issues=["no synthetic label"])
        return PodExtraction.model_validate(json.loads(label))
