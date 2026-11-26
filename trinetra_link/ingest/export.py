"""Mirror captured journeys into plain folders that people can open and the demo runner can read.

Every time a checkpoint is submitted, the journey is written to

    Real_Inputs/<journey_code>/
        journey.json        all checkpoints recorded so far (weights, scale, seals, IDs, notes)
        readings.csv        the same readings as a table, one row per checkpoint
        images/CP<k>_<SIDE>.jpg          the original photos (analysed and sealed, never altered)
        images_stamped/CP<k>_<SIDE>.jpg  copies with journey, checkpoint, time and location printed under the photo
        scales.json         scale characterisation (created once, edit it with your calibration)

The layout matches TriNetra_Demo_Inputs, so `run_demo_input.py Real_Inputs/<code>` runs it.
The store (SQLite) and the hashed copies under data/artifacts remain the record of truth.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path
from typing import Optional

from trinetra_link.config import REPO_ROOT
from trinetra_link.integrity.stamp import render_stamped, stamp_lines
from trinetra_link.store.database import Store

CP_NAMES = {
    1: "CP1 Seller dispatch (origin hub)",
    2: "CP2 Delivered to customer",
    3: "CP3 Return pickup from customer",
    4: "CP4 Warehouse intake (return hub)",
}


def real_inputs_dir() -> Path:
    return Path(os.getenv("TRINETRA_REAL_INPUTS_DIR", str(REPO_ROOT / "Real_Inputs")))


def export_journey_folder(store: Store, journey_code: str, base_dir: Optional[Path] = None) -> Path:
    """Write the journey's checkpoints and photos to Real_Inputs/<journey_code>/ and return that folder."""
    base = Path(base_dir) if base_dir else real_inputs_dir()
    folder = base / journey_code
    img_dir = folder / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    stamped_dir = folder / "images_stamped"  # for people to look at; the analysis uses images/
    stamped_dir.mkdir(exist_ok=True)

    cps = sorted(store.list_checkpoints(journey_code), key=lambda c: c.cp_index)
    out_cps = []
    for cp in cps:
        d = cp.model_dump(mode="json")
        d["checkpoint_name"] = CP_NAMES.get(cp.cp_index, f"CP{cp.cp_index}")
        images = []
        for im in cp.images:
            src = Path(im.path)
            rel = f"images/CP{cp.cp_index}_{im.side.upper()}.jpg"
            if src.exists():
                shutil.copyfile(src, folder / rel)
                (stamped_dir / Path(rel).name).write_bytes(render_stamped(src, stamp_lines(cp, im)))
            images.append({**im.model_dump(mode="json"), "path": rel})
        d["images"] = images
        d["operator_note"] = cp.carrier_log or ""
        out_cps.append(d)

    journey = {
        "journey_code": journey_code,
        "product": "",
        "source": "Captured with the TriNetra-Link capture page",
        "checkpoints": out_cps,
    }
    (folder / "journey.json").write_text(json.dumps(journey, indent=2), encoding="utf-8")

    with open(folder / "readings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["checkpoint", "time_utc", "received_at_utc", "photo_times", "photo_locations", "reading_1_g", "reading_2_g", "reading_3_g", "scale_id",
                    "scale_status", "seal_qr", "serial", "imei", "identifier_source", "glare_reported",
                    "seals", "photos", "notes"])
        for cp in cps:
            r = list(cp.weights_g) + [""] * (3 - len(cp.weights_g))
            w.writerow([CP_NAMES.get(cp.cp_index, cp.cp_index), cp.ts_utc.isoformat(),
                        cp.received_at_utc.isoformat() if cp.received_at_utc else "",
                        "; ".join(f"{im.side}={im.captured_at}" for im in cp.images if im.captured_at),
                        "; ".join(f"{im.side}={im.lat:.6f},{im.lon:.6f}" + (f" ±{im.geo_accuracy_m:.0f}m" if im.geo_accuracy_m is not None else "")
                                  for im in cp.images if im.lat is not None and im.lon is not None),
                        *r[:3], cp.scale_id,
                        cp.scale_status, cp.seal_qr or "", cp.serial or "", cp.imei or "",
                        cp.identifier_source or "", bool(cp.glare_reported),
                        "; ".join(f"{s.layer}={s.seal_id_read or '-'}:{s.state}" for s in cp.seals),
                        "; ".join(f"CP{cp.cp_index}_{im.side.upper()}.jpg" for im in cp.images),
                        cp.carrier_log or ""])

    scales = folder / "scales.json"
    if not scales.exists():
        ids = sorted({cp.scale_id for cp in cps if cp.scale_id})
        scales.write_text(json.dumps({
            "note": ("Default values. Replace sigma_g with your scale's measured noise: weigh one object 10 "
                     "times and use the standard deviation of the readings. delta_g is the linearity drift."),
            "calibrated": False,
            "scales": {sid: {"scale_id": sid, "sigma_g": 1.0, "delta_g": 0.5} for sid in ids},
        }, indent=2), encoding="utf-8")
    else:  # make sure a newly used scale ID is present
        data = json.loads(scales.read_text(encoding="utf-8"))
        changed = False
        for cp in cps:
            if cp.scale_id and cp.scale_id not in data.setdefault("scales", {}):
                data["scales"][cp.scale_id] = {"scale_id": cp.scale_id, "sigma_g": 1.0, "delta_g": 0.5}
                changed = True
        if changed:
            scales.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return folder
