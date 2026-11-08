"""The AI benchmark: how well the POD reader does on photographed sample sheets, shown on the office "AI benchmark" screen.

It only reads files that the benchmark tool (`app.devtools.benchmark`) wrote under docs/benchmark: the results of each run and the photos.
Nothing here touches the database, and the sheets are printed samples with made-up names, so there is no personal data in them."""
import io
import json
import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from PIL import Image, ImageOps

from app.config import get_settings
from app.models import Role, User
from app.security import require_roles

router = APIRouter(prefix="/benchmark", tags=["benchmark"])
Viewer = Annotated[User, Depends(require_roles(Role.ops, Role.billing, Role.md))]
PHOTO_NAME = re.compile(r"^S\d\d(?:_[a-z]+)?\.(?:jpe?g|png)$")
_thumbs: dict[tuple[str, float], bytes] = {}


def base_dir() -> Path:
    configured = get_settings().benchmark_dir
    return Path(configured) if configured else Path(__file__).resolve().parents[3] / "docs" / "benchmark"


@router.get("/runs")
async def runs(_: Viewer) -> list[dict[str, Any]]:
    """Every saved run, oldest first, each with its labelled cases (what was expected, what the reader read, what the app decided)."""
    out: list[dict[str, Any]] = []
    for p in (base_dir() / "results").glob("*.json"):
        try:
            run = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # a half-written file: skip it, the next look will have it
        out.append({"id": p.stem, **run})
    return sorted(out, key=lambda r: (r.get("when", ""), r["id"]))


@router.get("/photos/{name}")
async def photo(name: str, _: Viewer) -> Response:
    """A photographed sheet, upright and at most 900 px wide, so a page of them loads quickly."""
    path = base_dir() / "photos" / name
    if not PHOTO_NAME.match(name) or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    key = (name, path.stat().st_mtime)
    if key not in _thumbs:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((900, 1200))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=74)
        _thumbs[key] = buf.getvalue()
    return Response(_thumbs[key], media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
