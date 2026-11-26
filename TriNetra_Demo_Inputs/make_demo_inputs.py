"""Generate the five TriNetra-Link demo inputs (one folder per output type).

Every image and number here is SIMULATED for demonstration. Each folder holds one parcel
journey (4 checkpoints) built so the real pipeline returns one specific output type.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

from trinetra_link.integrity.chain import seal_journey
from trinetra_link.schema.models import CheckpointObservation
from trinetra_link.sim.simulator import SimConfig, _apply_marks, _capture, _surface_texture

OUT = Path(sys.argv[1]).resolve()
CFG = SimConfig()
SCALES = {
    "synthetic": True,
    "note": "Demo scale characterisation (simulated): sigma = noise SD, delta = linearity drift, grams.",
    "scales": {
        "SCALE_HUB_01": {"scale_id": "SCALE_HUB_01", "sigma_g": 0.5, "delta_g": 0.1},
        "SCALE_DOOR_02": {"scale_id": "SCALE_DOOR_02", "sigma_g": 1.0, "delta_g": 0.2},
        "SCALE_RET_03": {"scale_id": "SCALE_RET_03", "sigma_g": 1.0, "delta_g": 0.2},
        "SCALE_WH_04": {"scale_id": "SCALE_WH_04", "sigma_g": 0.5, "delta_g": 0.1},
    },
}
CP_NAMES = {1: "CP1 Seller dispatch (origin hub)", 2: "CP2 Delivered to customer",
            3: "CP3 Return pickup from customer", 4: "CP4 Warehouse intake (return hub)"}
CP_SCALE = {1: "SCALE_HUB_01", 2: "SCALE_DOOR_02", 3: "SCALE_RET_03", 4: "SCALE_WH_04"}


def face(side: str, product: str, seal_text: str, serial: str) -> np.ndarray:
    """Clean image of one parcel face with the product name on the shipping label."""
    w, h = 640, 480
    img = np.full((h, w, 3), (196, 194, 190), np.uint8)
    for x in range(0, w, 40):
        cv2.line(img, (x, 0), (x, h), (184, 182, 179), 1)
    for y in range(0, h, 40):
        cv2.line(img, (0, y), (w, y), (184, 182, 179), 1)
    if side == "TOP":
        cv2.rectangle(img, (110, 75), (530, 405), (138, 178, 206), -1)
        cv2.rectangle(img, (110, 75), (530, 405), (88, 126, 155), 3)
        cv2.rectangle(img, (310, 75), (330, 405), (200, 222, 232), -1)
        cv2.rectangle(img, (210, 215), (430, 265), (210, 140, 0), -1)
        cv2.putText(img, seal_text[:18], (218, 247), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    elif side == "LABEL":
        cv2.rectangle(img, (100, 80), (540, 400), (128, 168, 195), -1)
        cv2.rectangle(img, (150, 120), (490, 360), (200, 202, 203), -1)
        cv2.rectangle(img, (150, 120), (490, 160), (90, 60, 40), -1)
        cv2.putText(img, "TRINETRA DEMO SHIPPING", (165, 147), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(img, product.upper()[:24], (165, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2)
        cv2.putText(img, f"SN {serial}", (165, 222), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1)
        bx = 170
        for bw in (3, 1, 4, 2, 5, 2, 3, 1, 4, 2, 3, 5, 2, 4, 1, 3, 2, 5, 3):
            cv2.rectangle(img, (bx, 255), (bx + bw, 325), (0, 0, 0), -1)
            bx += bw + 4
    else:  # SEAL close-up
        cv2.rectangle(img, (80, 120), (560, 360), (130, 170, 200), -1)
        cv2.rectangle(img, (120, 180), (520, 290), (210, 140, 0), -1)
        cv2.putText(img, seal_text[:22], (135, 245), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(img, "SIMULATED DEMO IMAGE", (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 180), 1)
    return img


def make_journey(folder: str, code: str, product: str, mass_g: float, seed: int, cps_spec: dict,
                 expected: dict, story: str) -> None:
    d = OUT / folder
    if d.exists():
        shutil.rmtree(d)
    (d / "images").mkdir(parents=True)
    rng = np.random.default_rng(seed)
    t0 = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    tag = hashlib.sha1(code.encode()).hexdigest()[:6].upper()
    serial0 = f"SN{tag}"
    imei0 = f"35{int(tag, 16) % 10**13:013d}" if cps_spec.get("imei") else None
    ids = {"L1_FWD": f"FWD-{tag}", "L1_RET": f"RET-{tag}", "L2_BOX": f"BOX-{tag}", "L3_ITEM": f"TAG-{tag}"}

    checkpoints = []
    for k in (1, 2, 3, 4):
        s = cps_spec[k]
        sigma = SCALES["scales"][CP_SCALE[k]]["sigma_g"]
        true_mass = s.get("mass", mass_g)
        if s.get("scale_error"):
            readings, status = [], "ERROR"
        else:
            readings = [round(float(true_mass + n), 2) for n in rng.normal(0.0, sigma * 0.8, size=3)]
            status = "OK"
        # layered seals: forward flyer at CP1-CP2, return flyer at CP3-CP4, box and item seals throughout
        seals = []
        outer = "L1_FWD" if k <= 2 else "L1_RET"
        for layer in (outer, "L2_BOX", "L3_ITEM"):
            sid, state = ids[layer], "INTACT"
            ov = s.get("seals", {}).get(layer)
            if ov:
                sid, state = ov.get("id", sid), ov.get("state", state)
            seals.append({"layer": layer, "seal_id_read": sid, "state": state})
        serial = s.get("serial", serial0)
        box_seal = next(x["seal_id_read"] or "" for x in seals if x["layer"] == "L2_BOX")
        images = []
        for side in ("TOP", "LABEL", "SEAL"):
            base = face(side, product, box_seal if side != "LABEL" else "", serial)
            tex_seed = int(hashlib.sha1(f"{code}:{side}".encode()).hexdigest()[:8], 16)
            base = np.clip(base.astype(np.float32) + _surface_texture(base.shape, tex_seed), 0, 255).astype(np.uint8)
            marked = _apply_marks(base, side, s.get("tamper_marks", 0.0), s.get("dent", 0.0), rng)
            shot = _capture(marked, CFG, rng, dark=s.get("dark", False), blur=s.get("blur", False),
                            glare=s.get("glare", False))
            rel = f"images/CP{k}_{side}.jpg"
            cv2.imwrite(str(d / rel), shot, [cv2.IMWRITE_JPEG_QUALITY, 88])
            images.append({"side": side, "path": rel, "sha256": hashlib.sha256((d / rel).read_bytes()).hexdigest(),
                           "w": 640, "h": 480})
        checkpoints.append({
            "journey_code": code, "cp_index": k, "checkpoint_name": CP_NAMES[k],
            "ts_utc": (t0 + timedelta(days=[0, 2, 9, 11][k - 1], hours=k)).isoformat(),
            "device_id": f"DEMO_PHONE_{k}", "operator_id": f"OP_DEMO_{k}",
            "weights_g": readings, "scale_id": CP_SCALE[k], "scale_status": status,
            "seal_qr": ids["L2_BOX"] if not s.get("seals", {}).get("L2_BOX") else s["seals"]["L2_BOX"].get("id"),
            "serial": serial, "imei": s.get("imei_value", imei0),
            "identifier_source": s.get("identifier_source", "scanned"),
            "glare_reported": bool(s.get("glare_reported", False)),
            "permitted_packaging_change": False, "tare_delta_g": 0.0,
            "seals": seals, "images": images,
            "operator_note": s.get("note", ""),
        })

    # Seal the checkpoints into an evidence chain (fingerprints cover readings, seals, IDs and photo hashes)
    models = [CheckpointObservation(**{k: v for k, v in c.items() if k in CheckpointObservation.model_fields})
              for c in checkpoints]
    for c, sealed in zip(checkpoints, seal_journey(models)):
        c["prev_record_hash"], c["record_hash"] = sealed.prev_record_hash, sealed.record_hash

    journey = {
        "journey_code": code,
        "product": product,
        "SIMULATED": "Demo input generated for illustration. Not a real parcel.",
        "checkpoints": checkpoints,
    }
    (d / "journey.json").write_text(json.dumps(journey, indent=2), encoding="utf-8")
    (d / "scales.json").write_text(json.dumps(SCALES, indent=2), encoding="utf-8")
    (d / "expected_output.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")
    rows = []
    for c in checkpoints:
        w = c["weights_g"]
        rows.append(f"| {c['checkpoint_name']} | {', '.join(f'{x:.2f}' for x in w) if w else 'scale ERROR'} | "
                    f"{c['operator_note'] or '-'} |")
    readme = f"""# {folder}

**Product:** {product}
**Journey code:** {code}
**Expected output:** `{expected['label']}`

## Story
{story}

## What was recorded
| Checkpoint | Weight readings (g) | Note |
|---|---|---|
""" + "\n".join(rows) + f"""

## Run it
From the TriNetraAI project folder (virtual environment active):
```
python TriNetra_Demo_Inputs/run_demo_input.py TriNetra_Demo_Inputs/{folder}
```

All images and readings in this folder are SIMULATED for demonstration.
"""
    (d / "README.md").write_text(readme, encoding="utf-8")
    print("wrote", folder)


# ---------------------------------------------------------------- 1. Legitimate: cotton dress
make_journey(
    "input1_Legitimate", "DEMO-DRESS-0001", "Cotton Dress", 455.0, 101,
    {1: {}, 2: {}, 3: {}, 4: {}},
    {"label": "ATTR_CONFIRMED_LEGITIMATE", "meaning": "Nothing changed at any checkpoint; refund can be approved."},
    "A customer orders a cotton dress (380 g + 75 g packaging), it does not fit, and they return it "
    "unopened. Every checkpoint has good photos, a stable scale and intact seals.",
)

# ---------------------------------------------------------------- 2. Stage found: smartphone, return courier
make_journey(
    "input2_Stage_Fault_Return_Courier", "DEMO-PHONE-0002", "Smartphone", 295.0, 202,
    {1: {"imei": True}, 2: {}, 3: {},
     4: {"mass": 210.0, "tamper_marks": 0.9, "serial": "SNXX0000", "imei_value": "350000000000000",
         "seals": {"L1_RET": {"id": "RET-FAKE99", "state": "INTACT"}, "L3_ITEM": {"id": None, "state": "MISSING"}},
         "note": "Return flyer seal ID differs; item tag missing; box re-taped"}},
    {"label": "ATTR_STAGE_REVERSE_TRANSIT", "meaning": "Changed between CP3 (return pickup) and CP4 (warehouse): "
     "the return courier stage S3 is responsible, not the customer."},
    "A smartphone (220 g + 75 g packaging) is delivered and returned by the customer intact. Between the "
    "return pickup (CP3) and the warehouse (CP4) the box is opened, the phone is swapped for a lighter "
    "dummy and the return flyer is re-sealed. The warehouse sees 85 g missing.",
)
# fix: make IMEI present at all checkpoints for the phone
p = OUT / "input2_Stage_Fault_Return_Courier" / "journey.json"
j = json.loads(p.read_text())
imei = j["checkpoints"][0]["imei"]
for c in j["checkpoints"][1:3]:
    c["imei"] = imei
_models = [CheckpointObservation(**{k: v for k, v in c.items() if k in CheckpointObservation.model_fields})
           for c in j["checkpoints"]]
for c, sealed in zip(j["checkpoints"], seal_journey(_models)):
    c["prev_record_hash"], c["record_hash"] = sealed.prev_record_hash, sealed.record_hash
p.write_text(json.dumps(j, indent=2))

# ---------------------------------------------------------------- 3. Abstain degraded (middle stop): smartwatch
make_journey(
    "input3_Abstain_Degraded_Middle_Stop", "DEMO-WATCH-0003", "Smartwatch", 137.0, 303,
    {1: {}, 2: {},
     3: {"scale_error": True, "dark": True, "blur": True, "identifier_source": "photo",
         "note": "Night pickup: scale showed ERROR, photos dark and blurred"},
     4: {"mass": 95.0, "tamper_marks": 0.9,
         "seals": {"L2_BOX": {"id": "BOX-NEW777", "state": "INTACT"}, "L3_ITEM": {"id": None, "state": "MISSING"}},
         "note": "Box seal ID differs; item tag missing"}},
    {"label": "ATTR_ABSTAIN_DEGRADED", "meaning": "The change happened after CP2, but CP3's evidence is unusable, "
     "so customer (S2) and return courier (S3) cannot be separated. Send to manual review."},
    "A smartwatch (62 g + 75 g packaging) is delivered fine. The return pickup (CP3) happens at night: the "
    "scale shows ERROR and the photos are dark and blurred. At the warehouse (CP4) the watch is missing. "
    "It could have been taken by the customer or by the return courier.",
)

# ---------------------------------------------------------------- 4. Abstain degraded (no reference): running shoes
make_journey(
    "input4_Abstain_No_Reference", "DEMO-SHOES-0004", "Running Shoes", 975.0, 404,
    {1: {"scale_error": True, "dark": True, "blur": True, "identifier_source": "photo",
         "note": "Seller packed in a dark store room: scale ERROR, photos dark and blurred"},
     2: {}, 3: {},
     4: {"mass": 655.0, "tamper_marks": 0.8, "note": "One shoe missing (320 g lighter)"}},
    {"label": "ATTR_ABSTAIN_DEGRADED", "meaning": "CP1, the reference everything is compared with, is unusable, "
     "so no change can be measured. Recapture or manual review."},
    "A pair of running shoes (900 g + 75 g packaging). The seller's dispatch record (CP1) is useless: the "
    "scale errored and the photos are dark and blurred. Later checkpoints are fine and the warehouse "
    "finds one shoe missing, but there is no trustworthy reference to compare against.",
)

# ---------------------------------------------------------------- 5. Abstain indistinguishable: headphones
make_journey(
    "input5_Abstain_Indistinguishable_Glare", "DEMO-HEADPH-0005", "Wireless Headphones", 325.0, 505,
    {1: {}, 2: {},
     3: {"glare": True, "glare_reported": True, "dent": 0.9, "note": "Strong glare over the box top (reported)"},
     4: {"glare": True, "glare_reported": True, "dent": 0.9, "note": "Strong glare over the box top (reported)"}},
    {"label": "ATTR_ABSTAIN_INDISTINGUISHABLE", "meaning": "Weight and seals never change; only the photos could "
     "show the damage, and glare hides it at both later checkpoints. Stage cannot be separated."},
    "Wireless headphones (250 g + 75 g packaging). The box gets a crushed corner, but nothing is removed: "
    "the weight and all seals stay the same. The only evidence would be in the photos, and strong glare "
    "covers the box top at both the return pickup (CP3) and the warehouse (CP4).",
)
