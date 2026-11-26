"""Tamper-evident evidence chain for checkpoint records.

Each checkpoint record is sealed with a SHA-256 fingerprint of its own content (readings, scale,
seals, identifiers, notes and the SHA-256 of every photo) together with the fingerprint of the
previous checkpoint. Changing any recorded value, replacing a photo, or removing or swapping a
record breaks the chain at that point, so anyone can check that the evidence is the evidence that
was captured. No blockchain or server is needed: the check runs on the journey data alone.

The fingerprint deliberately excludes file paths, so a journey stays verifiable after it is copied
or exported to another folder.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from trinetra_link.schema.models import CheckpointObservation

CHAIN_VERSION = "trinetra-chain/v1"


def genesis_hash(journey_code: str) -> str:
    """Fixed starting link for a journey, so CP1 is bound to its journey code."""
    return hashlib.sha256(f"{CHAIN_VERSION}|genesis|{journey_code}".encode("utf-8")).hexdigest()


def _ts(ts: datetime) -> str:
    ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _photo_entry(im: Any) -> List[Any]:
    entry: List[Any] = [im.side, im.sha256, im.w, im.h]
    extra = {k: getattr(im, k, None) for k in ("captured_at", "lat", "lon", "geo_accuracy_m")}
    extra = {k: v for k, v in extra.items() if v is not None}
    if extra:  # time and place of the photo are sealed too (omitted when absent, so older records keep their hash)
        entry.append(extra)
    return entry


def record_payload(cp: CheckpointObservation) -> Dict[str, Any]:
    """The content that the fingerprint covers (everything recorded, no file paths)."""
    payload = {
        "journey_code": cp.journey_code,
        "cp_index": cp.cp_index,
        "ts_utc": _ts(cp.ts_utc),
        "device_id": cp.device_id,
        "operator_id": cp.operator_id,
        "weights_g": [float(w) for w in cp.weights_g],
        "scale_id": cp.scale_id,
        "scale_status": cp.scale_status,
        "calibration_date": cp.calibration_date,
        "photos": sorted((_photo_entry(im) for im in cp.images), key=lambda e: (e[0], e[1])),
        "seals": [[s.layer, s.seal_id_read, s.state] for s in cp.seals],
        "seal_qr": cp.seal_qr,
        "serial": cp.serial,
        "imei": cp.imei,
        "carrier_log": cp.carrier_log,
        "identifier_source": cp.identifier_source,
        "glare_reported": cp.glare_reported,
        "permitted_packaging_change": cp.permitted_packaging_change,
        "tare_delta_g": float(cp.tare_delta_g),
    }
    if cp.received_at_utc is not None:
        payload["received_at_utc"] = _ts(cp.received_at_utc)
    return payload


def compute_record_hash(cp: CheckpointObservation, prev_hash: Optional[str]) -> str:
    body = {"v": CHAIN_VERSION, "prev": prev_hash, "record": record_payload(cp)}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def seal_checkpoint(cp: CheckpointObservation, prev_hash: Optional[str]) -> CheckpointObservation:
    """Return a copy of the checkpoint carrying its link to the previous record and its own fingerprint."""
    sealed = cp.model_copy(update={"prev_record_hash": prev_hash})
    return sealed.model_copy(update={"record_hash": compute_record_hash(sealed, prev_hash)})


def seal_journey(checkpoints: Iterable[CheckpointObservation]) -> List[CheckpointObservation]:
    """Seal a whole journey in checkpoint order (used when building journeys offline)."""
    out: List[CheckpointObservation] = []
    for cp in sorted(checkpoints, key=lambda c: c.cp_index):
        prev = out[-1].record_hash if out else genesis_hash(cp.journey_code)
        out.append(seal_checkpoint(cp, prev))
    return out


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_chain(checkpoints: Iterable[CheckpointObservation], check_photos: bool = True) -> Dict[str, Any]:
    """Check every link and fingerprint, and (optionally) that each photo file still matches its recorded hash.

    status: "intact"   every record sealed, linked and unchanged, every photo matches
            "broken"   something was changed, replaced or removed after capture (see problems)
            "unsealed" the records were made without a chain (older captures), nothing to verify
    """
    cps = sorted(checkpoints, key=lambda c: c.cp_index)
    if not cps or all(not c.record_hash for c in cps):
        return {"status": "unsealed", "records": [], "problems": [], "photos_checked": 0,
                "summary": "These records were captured without an evidence chain, so they cannot be verified."}

    records: List[Dict[str, Any]] = []
    problems: List[str] = []
    photos_checked = 0
    expected_prev = genesis_hash(cps[0].journey_code)
    for i, cp in enumerate(cps):
        issues: List[str] = []
        if not cp.record_hash:
            issues.append("record has no fingerprint (added without the chain)")
        else:
            if cp.prev_record_hash != expected_prev:
                where = "the journey start" if i == 0 else f"CP{cps[i - 1].cp_index}"
                issues.append(f"link to {where} does not match (a record was removed, replaced or reordered)")
            if compute_record_hash(cp, cp.prev_record_hash) != cp.record_hash:
                issues.append("recorded values were changed after capture")
        if check_photos:
            for im in cp.images:
                p = Path(im.path)
                if not p.exists():
                    issues.append(f"{im.side} photo file is missing")
                    continue
                photos_checked += 1
                if _file_sha256(p) != im.sha256:
                    issues.append(f"{im.side} photo was replaced or edited after capture")
        records.append({"k": cp.cp_index, "ok": not issues, "issues": issues,
                        "record_hash": cp.record_hash, "prev_record_hash": cp.prev_record_hash})
        problems += [f"CP{cp.cp_index}: {msg}" for msg in issues]
        expected_prev = cp.record_hash
    status = "intact" if not problems else "broken"
    summary = (f"Evidence intact: {len(cps)} linked records and {photos_checked} photos match what was captured."
               if status == "intact" else
               f"Evidence altered after capture: {problems[0]}" + (f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""))
    return {"status": status, "records": records, "problems": problems, "photos_checked": photos_checked,
            "summary": summary}
