"""Parametric simulator for the TriNetra-Link simulation study.

Every output of this module is SIMULATED. It is a stress test of the method under a
generative model written down in advance, not evidence about real parcels.

Design rules (to keep the benchmark from being built around the method):

* Nuisance effects (scale faults, dark or blurred photos, glare nobody flagged, seal and
  serial misreads, pose and lighting changes, humidity drift) are drawn independently of
  the scenario cell, with the same probabilities for every journey.
* Tamper strength is drawn from wide distributions that include signals below the
  detection limits (weight-matched swaps, a few grams, cloned seals, faint marks), so some
  tampering is physically undetectable by any method that uses these modalities.
* Ground truth follows the protocol rule (``derive_ground_truth``): a journey is
  non-determinable only when a checkpoint bounding the staged interval is *unusable*
  (scale and photos both failed) or when glare deliberately hides the defect at both
  bounding checkpoints. Single-modality failures never change the truth.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from trinetra_link.schema.models import CheckpointObservation, ImageRef, Journey, SealObservation
from trinetra_link.staging.assign import CELL_QUOTAS
from trinetra_link.staging.determinability import derive_ground_truth
from trinetra_link.store.database import Store

SIM_WATERMARK = "SIMULATED"
CALIBRATION_FRACTION = 0.20

ITEMS = [
    ("smartphone", 220.0), ("headphones", 250.0), ("smartwatch", 62.0), ("keyboard", 810.0),
    ("tablet", 475.0), ("ssd", 85.0), ("camera", 690.0), ("earbuds", 55.0),
]


@dataclass
class SimConfig:
    """Generative model parameters. Defaults are the 'nominal' condition of the study."""

    seed: int = 2026
    cell_multiplier: int = 10            # journeys per cell = protocol quota x multiplier
    # Scales: (id, sigma_g, delta_g). Each checkpoint uses one scale drawn at random.
    scales: Tuple[Tuple[str, float, float], ...] = (
        ("SIM_SCALE_A", 0.5, 0.10), ("SIM_SCALE_B", 1.0, 0.20), ("SIM_SCALE_C", 2.0, 0.50),
    )
    sigma_multiplier: float = 1.0        # sweep: true noise = nominal sigma x multiplier
    humidity_sd_g: float = 0.6           # legitimate per-checkpoint mass drift of packaging
    # Nuisance probabilities per checkpoint (independent of cell)
    p_scale_fault: float = 0.03          # scale ERROR, photos fine
    p_dark: float = 0.03                 # underexposed photos, scale fine
    p_blur: float = 0.04                 # motion / focus blur
    p_unusable: float = 0.015            # scale ERROR and dark photos together
    p_glare_unflagged: float = 0.03      # glare present, operator did not flag it
    p_identifier_from_photo: float = 0.30
    p_misread_photo: float = 0.04        # one seal/serial character misread (photo source)
    p_misread_typed: float = 0.01        # misread when scanned / typed
    # Capture geometry
    pose_jitter_px: float = 8.0
    lighting_sd: float = 0.08
    sensor_noise_sd: float = 2.0
    # Tamper profile (S2/S3 tamper, degraded and doorstep cells)
    p_weight_matched: float = 0.25
    p_small_mass: float = 0.25           # 2-15 g; remainder 15-200 g
    seal_action_probs: Tuple[Tuple[str, float], ...] = (
        ("torn", 0.35), ("replaced", 0.35), ("cloned", 0.15), ("subtle", 0.15),
    )
    p_serial_changed: float = 0.5        # swapped item carries a different serial
    image_size: Tuple[int, int] = (640, 480)
    extra: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------- images

def _base_scene(side: str, seal_text: str, serial: str, rng: np.random.Generator) -> np.ndarray:
    """Canonical (un-posed) BGR image of one parcel face."""
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
        cv2.putText(img, f"SN {serial}", (165, 195), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1)
        bx = 170
        for bw in (3, 1, 4, 2, 5, 2, 3, 1, 4, 2, 3, 5, 2, 4, 1, 3, 2, 5, 3):
            cv2.rectangle(img, (bx, 250), (bx + bw, 320), (0, 0, 0), -1)
            bx += bw + 4
    else:  # SEAL close-up
        cv2.rectangle(img, (80, 120), (560, 360), (130, 170, 200), -1)
        cv2.rectangle(img, (120, 180), (520, 290), (210, 140, 0), -1)
        cv2.putText(img, seal_text[:22], (135, 245), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(img, SIM_WATERMARK, (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 180), 1)
    return img


def _surface_texture(shape: Tuple[int, int, int], seed: int) -> np.ndarray:
    """Fixed fine-grain texture of one parcel face (cardboard fibre, paper grain).

    Seeded per journey and face, so the same box shows the same texture at every checkpoint.
    """
    r = np.random.default_rng(seed)
    grain = r.normal(0.0, 9.0, size=shape[:2]).astype(np.float32)
    fibres = cv2.GaussianBlur(r.normal(0.0, 1.0, size=shape[:2]).astype(np.float32), (0, 0), sigmaX=6, sigmaY=0.8) * 30.0
    return (grain + fibres)[..., None]


def _apply_marks(img: np.ndarray, side: str, tamper_strength: float, dent_strength: float,
                 rng: np.random.Generator) -> np.ndarray:
    """Draw tamper and damage cues whose visibility scales with strength in [0, 1]."""
    out = img.copy()
    if tamper_strength > 0 and side in ("TOP", "SEAL"):
        overlay = out.copy()
        y0 = 240 if side == "TOP" else 235
        x0, x1 = (210, 430) if side == "TOP" else (120, 520)
        pts = np.array([[x, y0 + int(rng.integers(-14, 15))] for x in np.linspace(x0, x1, 6).astype(int)], np.int32)
        cv2.polylines(overlay, [pts], False, (40, 40, 200), 5)
        cv2.rectangle(overlay, (x0 + 30, y0 - 18), (x0 + 110, y0 + 18), (160, 190, 215), -1)  # re-tape patch
        out = cv2.addWeighted(overlay, float(tamper_strength), out, 1 - float(tamper_strength), 0)
    if dent_strength > 0 and side == "TOP":
        overlay = out.copy()
        poly = np.array([[110, 75], [175, 75], [150, 128], [110, 150]], np.int32)
        cv2.fillPoly(overlay, [poly], (65, 100, 130))
        cv2.line(overlay, (110, 150), (185, 105), (30, 50, 70), 2)
        out = cv2.addWeighted(overlay, float(dent_strength), out, 1 - float(dent_strength), 0)
    return out


def _capture(img: np.ndarray, cfg: SimConfig, rng: np.random.Generator, *, dark: bool, blur: bool,
             glare: bool) -> np.ndarray:
    """Simulate the act of photographing: pose, lighting, glare, blur, exposure, noise."""
    h, w = img.shape[:2]
    j = cfg.pose_jitter_px
    src = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
    dst = src + rng.normal(0.0, j, size=(4, 2)).astype(np.float32)
    out = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h),
                              borderMode=cv2.BORDER_REPLICATE)
    gain = float(np.clip(1.0 + rng.normal(0.0, cfg.lighting_sd), 0.80, 1.12))  # auto-exposure keeps highlights unclipped
    out = np.clip(out.astype(np.float32) * gain, 0, 255)
    if glare:
        mask = np.zeros((h, w), np.float32)
        cx, cy = int(w / 2 + rng.normal(0, 25)), int(h / 2 + rng.normal(0, 20))
        cv2.ellipse(mask, (cx, cy), (int(rng.uniform(90, 130)), int(rng.uniform(60, 90))), 0, 0, 360, 1.0, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), 12)[..., None]
        out = out * (1 - mask) + 255.0 * mask
    if blur:
        k = int(rng.choice([15, 19, 25]))
        kernel = np.zeros((k, k), np.float32)
        kernel[k // 2, :] = 1.0 / k
        out = cv2.filter2D(out, -1, kernel)
    if dark:
        out = out * float(rng.uniform(0.04, 0.10))
    out = out + rng.normal(0.0, cfg.sensor_noise_sd, size=out.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


# ----------------------------------------------------------------------------- helpers

def _misread(text: Optional[str], rng: random.Random) -> Optional[str]:
    if not text:
        return text
    i = rng.randrange(len(text))
    swaps = {"0": "O", "O": "0", "1": "I", "I": "1", "8": "B", "B": "8", "5": "S", "S": "5"}
    ch = swaps.get(text[i], "X" if text[i] != "X" else "Y")
    return text[:i] + ch + text[i + 1:]


def _weighted(rng: random.Random, options: Tuple[Tuple[str, float], ...]) -> str:
    names, probs = zip(*options)
    return rng.choices(names, weights=probs, k=1)[0]


def _stage_of(interval: str) -> int:
    return int(interval[1]) if interval.startswith("S") and interval[1:].isdigit() else 0


def _bounding(stage: int) -> List[int]:
    """Checkpoints that must be usable for the truth to be determinable (Algorithm 1 needs CP1)."""
    return [1, stage, stage + 1] if stage else [1, 4]


# ----------------------------------------------------------------------------- journeys

def _plan_journey(code: str, cell: str, cfg: SimConfig, rng: random.Random) -> Dict[str, Any]:
    """Draw the staged scenario and the nuisance effects for one journey."""
    interval = CELL_QUOTAS[cell]["target_interval"]
    stage = _stage_of(interval)
    plan: Dict[str, Any] = {
        "code": code, "cell": cell, "interval": interval, "stage": stage,
        "item": rng.choice(ITEMS), "seal_action": "none", "mass_change_g": 0.0,
        "tamper_strength": 0.0, "dent_strength": 0.0, "serial_changed": False,
        "glare_cps": [], "unusable_cps": [], "scale_fault_cps": [], "dark_cps": [], "blur_cps": [],
        "unflagged_glare_cps": [],
    }
    tampered = cell in ("customer_tamper", "reverse_transit_tamper", "degraded_evidence", "doorstep_substitution")
    if tampered:
        u = rng.random()
        if u < cfg.p_weight_matched:
            plan["mass_change_g"] = 0.0
        elif u < cfg.p_weight_matched + cfg.p_small_mass:
            plan["mass_change_g"] = round(rng.uniform(2.0, 15.0), 1)
        else:
            plan["mass_change_g"] = round(rng.uniform(15.0, 200.0), 1)
        plan["mass_change_g"] = min(plan["mass_change_g"], round(0.9 * plan["item"][1], 1))  # cannot remove more than the item
        plan["serial_changed"] = rng.random() < cfg.p_serial_changed
    if cell == "doorstep_substitution":
        plan["seal_action"] = "all_decoy"
        plan["tamper_strength"] = rng.uniform(0.0, 0.3)
    elif cell in ("customer_tamper", "reverse_transit_tamper", "degraded_evidence"):
        plan["seal_action"] = _weighted(rng, cfg.seal_action_probs)
        plan["tamper_strength"] = {
            "torn": rng.uniform(0.5, 1.0), "replaced": rng.uniform(0.1, 0.5),
            "cloned": rng.uniform(0.0, 0.2), "subtle": rng.uniform(0.1, 0.3),
        }[plan["seal_action"]]
    elif cell == "forward_transit_damage":
        plan["dent_strength"] = rng.uniform(0.2, 1.0)
        plan["mass_change_g"] = round(rng.uniform(0.0, 8.0), 1)
    elif cell == "ambiguous_evidence":
        plan["seal_action"] = "subtle"
        plan["tamper_strength"] = rng.uniform(0.1, 0.3)
        plan["glare_cps"] = [3, 4]
    elif cell == "permitted_flyer":
        plan["seal_action"] = "flyer_replaced_logged"

    if cell == "degraded_evidence":
        plan["unusable_cps"].append(rng.choice([2, 3]))

    # Nuisance effects, identical probabilities for every cell
    for k in (1, 2, 3, 4):
        if rng.random() < cfg.p_unusable and k not in plan["unusable_cps"]:
            plan["unusable_cps"].append(k)
        if rng.random() < cfg.p_scale_fault:
            plan["scale_fault_cps"].append(k)
        if rng.random() < cfg.p_dark:
            plan["dark_cps"].append(k)
        if rng.random() < cfg.p_blur:
            plan["blur_cps"].append(k)
        if rng.random() < cfg.p_glare_unflagged and k not in plan["glare_cps"]:
            plan["unflagged_glare_cps"].append(k)
    plan["identifier_source"] = {
        k: ("photo" if rng.random() < cfg.p_identifier_from_photo else rng.choice(["scanned", "typed"]))
        for k in (1, 2, 3, 4)
    }
    return plan


def _staging_row(plan: Dict[str, Any]) -> Dict[str, Any]:
    stage = plan["stage"]
    bounding_unusable = [k for k in _bounding(stage) if k in plan["unusable_cps"]]
    mass = plan["mass_change_g"]
    return {
        "journey_code": plan["code"],
        "assigned_cell": plan["cell"],
        "manipulation_interval": plan["interval"],
        "actual_manipulation": "none" if plan["interval"] == "none" else f"tamper_{plan['cell']}",
        "tare_adjusted": "yes" if plan["cell"] == "permitted_flyer" else "no",
        "degraded_checkpoint": f"cp{bounding_unusable[0]}" if bounding_unusable else "none",
        "degradation_type": "scale_error+dark" if bounding_unusable else "none",
        "glare_over_defect": "yes" if plan["glare_cps"] else "no",
        "staged_by": "SIMULATOR",
        "synthetic": "true",
        "seal_action": plan["seal_action"],
        "weight_matched": ("yes" if mass == 0 else "no") if plan["stage"] else "n/a",
        "mass_change_g": f"{mass:g}",
        "mass_band": ("0" if mass == 0 else ("<15" if mass < 15 else ">=15")) if plan["stage"] else "n/a",
        "serial_changed": "yes" if plan["serial_changed"] else "no",
        "nuisance_unusable_cps": ";".join(str(k) for k in plan["unusable_cps"] if k not in bounding_unusable),
        "nuisance_scale_fault_cps": ";".join(map(str, plan["scale_fault_cps"])),
        "nuisance_dark_cps": ";".join(map(str, plan["dark_cps"])),
        "nuisance_blur_cps": ";".join(map(str, plan["blur_cps"])),
        "nuisance_unflagged_glare_cps": ";".join(map(str, plan["unflagged_glare_cps"])),
        "nuisance_misread_cps": "",  # filled while the checkpoints are generated
    }


def _seals_for(plan: Dict[str, Any], k: int, ids: Dict[str, str]) -> Tuple[List[SealObservation], str]:
    """Layered seal observations at checkpoint k and any carrier note."""
    cell, stage, action = plan["cell"], plan["stage"], plan["seal_action"]
    tampered_here = stage > 0 and k > stage and cell not in ("forward_transit_damage",)
    note = ""

    def inner(state_l2: str = "INTACT", id_l2: Optional[str] = None, state_l3: str = "INTACT", id_l3: Optional[str] = None):
        return [
            SealObservation(layer="L2_BOX", seal_id_read=id_l2 if id_l2 is not None else ids["L2"], state=state_l2),
            SealObservation(layer="L3_ITEM", seal_id_read=id_l3 if id_l3 is not None else ids["L3"], state=state_l3),
        ]

    if cell == "doorstep_substitution" and k >= 2:
        layers = inner(id_l2=ids["L2_DECOY"], id_l3=ids["L3_DECOY"])
    elif tampered_here and action == "torn":
        layers = inner(state_l2="TORN", state_l3="MISSING", id_l3="")
    elif tampered_here and action == "replaced":
        layers = inner(id_l2=ids["L2_REPL"], id_l3=ids["L3_REPL"])
    elif tampered_here and action == "subtle":
        layers = inner(state_l2="UNREADABLE", id_l2="")
    else:  # none, cloned (attacker reproduced the IDs), or before the tamper
        layers = inner()

    if k <= 2:
        fwd_id = ids["L1_FWD"]
        if cell == "doorstep_substitution" and k == 2:
            fwd_id = ids["L1_DECOY"]
        if cell == "permitted_flyer" and k == 2:
            fwd_id = ids["L1_NEW"]
            note = f"flyer replaced at hub, new seal {fwd_id}"
        layers = [SealObservation(layer="L1_FWD", seal_id_read=fwd_id, state="INTACT")] + layers
    if k >= 3:
        ret_state, ret_id = "INTACT", ids["L1_RET"]
        if tampered_here and stage == 3 and action == "torn":
            ret_state = "TORN"
        elif tampered_here and stage == 3 and action == "replaced":
            ret_id = ids["L1_RET_REPL"]
        layers = [SealObservation(layer="L1_RET", seal_id_read=ret_id, state=ret_state)] + layers
    for s in layers:
        if s.seal_id_read == "":
            s.seal_id_read = None
    return layers, note


def simulate_benchmark(output_dir: Path | str, cfg: Optional[SimConfig] = None) -> Dict[str, Any]:
    """Generate a simulated benchmark: store.db, staging_log.csv, split_manifest.json, scales.json."""
    cfg = cfg or SimConfig()
    out = Path(output_dir).resolve()
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(cfg.seed)
    np_rng = np.random.default_rng(cfg.seed)

    cells: List[str] = []
    for cell, info in CELL_QUOTAS.items():
        cells += [cell] * (info["count"] * cfg.cell_multiplier)
    rng.shuffle(cells)

    db_path = out / "store.db"
    if db_path.exists():
        db_path.unlink()
    store = Store(db_path)
    scale_table = {sid: (sig, dlt) for sid, sig, dlt in cfg.scales}
    t0 = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    staging_rows: List[Dict[str, Any]] = []

    for idx, cell in enumerate(cells, start=1):
        code = f"SIM-{cfg.seed}-{idx:05d}"
        plan = _plan_journey(code, cell, cfg, rng)
        row = _staging_row(plan)
        staging_rows.append(row)
        tag = hashlib.sha1(code.encode()).hexdigest()[:6].upper()
        ids = {
            "L1_FWD": f"F{tag}1", "L1_NEW": f"F{tag}9", "L1_DECOY": f"D{tag}1", "L1_RET": f"R{tag}1",
            "L1_RET_REPL": f"R{tag}7", "L2": f"B{tag}2", "L2_REPL": f"B{tag}8", "L2_DECOY": f"D{tag}2",
            "L3": f"T{tag}3", "L3_REPL": f"T{tag}6", "L3_DECOY": f"D{tag}3",
        }
        serial = f"SN{tag}{idx % 97:02d}"
        swapped_serial = f"SN{tag[::-1]}{(idx + 13) % 97:02d}"
        imei = f"35{int(tag, 16) % 10**13:013d}"
        mass0 = plan["item"][1] + 75.0
        stage = plan["stage"]
        cps: List[CheckpointObservation] = []

        for k in (1, 2, 3, 4):
            after_tamper = stage > 0 and k > stage
            true_mass = mass0 - (plan["mass_change_g"] if after_tamper else 0.0) + np_rng.normal(0.0, cfg.humidity_sd_g)
            scale_id = rng.choice(list(scale_table))
            sigma, delta = scale_table[scale_id]
            unusable = k in plan["unusable_cps"]
            scale_fault = unusable or k in plan["scale_fault_cps"]
            if scale_fault:
                readings, status = [], "ERROR"
            else:
                bias = np_rng.uniform(-delta, delta)
                noise = np_rng.normal(0.0, sigma * cfg.sigma_multiplier, size=3)
                readings, status = [round(float(true_mass + bias + n), 2) for n in noise], "OK"

            seals, note = _seals_for(plan, k, ids)
            obs_serial = swapped_serial if (after_tamper and plan["serial_changed"] and plan["cell"] != "forward_transit_damage") else serial
            src = plan["identifier_source"][k]
            p_mis = cfg.p_misread_photo if src == "photo" else cfg.p_misread_typed
            if k > 1 and rng.random() < p_mis:  # a misread at a later checkpoint creates a false mismatch
                row["nuisance_misread_cps"] = ";".join(filter(None, [row["nuisance_misread_cps"], str(k)]))
                if rng.random() < 0.5 and seals:
                    s = rng.choice([s for s in seals if s.seal_id_read] or seals)
                    s.seal_id_read = _misread(s.seal_id_read, rng)
                else:
                    obs_serial = _misread(obs_serial, rng)
            flagged_glare = k in plan["glare_cps"]
            glare = flagged_glare or k in plan["unflagged_glare_cps"]
            dark = unusable or k in plan["dark_cps"]
            blur = k in plan["blur_cps"]
            seal_text = next((s.seal_id_read or "" for s in seals if s.layer == "L2_BOX"), "")

            images: List[ImageRef] = []
            for side in ("TOP", "LABEL", "SEAL"):
                base = _base_scene(side, seal_text if side != "LABEL" else "", obs_serial or "", np_rng)
                tex_seed = int(hashlib.sha1(f"{code}:{side}".encode()).hexdigest()[:8], 16)
                base = np.clip(base.astype(np.float32) + _surface_texture(base.shape, tex_seed), 0, 255).astype(np.uint8)
                marked = _apply_marks(base, side, plan["tamper_strength"] if after_tamper else 0.0,
                                      plan["dent_strength"] if after_tamper else 0.0, np_rng)
                shot = _capture(marked, cfg, np_rng, dark=dark, blur=blur, glare=glare)
                path = img_dir / f"{code}_CP{k}_{side}.jpg"
                cv2.imwrite(str(path), shot, [cv2.IMWRITE_JPEG_QUALITY, int(rng.uniform(72, 92))])
                images.append(ImageRef(side=side, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                       w=cfg.image_size[0], h=cfg.image_size[1]))

            cps.append(CheckpointObservation(
                journey_code=code, cp_index=k, ts_utc=t0 + timedelta(days=idx // 40, hours=3 * k),
                device_id=f"SIM_DEV_{k}", operator_id=f"SIM_OP_{rng.randint(1, 6)}",
                weights_g=readings, scale_id=scale_id, scale_status=status,
                seal_qr=ids["L2"], serial=obs_serial, imei=imei, carrier_log=note,
                identifier_source=src, glare_reported=flagged_glare,
                permitted_packaging_change=(plan["cell"] == "permitted_flyer" and k == 2), tare_delta_g=0.0,
                images=images, seals=seals,
            ))
        journey = Journey(journey_code=code, checkpoints=cps,
                          metadata={"synthetic": True, "simulated": True, "assigned_cell": cell})
        store.insert_journey(journey)
        for cp in cps:
            store.insert_checkpoint(cp)

    # Stratified calibration / test split
    rng_split = random.Random(cfg.seed + 1)
    by_cell: Dict[str, List[str]] = {}
    for r in staging_rows:
        by_cell.setdefault(r["assigned_cell"], []).append(r["journey_code"])
    cal, test = [], []
    for cell, codes in by_cell.items():
        rng_split.shuffle(codes)
        n_cal = max(1, round(len(codes) * CALIBRATION_FRACTION))
        cal += codes[:n_cal]
        test += codes[n_cal:]

    fields = list(staging_rows[0].keys())
    with open(out / "staging_log.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        wr.writerows(staging_rows)
    manifest = {
        "synthetic": True, "simulated": True, "disclaimer": "SIMULATION STUDY — NOT PHYSICAL DATA",
        "calibration_journey_codes": sorted(cal), "test_journey_codes": sorted(test),
        "split_mapping": {**{c: "calibration" for c in cal}, **{c: "test" for c in test}},
    }
    (out / "split_manifest.json").write_text(json.dumps(manifest, indent=1))
    scales = {"synthetic": True, "scales": {sid: {"scale_id": sid, "sigma_g": sig, "delta_g": dlt}
                                            for sid, sig, dlt in cfg.scales}}
    (out / "scales.json").write_text(json.dumps(scales, indent=1))
    (out / "sim_config.json").write_text(json.dumps(asdict(cfg), indent=1))
    truths = [derive_ground_truth(r)[0] for r in staging_rows]
    return {"output_dir": str(out), "n": len(staging_rows), "calibration": len(cal), "test": len(test),
            "omega_counts": {o: truths.count(o) for o in sorted(set(truths))}}
