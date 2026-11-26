"""TriNetra-Link Console: open a journey folder, run the pipeline, see where the parcel changed.

Reads journey folders in the TriNetra_Demo_Inputs / Real_Inputs layout (journey.json, images/, scales.json,
optional expected_output.json) and runs the pipeline with the parameters fitted in the simulation study.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from trinetra_link.attribution.policy import map_attribution_to_decision
from trinetra_link.config import REPO_ROOT
from trinetra_link.eval.pipeline import predict_trinetra_link
from trinetra_link.ingest.export import real_inputs_dir
from trinetra_link.integrity.chain import verify_chain
from trinetra_link.integrity.stamp import format_place, format_time, provenance_checks, render_stamped, stamp_lines
from trinetra_link.quality.gate import QualityGate
from trinetra_link.reconcile.visual import reconcile_visual
from trinetra_link.reconcile.weight import reconcile_weights
from trinetra_link.schema.models import CheckpointObservation, Journey

STATIC_DIR = Path(__file__).resolve().parent / "static"
THETA, GAMMA, Z = 0.70, 0.06, 3.0

VERDICTS = {
    "ATTR_CONFIRMED_LEGITIMATE": dict(kind="clear", stamp="CLEARED", title="Nothing changed",
                                      lead="The parcel matched its dispatch record at every checkpoint.", stage=None),
    "ATTR_STAGE_FORWARD_TRANSIT": dict(kind="fault", stamp="STAGE S1", title="Changed during delivery",
                                       lead="Intact at dispatch, different when it reached the customer.", stage=1),
    "ATTR_STAGE_CONSUMER_CUSTODY": dict(kind="fault", stamp="STAGE S2", title="Changed while with the customer",
                                        lead="Intact on delivery, different at the return pickup.", stage=2),
    "ATTR_STAGE_REVERSE_TRANSIT": dict(kind="fault", stamp="STAGE S3", title="Changed on the way back",
                                       lead="Intact at the return pickup, different at the warehouse.", stage=3),
    "ATTR_ABSTAIN_DEGRADED": dict(kind="abstain", stamp="NO CALL", title="Not enough evidence to decide",
                                  lead="A checkpoint the decision depends on could not be trusted.", stage=None),
    "ATTR_ABSTAIN_INDISTINGUISHABLE": dict(kind="abstain", stamp="NO CALL", title="The stages can't be told apart",
                                           lead="The evidence is readable but cannot separate the candidate stages.",
                                           stage=None),
}
BREACH = {"none": None, "L1_only": "Outer flyer opened", "box_entered": "Box entered",
          "full_substitution": "Every seal replaced"}
CP_PLACES = {1: "Seller dispatch", 2: "Delivered", 3: "Return pickup", 4: "Warehouse"}
STAGES = {1: "Delivery courier", 2: "Customer", 3: "Return courier"}


def _sources() -> Dict[str, Path]:
    return {"demo": REPO_ROOT / "TriNetra_Demo_Inputs", "real": real_inputs_dir()}


def _folder(jid: str) -> Path:
    group, _, name = jid.partition(":")
    base = _sources().get(group)
    if base is None or not name or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=404, detail="Unknown journey")
    folder = (base / name).resolve()
    if folder.parent != base.resolve() or not (folder / "journey.json").exists():
        raise HTTPException(status_code=404, detail="Journey folder not found")
    return folder


def _load(folder: Path) -> tuple[Dict[str, Any], Journey]:
    meta = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
    cps = []
    for c in meta["checkpoints"]:
        c = {k: v for k, v in c.items() if k in CheckpointObservation.model_fields}
        c["images"] = [{**im, "path": str((folder / im["path"]).resolve())} for im in c.get("images", [])]
        cps.append(CheckpointObservation(**c))
    return meta, Journey(journey_code=meta["journey_code"], checkpoints=cps)


def list_journeys() -> List[Dict[str, Any]]:
    out = []
    for group, base in _sources().items():
        if not base.exists():
            continue
        for folder in sorted(p for p in base.iterdir() if (p / "journey.json").exists()):
            try:
                meta = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            exp = folder / "expected_output.json"
            expected = json.loads(exp.read_text(encoding="utf-8")).get("label") if exp.exists() else None
            out.append({
                "id": f"{group}:{folder.name}", "group": group, "folder": folder.name,
                "code": meta.get("journey_code", folder.name), "product": meta.get("product") or "",
                "checkpoints": len(meta.get("checkpoints", [])), "simulated": "SIMULATED" in meta,
                "expected": expected,
            })
    return out


def analyze(jid: str) -> Dict[str, Any]:
    folder = _folder(jid)
    meta, journey = _load(folder)
    scales_path = folder / "scales.json"
    scales_cfg = json.loads(scales_path.read_text(encoding="utf-8")) if scales_path.exists() else {"scales": {}}
    attr = predict_trinetra_link(journey, mode="algorithm1", theta=THETA, z_weight=Z, visual_threshold=GAMMA,
                                 visual_method="local", scales_config=scales_cfg,
                                 scales_path=scales_path if scales_path.exists() else None)
    gate = QualityGate(config={"scale": {"scales": scales_cfg.get("scales", {}), "sigma_g": 1.0}}, theta=THETA)
    ev = attr.per_modality_evidence or {}
    q_k = {int(k): float(v) for k, v in (ev.get("q_k") or {}).items()}
    z_k = {int(k): v for k, v in (ev.get("z_k") or {}).items()}
    mods = {int(k): v for k, v in (ev.get("modality_evidence") or {}).items()}
    cps = {c.cp_index: c for c in journey.checkpoints}
    cp1 = cps.get(1)
    rel = {c["cp_index"]: c for c in meta["checkpoints"]}

    checkpoints = []
    for k in sorted(cps):
        c = cps[k]
        qr = gate.evaluate(c, previous_observation=cps.get(k - 1))
        q = q_k.get(k, qr.q_k)
        median = sorted(c.weights_g)[len(c.weights_g) // 2] if c.weights_g else None
        weight_test = None
        visual = {}
        if k > 1 and cp1 is not None:
            anom, delta, bound = reconcile_weights(cp1, c, z=Z, scales_file_path=scales_path if scales_path.exists() else None)
            if anom != "UNKNOWN":
                weight_test = {"delta_g": delta, "bound_g": bound, "changed": bool(anom)}
            if cp1.images and c.images:
                _, visual = reconcile_visual(cp1, c, visual_threshold=GAMMA, method="local")
        evidence = {}
        for key, (obs, _q) in (mods.get(k) or {}).items():
            if key in ("weight", "seal", "photo"):
                evidence[key] = obs
        photos = []
        sides1 = {im.side: im for im in (cp1.images if cp1 else [])}
        for im_meta, im in zip(rel[k].get("images", []), c.images):
            ref_rel = next((i["path"] for i in rel[1]["images"] if i["side"] == im.side), None) if k > 1 and im.side in sides1 else None
            photos.append({
                "side": im.side, "url": f"/api/image/{jid}/{im_meta['path']}",
                "stamped_url": f"/api/image/{jid}/{im_meta['path']}?stamped=1",
                "ref_url": f"/api/image/{jid}/{ref_rel}" if ref_rel else None,
                "ref_stamped_url": f"/api/image/{jid}/{ref_rel}?stamped=1" if ref_rel else None,
                "change": visual.get(im.side),
                "captured_at": im.captured_at, "time_text": format_time(im.captured_at),
                "lat": im.lat, "lon": im.lon, "accuracy_m": im.geo_accuracy_m, "place_text": format_place(im),
            })
        checkpoints.append({
            "k": k, "place": CP_PLACES.get(k, f"CP{k}"), "name": rel[k].get("checkpoint_name", f"CP{k}"),
            "time": c.ts_utc.isoformat(), "weights": c.weights_g, "median": median,
            "scale_id": c.scale_id, "scale_status": c.scale_status,
            "q": round(q, 2), "trusted": q >= THETA, "state": "REFERENCE" if k == 1 else z_k.get(k, "UNK"),
            "evidence": evidence, "weight_test": weight_test, "photos": photos,
            "quality_notes": qr.reasons,
            "seals": [s.model_dump() for s in c.seals], "seal_qr": c.seal_qr, "serial": c.serial, "imei": c.imei,
            "glare_reported": bool(c.glare_reported), "note": rel[k].get("operator_note") or c.carrier_log or "",
            "received_at": c.received_at_utc.isoformat() if c.received_at_utc else None,
        })

    integrity = verify_chain(journey.checkpoints)
    by_k = {r["k"]: r for r in integrity["records"]}
    for c in checkpoints:
        rec = by_k.get(c["k"], {})
        c["record_hash"] = rec.get("record_hash")
        c["integrity_issues"] = rec.get("issues", [])

    v = VERDICTS.get(attr.label, dict(kind="abstain", stamp="HOLD", title=attr.label, lead="", stage=None))
    decision = map_attribution_to_decision(attr.label)
    exp_path = folder / "expected_output.json"
    expected = json.loads(exp_path.read_text(encoding="utf-8")).get("label") if exp_path.exists() else None
    return {
        "id": jid, "code": journey.journey_code, "product": meta.get("product") or "",
        "simulated": "SIMULATED" in meta,
        "verdict": {"label": attr.label, **v, "stage_name": STAGES.get(v["stage"]) if v["stage"] else None,
                    "reason": attr.rationale_text, "interval": attr.interval,
                    "decision_code": decision[0], "decision": decision[1],
                    "breach": BREACH.get(attr.breach_depth), "trusted_set": attr.trusted_set},
        "expected": expected, "matches_expected": (expected == attr.label) if expected else None,
        "checkpoints": checkpoints,
        "integrity": {k: integrity[k] for k in ("status", "summary", "problems", "photos_checked")},
        "provenance": provenance_checks(journey.checkpoints),
        "settings": {"theta": THETA, "gamma": GAMMA, "z": Z},
    }


def create_console_app() -> FastAPI:
    app = FastAPI(title="TriNetra-Link Console", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    @app.get("/api/journeys")
    def journeys() -> List[Dict[str, Any]]:
        return list_journeys()

    @app.get("/api/analyze/{jid}")
    def analyze_route(jid: str) -> Dict[str, Any]:
        try:
            return analyze(jid)
        except HTTPException:
            raise
        except Exception as exc:  # surface the cause to the page instead of a bare 500
            raise HTTPException(status_code=422, detail=f"Could not analyse this journey: {exc}") from exc

    @app.get("/api/report/{jid}")
    def report(jid: str) -> Response:
        from trinetra_link.console.report import build_report

        result = analyze(jid)
        pdf = build_report(result, _folder(jid))
        name = f"TriNetra_dispute_report_{result['code']}.pdf".replace("/", "_")
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/image/{jid}/{rel_path:path}")
    def image(jid: str, rel_path: str, stamped: int = 0) -> Response:
        folder = _folder(jid)
        path = (folder / rel_path).resolve()
        if folder not in path.parents or not path.is_file() or path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise HTTPException(status_code=404, detail="Image not found")
        if not stamped:
            return FileResponse(path)
        found = stamped_lines_for(folder, path)
        if found is None:
            return FileResponse(path)
        return Response(render_stamped(path, found), media_type="image/jpeg")

    return app


def stamped_lines_for(folder: Path, path: Path) -> Optional[List[str]]:
    """Stamp text for a photo, built from the journey's recorded (and sealed) metadata."""
    _meta, journey = _load(folder)
    for cp in journey.checkpoints:
        for im in cp.images:
            if Path(im.path).resolve() == path:
                return stamp_lines(cp, im)
    return None


def find_journey(group: str, name: str) -> Optional[Path]:
    try:
        return _folder(f"{group}:{name}")
    except HTTPException:
        return None
