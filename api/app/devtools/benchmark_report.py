"""Builds docs/benchmark/dashboard.html (one self-contained file: results, photo thumbnails, filters) from docs/benchmark/results/*.json.

  .venv/Scripts/python -m app.devtools.benchmark_report
"""
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

BASE = Path(__file__).resolve().parents[3] / "docs" / "benchmark"
TEMPLATE = Path(__file__).with_name("benchmark_dashboard.html")


def thumb(path: Path) -> str:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((900, 1200))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=72)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def safe_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def main() -> None:
    data = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (BASE / "results").glob("*.json")}
    data = dict(sorted(data.items(), key=lambda kv: (kv[1].get("when", ""), kv[0])))  # oldest run first, the latest is shown by default
    if not data:
        sys.exit("no results yet: run app.devtools.benchmark first")
    photos = {c["photo"] for r in data.values() for c in r["cases"].values()}
    thumbs = {name: thumb(BASE / "photos" / name) for name in sorted(photos)}
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/", safe_json(data)).replace("/*THUMBS*/", safe_json(thumbs))
    out = BASE / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(data)} model(s), {len(photos)} photos)")


if __name__ == "__main__":
    main()
