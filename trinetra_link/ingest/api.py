from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import hmac
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Path as FPath, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from PIL import Image
import io

from trinetra_link import __version__
from trinetra_link.config import ARTIFACTS_DIR
from trinetra_link.quality.gate import QualityGate
from trinetra_link.quality.features import compute_image_quality_features, evaluate_scale_readings, resolution_score, score_photo
from trinetra_link.reconcile.fuse import fuse_checkpoint_observations
from trinetra_link.schema.models import CheckpointObservation, ImageRef, Journey, SealObservation
from trinetra_link.store.database import Store
from trinetra_link.ingest.export import export_journey_folder
from trinetra_link.integrity.chain import genesis_hash, seal_checkpoint

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_STORAGE_DIR = ARTIFACTS_DIR / "images"
IMAGES_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Example token for local tests only. The service never falls back to it: DEVICE_INGEST_TOKEN must be set.
DEFAULT_DEV_TOKEN = "trinetra-dev-capture-token"


def get_expected_token() -> Optional[str]:
    token = os.getenv("DEVICE_INGEST_TOKEN", "").strip()
    return token or None


def verify_device_token(
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
) -> str:
    expected = get_expected_token()
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Capture is disabled: set DEVICE_INGEST_TOKEN on the server before accepting observations",
        )
    provided = x_device_token
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing or invalid device capture token",
        )
    return provided


app = FastAPI(
    title="TriNetra-Link Ingest API",
    description="Multimodal Physical Observation Ingest & Evidence Capture Service",
    version=__version__,
)

# The capture page is served by this app (same origin), so no cross-origin access is needed by default.
# Extra origins, e.g. a separate capture front end, are listed in TRINETRA_CORS_ORIGINS (comma-separated).
_cors_origins = [o.strip() for o in os.getenv("TRINETRA_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Device-Token"],
    )

# Shared store instance (configurable via env)
def get_store() -> Store:
    db_path = os.getenv("TRINETRA_DB_PATH")
    return Store(db_path)


class JourneyCreateRequest(BaseModel):
    journey_code: str
    metadata: Optional[Dict[str, Any]] = None


@app.get("/health", tags=["System"])
def health_check() -> Dict[str, str]:
    """Service health probe."""
    return {"status": "ok", "version": __version__}


@app.get("/", tags=["UI"])
def serve_capture_ui() -> FileResponse:
    """Serve the mobile-optimized capture client."""
    capture_html = STATIC_DIR / "capture.html"
    if not capture_html.exists():
        raise HTTPException(status_code=404, detail="capture.html UI not yet compiled")
    return FileResponse(str(capture_html))


class ReadingsCheckRequest(BaseModel):
    weights_g: List[float] = []
    scale_status: str = "OK"
    scale_id: Optional[str] = None


@app.post("/quality/photo", tags=["Capture checks"])
async def check_photo_quality(
    file: UploadFile = File(...),
    side: str = Form(""),
    _token: str = Depends(verify_device_token),
) -> Dict[str, Any]:
    """Score one photo with the quality gate's own rules before it is submitted, so the operator can retake it."""
    contents = await file.read()
    try:
        arr = cv2.cvtColor(np.array(Image.open(io.BytesIO(contents)).convert("RGB")), cv2.COLOR_RGB2BGR)
    except Exception:
        raise HTTPException(status_code=400, detail="The file is not a readable image")
    img_cfg = QualityGate().config.get("image", {})
    h, w = arr.shape[:2]
    feats = compute_image_quality_features(arr)
    scored = score_photo(feats, resolution_score(w, h, img_cfg), img_cfg, side=side)
    theta = QualityGate().theta
    # Advisory only (does not change the score): a concentrated reflection, found with the same glare
    # detector the photo comparison uses, can hide a seal or damage even when it covers little of the photo.
    tips: List[Dict[str, str]] = []
    hsv = cv2.cvtColor(cv2.resize(arr, (320, 240), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
    spots = (((hsv[:, :, 2] > 240) & (hsv[:, :, 1] < 30)) * 255).astype(np.uint8)
    spots = cv2.morphologyEx(spots, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(spots)
    if any(stats[i, cv2.CC_STAT_AREA] >= 300 for i in range(1, n)):
        tips.append({"code": "glare_spot", "message": "Bright reflection spot visible",
                     "fix": "If it covers the seal or any damage, tilt the phone and retake, or set 'Glare over a seal' to Yes."})
    return {
        "side": side, "ok": scored["score"] >= theta, "score": round(scored["score"], 3), "theta": theta,
        "issues": scored["issues"], "tips": tips, "width": w, "height": h,
        "luminance": round(scored["luminance"], 1), "sharpness": round(scored["laplacian_variance"], 3),
        "glare_fraction": round(scored["specular_fraction"], 3),
    }


@app.post("/quality/readings", tags=["Capture checks"])
def check_readings_quality(
    payload: ReadingsCheckRequest,
    _token: str = Depends(verify_device_token),
) -> Dict[str, Any]:
    """Check the three weighings with the quality gate's own scale rule before they are submitted."""
    gate = QualityGate()
    scale_cfg = gate.config.get("scale", {})
    sigma = None
    if payload.scale_id and "scales" in scale_cfg:
        sigma = scale_cfg["scales"].get(payload.scale_id, {}).get("sigma_g")
    sigma = sigma if sigma is not None else scale_cfg.get("sigma_g", 1.0)
    score, _reasons = evaluate_scale_readings(
        weights_g=payload.weights_g, scale_status=payload.scale_status,
        min_readings=scale_cfg.get("min_readings", 3), min_weight_g=scale_cfg.get("min_weight_g", 1.0),
        max_spread_g=scale_cfg.get("max_spread_g"), scale_sigma=sigma,
        allowed_statuses=scale_cfg.get("allowed_statuses", ["OK", "MANUAL", "SETTLED"]),
    )
    issues: List[Dict[str, str]] = []
    status_ok = payload.scale_status.upper() in [s.upper() for s in scale_cfg.get("allowed_statuses", ["OK", "MANUAL", "SETTLED"])]
    if not status_ok:
        issues.append({"code": "status", "message": f"Scale status is {payload.scale_status}",
                       "fix": "This checkpoint's weight will not be used. If the scale works, set it to OK and weigh again."})
    elif len(payload.weights_g) < scale_cfg.get("min_readings", 3):
        issues.append({"code": "count", "message": "Fewer than three readings",
                       "fix": "Lift the parcel off and weigh it again until you have three readings."})
    elif payload.weights_g and min(payload.weights_g) < scale_cfg.get("min_weight_g", 1.0):
        issues.append({"code": "zero", "message": "A reading is zero or almost zero", "fix": "Check the scale is tared and weigh again."})
    elif score < 1.0:
        spread = max(payload.weights_g) - min(payload.weights_g)
        issues.append({"code": "spread", "message": f"Readings differ by {spread:.1f} g, more than the {4 * sigma:.1f} g a steady scale allows",
                       "fix": "Put the scale on a flat, still surface and weigh again."})
    return {"ok": score >= gate.theta, "score": round(score, 3), "theta": gate.theta, "issues": issues,
            "spread_limit_g": round(4 * sigma, 2)}


@app.post("/journeys", status_code=status.HTTP_201_CREATED, tags=["Journeys"])
def create_journey(
    payload: JourneyCreateRequest,
    response: Response,
    store: Store = Depends(get_store),
    _token: str = Depends(verify_device_token),
) -> Dict[str, Any]:
    """Register a new physical journey container idempotently."""
    code = payload.journey_code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="journey_code cannot be empty")

    existing = store.get_journey(code)
    if existing:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "exists",
            "message": f"Journey {code} already registered",
            "journey": existing.model_dump(mode="json"),
        }

    journey = Journey(
        journey_code=code,
        status="ACTIVE",
        metadata=payload.metadata or {},
    )
    store.insert_journey(journey)
    return {
        "status": "created",
        "journey": journey.model_dump(mode="json"),
    }


@app.post("/journeys/{code}/checkpoints/{k}", status_code=status.HTTP_201_CREATED, tags=["Checkpoints"])
async def ingest_checkpoint(
    code: str = FPath(..., description="Journey code"),
    k: int = FPath(..., ge=1, le=10, description="Checkpoint sequence index (1..K)"),
    data: str = Form(..., description="JSON string of CheckpointObservation metadata"),
    files: List[UploadFile] = File(..., description="Photographic evidence assets"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    store: Store = Depends(get_store),
    _token: str = Depends(verify_device_token),
) -> Dict[str, Any]:
    """
    Ingest multipart checkpoint observation:
        - Validates checkpoint sequence order
        - Computes and verifies server-side SHA-256 for all images
        - Evaluates quality gate (q_k)
        - Executes multimodal baseline reconciliation against CP1 (for k > 1)
        - Persists append-only records to store
    """
    code = code.strip()
    journey = store.get_journey(code)
    if not journey:
        # Auto-create active journey container if not explicitly pre-registered
        journey = Journey(journey_code=code, status="ACTIVE")
        store.insert_journey(journey)

    # Sequence continuity check
    existing_cps = {cp.cp_index: cp for cp in store.list_checkpoints(code)}
    if k in existing_cps:
        raise HTTPException(status_code=400, detail=f"Checkpoint CP{k} has already been recorded for {code} (append-only)")
    if k > 1 and (k - 1) not in existing_cps:
        raise HTTPException(
            status_code=400,
            detail=f"Sequence violation: CP{k - 1} must be recorded before CP{k}",
        )

    # Parse metadata JSON
    try:
        meta_dict = json.loads(data)
    except json.JSONDecodeError as err:
        raise HTTPException(status_code=400, detail=f"Malformed metadata JSON in 'data' form field: {err}")

    # Process and verify image files
    if not files:
        raise HTTPException(status_code=400, detail="At least one photographic evidence file is required")

    client_hashes = meta_dict.get("client_hashes", {})
    photo_meta = meta_dict.get("photo_meta") or {}
    received_at = datetime.now(timezone.utc)
    image_refs: List[ImageRef] = []
    image_arrays: Dict[str, np.ndarray] = {}

    target_dir = IMAGES_STORAGE_DIR / code
    target_dir.mkdir(parents=True, exist_ok=True)

    for idx, upload in enumerate(files):
        contents = await upload.read()
        if not contents:
            raise HTTPException(status_code=400, detail=f"Uploaded file '{upload.filename}' is empty")

        server_sha256 = hashlib.sha256(contents).hexdigest()

        # Side name resolution (front, top, seal, back, etc.)
        filename = upload.filename or f"image_{idx}.jpg"
        side_candidate = filename.split(".")[0].split("_")[-1].lower()
        allowed_sides = ["front", "top", "seal", "back", "left", "right"]
        side = side_candidate if side_candidate in allowed_sides else (meta_dict.get("side") or f"side_{idx}")

        # Check client provided hash if present
        expected_client_hash = client_hashes.get(upload.filename) or client_hashes.get(side)
        if expected_client_hash and expected_client_hash.lower() != server_sha256.lower():
            raise HTTPException(
                status_code=400,
                detail=f"Hash mismatch for '{upload.filename}': client={expected_client_hash}, server={server_sha256}",
            )

        # Decode image to inspect dimensions
        try:
            pil_img = Image.open(io.BytesIO(contents))
            w, h = pil_img.size
            # Convert to BGR array for CV quality checks
            cv_arr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            image_arrays[side] = cv_arr
        except Exception:
            w, h = 640, 480

        # Save to storage path
        storage_filename = f"cp{k}_{side}_{server_sha256[:8]}.jpg"
        storage_path = target_dir / storage_filename
        with open(storage_path, "wb") as f:
            f.write(contents)

        pm = photo_meta.get(upload.filename) or photo_meta.get(side) or {}

        def _num(key: str) -> Optional[float]:
            try:
                return float(pm[key]) if pm.get(key) is not None else None
            except (TypeError, ValueError):
                return None

        lat, lon = _num("lat"), _num("lon")
        if lat is not None and not (-90 <= lat <= 90) or lon is not None and not (-180 <= lon <= 180):
            raise HTTPException(status_code=400, detail=f"Location for '{upload.filename}' is out of range")
        image_refs.append(
            ImageRef(
                side=side,
                path=str(storage_path),
                sha256=server_sha256,
                w=w,
                h=h,
                exposure=meta_dict.get("exposure"),
                captured_at=str(pm["captured_at"]) if pm.get("captured_at") else None,
                lat=lat,
                lon=lon,
                geo_accuracy_m=_num("accuracy_m"),
            )
        )

    # Build CheckpointObservation
    weights_g = meta_dict.get("weights_g", [])
    scale_failed = str(meta_dict.get("scale_status", "OK")).upper() in ("ERROR", "UNSTABLE")
    if not isinstance(weights_g, list) or (len(weights_g) < 1 and not scale_failed):
        raise HTTPException(
            status_code=400,
            detail="weights_g must hold the readings taken (3 per the capture SOP); it may be empty only when the scale reported ERROR or UNSTABLE",
        )

    ts_str = meta_dict.get("ts_utc")
    ts_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.now(timezone.utc)

    obs = CheckpointObservation(
        journey_code=code,
        cp_index=k,
        ts_utc=ts_utc,
        device_id=meta_dict.get("device_id", "MOBILE-CAPTURE-01"),
        operator_id=meta_dict.get("operator_id", "OPERATOR-DEFAULT"),
        weights_g=[float(w) for w in weights_g],
        scale_id=meta_dict.get("scale_id", "SCALE-MANUAL"),
        scale_status=meta_dict.get("scale_status", "OK"),
        calibration_date=meta_dict.get("calibration_date"),
        images=image_refs,
        seal_qr=meta_dict.get("seal_qr"),
        serial=meta_dict.get("serial"),
        imei=meta_dict.get("imei"),
        carrier_log=meta_dict.get("carrier_log"),
        identifier_source=meta_dict.get("identifier_source"),
        glare_reported=meta_dict.get("glare_reported"),
        seals=[SealObservation(**seal) for seal in (meta_dict.get("seals") or [])],
        permitted_packaging_change=bool(meta_dict.get("permitted_packaging_change", False)),
        tare_delta_g=float(meta_dict.get("tare_delta_g", 0.0)),
        app_version=meta_dict.get("app_version", __version__),
        received_at_utc=received_at,
    )

    # Warn (do not reject) when a photo is byte-identical to one already recorded for this journey
    earlier = {im.sha256: f"CP{c.cp_index} {im.side.upper()}" for c in existing_cps.values() for im in c.images}
    reused_photo_warnings = [f"{im.side.upper()} is the same photo file as {earlier[im.sha256]}; take a new photo at this checkpoint."
                             for im in obs.images if im.sha256 in earlier]

    # Seal the record into the journey's evidence chain, linked to the previous checkpoint
    if k == 1:
        prev_hash = genesis_hash(code)
    else:
        prev_hash = existing_cps[k - 1].record_hash if (k - 1) in existing_cps else None
    obs = seal_checkpoint(obs, prev_hash)

    # Persist checkpoint to store
    store.insert_checkpoint(obs)

    # Quality Gate Evaluation
    prev_obs = existing_cps.get(k - 1)
    gate = QualityGate()
    quality_report = gate.evaluate(
        observation=obs,
        previous_observation=prev_obs,
        image_arrays=image_arrays,
    )
    store.insert_quality_report(quality_report)

    # Multimodal reconciliation vs CP1 (if k > 1)
    reconcile_res = None
    if k > 1 and 1 in existing_cps:
        cp1 = existing_cps[1]
        reconcile_res = fuse_checkpoint_observations(
            obs_baseline=cp1,
            obs_current=obs,
            quality_report=quality_report,
            image_arrays_current=image_arrays,
        )
        store.insert_reconcile_result(reconcile_res)

    # Mirror the journey into Real_Inputs/<code>/ (readable photos, journey.json, readings.csv)
    try:
        saved_folder = str(export_journey_folder(store, code))
    except Exception as exc:  # the store remains the record of truth; never fail the upload over the mirror
        saved_folder = f"not exported: {exc}"

    return {
        "saved_folder": saved_folder,
        "record_hash": obs.record_hash,
        "warnings": reused_photo_warnings,
        "status": "success",
        "journey_code": code,
        "cp_index": k,
        "checkpoint": obs.model_dump(mode="json"),
        "quality_report": quality_report.model_dump(mode="json"),
        "reconcile_result": reconcile_res.model_dump(mode="json") if reconcile_res else None,
    }


@app.get("/journeys/{code}/reference/{side}", tags=["Capture checks"])
def get_reference_photo(
    code: str = FPath(..., description="Journey code"),
    side: str = FPath(..., description="Photo side, e.g. front, top, back, seal"),
    store: Store = Depends(get_store),
    _token: str = Depends(verify_device_token),
) -> Response:
    """CP1 photo of one side, used as a framing guide so later checkpoints photograph the box the same way."""
    cps = {cp.cp_index: cp for cp in store.list_checkpoints(code.strip())}
    cp1 = cps.get(1)
    if cp1 is None:
        raise HTTPException(status_code=404, detail="CP1 has not been recorded for this journey yet")
    im = next((i for i in cp1.images if i.side.lower() == side.lower()), None)
    if im is None or not Path(im.path).exists():
        raise HTTPException(status_code=404, detail=f"CP1 has no {side} photo")
    pil = Image.open(im.path).convert("RGB")
    pil.thumbnail((1280, 1280))
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=80)
    return Response(buf.getvalue(), media_type="image/jpeg")


@app.get("/journeys/{code}", tags=["Journeys"])
def get_journey_timeline(
    code: str = FPath(..., description="Journey code"),
    store: Store = Depends(get_store),
    _token: str = Depends(verify_device_token),
) -> Dict[str, Any]:
    """Retrieve full physical observation timeline for a journey."""
    journey = store.get_journey(code.strip())
    if not journey:
        raise HTTPException(status_code=404, detail=f"Journey '{code}' not found")

    return {
        "journey": journey.model_dump(mode="json"),
        "checkpoints_count": len(journey.checkpoints),
    }
