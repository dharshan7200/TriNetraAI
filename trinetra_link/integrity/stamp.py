"""Time and place stamps for evidence photos, plus provenance checks.

The original photo is never altered: it is the evidence the pipeline analyses and the evidence chain
seals. A stamped copy, with a strip under the photo showing the journey, checkpoint, time and place,
is rendered from the sealed metadata whenever a person looks at the photo (console, report, export).
Burning text into the original would make the local photo comparison see the changing stamp as a
change to the parcel.
"""
from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from trinetra_link.schema.models import CheckpointObservation, ImageRef

PLACES = {1: "Seller dispatch", 2: "Delivered", 3: "Return pickup", 4: "Warehouse"}
MAX_PHOTO_AGE_MIN = 15.0      # photo taken this long before the checkpoint reached the server -> flag
MAX_SPREAD_M = 200.0          # photos of one checkpoint taken further apart than this -> flag
POOR_ACCURACY_M = 100.0       # location less precise than this -> note

_FONT_CANDIDATES = ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "segoeui.ttf")


def _font(size: int) -> ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_time(ts: Optional[str]) -> str:
    """Show the device time in the timezone it was recorded in, with its offset."""
    d = _parse(ts)
    if d is None:
        return "time not recorded"
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    off = d.utcoffset()
    mins = int(off.total_seconds() // 60) if off is not None else 0
    sign = "+" if mins >= 0 else "-"
    return d.strftime("%Y-%m-%d %H:%M:%S") + f" UTC{sign}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}"


def format_place(im: ImageRef) -> str:
    if im.lat is None or im.lon is None:
        return "location not recorded"
    ns, ew = ("N" if im.lat >= 0 else "S"), ("E" if im.lon >= 0 else "W")
    acc = f" (±{im.geo_accuracy_m:.0f} m)" if im.geo_accuracy_m is not None else ""
    return f"{abs(im.lat):.5f} {ns}, {abs(im.lon):.5f} {ew}{acc}"


def stamp_lines(cp: CheckpointObservation, im: ImageRef) -> List[str]:
    return [
        f"{cp.journey_code}  |  CP{cp.cp_index} {PLACES.get(cp.cp_index, '')}  |  {im.side.upper()}",
        f"{format_time(im.captured_at)}  |  {format_place(im)}",
    ]


def render_stamped(path: Path | str, lines: List[str], max_width: int = 1280, quality: int = 88) -> bytes:
    """JPEG bytes of the photo with a stamp strip added below it (the photo pixels are not touched)."""
    img = Image.open(path).convert("RGB")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    size = max(12, round(img.width / 42))
    font = _font(size)
    pad = round(size * 0.55)
    line_h = round(size * 1.35)
    band = pad * 2 + line_h * len(lines)
    out = Image.new("RGB", (img.width, img.height + band), (23, 32, 51))
    out.paste(img, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.rectangle([0, img.height, img.width, img.height + 3], fill=(242, 183, 5))  # tape-yellow edge
    for i, text in enumerate(lines):
        draw.text((pad, img.height + pad + i * line_h), text, fill=(255, 255, 255) if i == 0 else (200, 210, 222), font=font)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _distance_m(a: ImageRef, b: ImageRef) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def provenance_checks(checkpoints: List[CheckpointObservation]) -> Dict[str, Any]:
    """Plausibility checks on when and where the photos were taken. These are flags for a person to look at;
    they do not change the verdict (a clock can be wrong and indoor location is often imprecise)."""
    flags: List[str] = []
    notes: List[str] = []
    per_cp: Dict[int, Dict[str, Any]] = {}
    for cp in sorted(checkpoints, key=lambda c: c.cp_index):
        located = [im for im in cp.images if im.lat is not None and im.lon is not None]
        timed = [(im, _parse(im.captured_at)) for im in cp.images if _parse(im.captured_at)]
        info: Dict[str, Any] = {"located_photos": len(located), "photos": len(cp.images)}
        if cp.images and not located:
            notes.append(f"CP{cp.cp_index}: no location was recorded for the photos.")
        if located:
            spread = max((_distance_m(a, b) for a in located for b in located), default=0.0)
            info["spread_m"] = round(spread, 1)
            lat = sum(im.lat for im in located) / len(located)
            lon = sum(im.lon for im in located) / len(located)
            info["lat"], info["lon"] = round(lat, 6), round(lon, 6)
            if spread > MAX_SPREAD_M:
                flags.append(f"CP{cp.cp_index}: photos were taken {spread:.0f} m apart, more than {MAX_SPREAD_M:.0f} m for one checkpoint.")
            worst = max((im.geo_accuracy_m or 0.0) for im in located)
            if worst > POOR_ACCURACY_M:
                notes.append(f"CP{cp.cp_index}: location is imprecise (±{worst:.0f} m).")
        if timed and cp.received_at_utc is not None:
            recv = cp.received_at_utc if cp.received_at_utc.tzinfo else cp.received_at_utc.replace(tzinfo=timezone.utc)
            oldest = min(t if t.tzinfo else t.replace(tzinfo=timezone.utc) for _im, t in timed)
            age = (recv - oldest).total_seconds() / 60.0
            info["oldest_photo_age_min"] = round(age, 1)
            if age > MAX_PHOTO_AGE_MIN:
                flags.append(f"CP{cp.cp_index}: a photo was taken {age:.0f} min before the checkpoint was uploaded (an old photo may have been reused).")
            elif age < -2:
                flags.append(f"CP{cp.cp_index}: a photo's time is {-age:.0f} min after it reached the server (the device clock is wrong).")
        per_cp[cp.cp_index] = info
    # the same photo file submitted more than once (for example a checkpoint photographed by copying another's photos)
    seen: Dict[str, str] = {}
    for cp in sorted(checkpoints, key=lambda c: c.cp_index):
        for im in cp.images:
            label = f"CP{cp.cp_index} {im.side.upper()}"
            if im.sha256 in seen:
                flags.append(f"{label} is the same photo file as {seen[im.sha256]} (a photo was reused, so this checkpoint was not photographed).")
            else:
                seen[im.sha256] = label
    # distance between consecutive checkpoints, for context only
    moves = []
    prev = None
    for k in sorted(per_cp):
        if "lat" in per_cp[k]:
            if prev is not None:
                a = ImageRef(side="", path="", sha256="", w=1, h=1, lat=per_cp[prev]["lat"], lon=per_cp[prev]["lon"])
                b = ImageRef(side="", path="", sha256="", w=1, h=1, lat=per_cp[k]["lat"], lon=per_cp[k]["lon"])
                moves.append({"from": prev, "to": k, "km": round(_distance_m(a, b) / 1000.0, 2)})
            prev = k
    any_geo = any(v["located_photos"] for v in per_cp.values())
    any_time = any(im.captured_at for cp in checkpoints for im in cp.images)
    status = "flagged" if flags else ("ok" if (any_geo or any_time) else "not_recorded")
    summary = (flags[0] + (f" (+{len(flags) - 1} more)" if len(flags) > 1 else "")) if flags else (
        "Photo times and places are consistent." if status == "ok" else "No photo time or location was recorded.")
    return {"status": status, "summary": summary, "flags": flags, "notes": notes, "per_checkpoint": per_cp, "moves": moves}
