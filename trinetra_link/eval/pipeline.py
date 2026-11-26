from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import numpy as np

from trinetra_link.attribution.bayes import attribute_bayes
from trinetra_link.attribution.interval import attribute_interval_algorithm_1
from trinetra_link.quality.gate import QualityGate
from trinetra_link.quality.provenance import glare_reported, identifiers_independent_of_photos
from trinetra_link.reconcile.identity import reconcile_identity
from trinetra_link.reconcile.seals import determine_breach_depth, reconcile_seal_layers
from trinetra_link.reconcile.visual import reconcile_visual
from trinetra_link.reconcile.weight import reconcile_weights
from trinetra_link.schema.models import Attribution, Journey, QualityReport


def canonicalize_label(label: str) -> str:
    """Ensure exact canonical label format across all methods."""
    lbl = label.strip()
    if lbl in ("LEGITIMATE", "ATTR_CONFIRMED_LEGITIMATE"):
        return "ATTR_CONFIRMED_LEGITIMATE"
    if lbl in ("ABSTAIN_DEGRADED", "ATTR_ABSTAIN_DEGRADED"):
        return "ATTR_ABSTAIN_DEGRADED"
    if lbl in ("ABSTAIN_INDISTINGUISHABLE", "ATTR_ABSTAIN_INDISTINGUISHABLE"):
        return "ATTR_ABSTAIN_INDISTINGUISHABLE"
    if lbl in ("ATTR_STAGE(1)", "STAGE(1)", "ATTR_STAGE_1", "STAGE_1", "ATTR_STAGE_FORWARD_TRANSIT"):
        return "ATTR_STAGE_FORWARD_TRANSIT"
    if lbl in ("ATTR_STAGE(2)", "STAGE(2)", "ATTR_STAGE_2", "STAGE_2", "ATTR_STAGE_CONSUMER_CUSTODY"):
        return "ATTR_STAGE_CONSUMER_CUSTODY"
    if lbl in ("ATTR_STAGE(3)", "STAGE(3)", "ATTR_STAGE_3", "STAGE_3", "ATTR_STAGE_REVERSE_TRANSIT"):
        return "ATTR_STAGE_REVERSE_TRANSIT"
    return lbl


def predict_trinetra_link(
    journey: Journey,
    mode: str = "algorithm1",
    theta: float = 0.70,
    tau: float = 0.80,
    z_weight: float = 3.0,
    visual_threshold: float = 0.25,
    scales_config: Optional[Dict[str, Any]] = None,
    scales_path: Optional[Path | str] = None,
    disable_quality_gate: bool = False,
    disable_visual: bool = False,
    disable_seals: bool = False,
    fixed_weight_threshold: Optional[float] = None,
    visual_method: str = "global",
) -> Attribution:
    """
    Run full TriNetra-Link pipeline on a journey:
      1. Quality Gate evaluations -> q_k in [0, 1] per modality (photo, weight, seal)
      2. Multimodal physical reconciliation vs CP1 baseline -> z_k in {INTACT, ANOM, UNK}
      3. Attribution rule (Algorithm 1 or Bayesian posterior coalescence)
    Supports ablation configurations:
      - disable_quality_gate: forces all q_k = 1.0
      - disable_visual: ignores visual reconciler anomalies
      - fixed_weight_threshold: replaces scale noise model with constant grams threshold
    visual_method: "global" (preregistered 1 - SSIM of the rectified face) or "local"
      (registered, block-wise structural dissimilarity; see reconcile.visual.compute_local_change_score).
    """
    code = journey.journey_code
    cps = {cp.cp_index: cp for cp in journey.checkpoints}
    cp1 = cps.get(1)

    if not cp1 or len(cps) < 4:
        return Attribution(
            journey_code=code,
            label="ATTR_ABSTAIN_DEGRADED",
            rationale_text="Missing or incomplete checkpoint observations (fewer than 4 checkpoints).",
            breach_depth=determine_breach_depth(journey.checkpoints) if not disable_seals else "none",
        )

    # Pass scales_config to QualityGate so scale_sigma is known
    gate_cfg = None
    if scales_config:
        gate_cfg = {"scale": {"scales": scales_config.get("scales", {}), "sigma_g": 1.0}}
    gate = QualityGate(config=gate_cfg, theta=theta)
    q_reports: Dict[int, QualityReport] = {}
    q_k: Dict[int, float] = {}

    # 1. Quality Gate evaluation
    for k in (1, 2, 3, 4):
        cp = cps.get(k)
        if not cp:
            q_k[k] = 0.0
            continue

        if disable_quality_gate:
            qr = QualityReport(
                journey_code=code,
                cp_index=k,
                q_k=1.0,
                feature_scores={
                    "q_scale": 1.0,
                    "q_weight": 1.0,
                    "q_temporal": 1.0,
                    "q_seal": 1.0,
                    "q_image": 1.0,
                    "q_photo": 1.0,
                },
                passed=True,
                reasons=[],
            )
        else:
            prev_cp = cps.get(k - 1) if k > 1 else None
            qr = gate.evaluate(cp, previous_observation=prev_cp)

        q_reports[k] = qr
        q_k[k] = qr.q_k

    # 2. Multimodal Reconciliation
    # Every comparison is against CP1, so a modality can only be trusted at CP k if it was also
    # trusted at the CP1 reference (a blurred or dark CP1 photo cannot anchor a visual comparison).
    qr1 = q_reports[1]
    q1_photo = qr1.feature_scores.get("q_photo", qr1.feature_scores.get("q_image", 1.0))
    q1_weight = qr1.feature_scores.get("q_weight", qr1.feature_scores.get("q_scale", 1.0))
    q1_seal = qr1.feature_scores.get("q_seal", qr1.feature_scores.get("q_temporal", 1.0))
    ref_photo_ok = (q1_photo >= theta) and bool(cp1.images) and not glare_reported(cp1)
    ref_weight_ok = (q1_weight >= theta) and cp1.scale_status in ("OK", "MANUAL", "SETTLED")
    ref_seal_ok = (q1_seal >= theta) and (ref_photo_ok or identifiers_independent_of_photos(cp1))

    z_k: Dict[int, str] = {1: "INTACT"}
    modality_evidence: Dict[int, Dict[str, Tuple[str, float]]] = {}

    for k in (2, 3, 4):
        cp_k = cps.get(k)
        if not cp_k:
            z_k[k] = "UNK"
            continue

        qr = q_reports[k]
        q_weight = qr.feature_scores.get("q_weight", qr.feature_scores.get("q_scale", 1.0))
        q_seal = qr.feature_scores.get("q_seal", qr.feature_scores.get("q_temporal", 1.0))
        q_photo = qr.feature_scores.get("q_photo", qr.feature_scores.get("q_image", 1.0))

        # Weight test
        tare_delta = sum(
            cp.tare_delta_g
            for cp in journey.checkpoints
            if cp.cp_index <= k and cp.permitted_packaging_change
        )
        if fixed_weight_threshold is not None:
            w1 = float(np.mean(cp1.weights_g)) if cp1.weights_g else 0.0
            wk = float(np.mean(cp_k.weights_g)) if cp_k.weights_g else 0.0
            weight_diff = abs(wk - w1 - tare_delta)
            weight_anom = weight_diff > fixed_weight_threshold
            delta_w = weight_diff
        else:
            weight_anom, delta_w, _ = reconcile_weights(
                obs_baseline=cp1,
                obs_current=cp_k,
                z=z_weight,
                scales_file_path=scales_path,
                cumulative_tare_delta_g=tare_delta,
            )

        # Identity test
        identity_anom, mismatches = reconcile_identity(obs_baseline=cp1, obs_current=cp_k)

        # Layered seals test
        if disable_seals:
            seal_layers = {layer: "INTACT" for layer in ("L1_FWD", "L1_RET", "L2_BOX", "L3_ITEM")}
        else:
            seal_layers = reconcile_seal_layers(journey.checkpoints, k)

        # Visual test
        if disable_visual:
            visual_anom = False
            visual_scores = {}
        else:
            visual_anom, visual_scores = reconcile_visual(
                obs_baseline=cp1,
                obs_current=cp_k,
                visual_threshold=visual_threshold,
                method=visual_method,
            )

        # Checkpoint-level glare over defect
        has_glare_cp = glare_reported(cp_k)
        if has_glare_cp:
            q_photo = min(q_photo, 0.20)

        is_human_typed = identifiers_independent_of_photos(cp_k)
        trusted_photo = (q_photo >= theta) and bool(cp_k.images) and not disable_visual and ref_photo_ok

        # Rule: A checkpoint whose photos are untrusted (dark or blurred) cannot read seal IDs
        # from photos: seal modality is UNREADABLE there unless typed by a human
        if not trusted_photo and not is_human_typed:
            trusted_seal = False
            q_seal = 0.0
        else:
            trusted_seal = (q_seal >= theta) and ref_seal_ok and bool(
                cp_k.seal_qr or cp_k.serial or cp_k.imei or (cp_k.seals and not disable_seals)
            )

        trusted_weight = (
            (q_weight >= theta)
            and ref_weight_ok
            and (weight_anom != "UNKNOWN")
            and bool(cp_k.weights_g)
            and bool(cp1.weights_g)
            and cp_k.scale_status in ("OK", "MANUAL", "SETTLED")
        )

        weight_obs = "ANOM" if weight_anom is True else ("INTACT" if weight_anom is False else "UNK")
        seal_obs = "ANOM" if identity_anom else "INTACT"
        photo_obs = "ANOM" if visual_anom else "INTACT"

        modality_evidence[k] = {
            "weight": (weight_obs if trusted_weight else "UNK", q_weight if trusted_weight else 0.0),
            "seal": (seal_obs if trusted_seal else "UNK", q_seal if trusted_seal else 0.0),
            "photo": (photo_obs if trusted_photo else "UNK", q_photo if trusted_photo else 0.0),
        }

        # Integrate per-layer seal anomalies
        if not disable_seals:
            for l_name, l_st in seal_layers.items():
                if not trusted_seal:
                    modality_evidence[k][f"seal_{l_name}"] = ("UNK", 0.0)
                elif l_st == "ANOM":
                    modality_evidence[k][f"seal_{l_name}"] = ("ANOM", q_seal)
                elif l_st == "UNK":
                    modality_evidence[k][f"seal_{l_name}"] = ("UNK", 0.0)
                else:
                    modality_evidence[k][f"seal_{l_name}"] = ("INTACT", q_seal)

        anomalies_present = []
        agreements_present = []

        if trusted_weight:
            (anomalies_present if weight_anom is True else agreements_present).append("weight")
        if trusted_seal:
            # Seal QR, serial and IMEI identity is always checked; disable_seals removes only the layered seals.
            if identity_anom:
                anomalies_present.append("seal")
            else:
                agreements_present.append("seal")
        if trusted_seal and not disable_seals:
            for l_name, l_st in seal_layers.items():
                if l_st == "ANOM":
                    anomalies_present.append(f"seal_{l_name}")
                elif l_st == "INTACT":
                    agreements_present.append(f"seal_{l_name}")
        if trusted_photo:
            (anomalies_present if visual_anom else agreements_present).append("photo")

        if anomalies_present:
            z_k[k] = "ANOM"
        elif agreements_present:
            z_k[k] = "INTACT"
        else:
            z_k[k] = "UNK"

        # Checkpoint is TRUSTED for localisation only if modalities that detected/ruled out change are trusted
        # A checkpoint inside (a,b) with untrusted photo AND untrusted/unknown weight -> untrusted (q_k = 0.0)
        if not trusted_photo and not trusted_weight:
            q_k[k] = 0.0
        else:
            trusted_mod_scores = [q for (obs, q) in modality_evidence[k].values() if q >= theta]
            q_k[k] = max(trusted_mod_scores) if trusted_mod_scores else 0.0

    # Rule: Glare over defect at bounding checkpoints -> photo modality untrusted there ->
    # ABSTAIN_INDISTINGUISHABLE when no other trusted modality shows the change.
    glare_cps = [k for k in (2, 3, 4) if k in cps and glare_reported(cps[k])]
    other_trusted_anom = any(
        modality_evidence.get(k, {}).get("weight", ("UNK", 0.0))[0] == "ANOM"
        or modality_evidence.get(k, {}).get("seal", ("UNK", 0.0))[0] == "ANOM"
        or any(
            obs == "ANOM"
            for mkey, (obs, _) in modality_evidence.get(k, {}).items()
            if mkey.startswith("seal_")
        )
        for k in (2, 3, 4)
    )
    if len(glare_cps) >= 2 and not other_trusted_anom:
        return Attribution(
            journey_code=code,
            label="ATTR_ABSTAIN_INDISTINGUISHABLE",
            interval=None,
            trusted_set=[k for k in (1, 2, 3, 4) if q_k.get(k, 0.0) >= theta],
            per_modality_evidence={"q_k": q_k, "z_k": z_k, "modality_evidence": modality_evidence},
            rationale_text="Optical specular glare obscures defect across bounding checkpoints; no other trusted modality shows change. Ambiguous attribution.",
            breach_depth=determine_breach_depth(journey.checkpoints) if not disable_seals else "none",
        )

    # 3. Attribution Rule Selection
    if mode == "bayes":
        attr = attribute_bayes(
            journey_code=code,
            q_k=q_k,
            z_k=z_k,
            tau=tau,
            theta=theta,
            modality_evidence=modality_evidence,
        )
    else:
        # Default: Algorithm 1 (deterministic interval attribution)
        attr = attribute_interval_algorithm_1(
            journey_code=code,
            q_k=q_k,
            z_k=z_k,
            theta=theta,
        )

    # Keep the per-modality evidence on every result so interfaces can show why each checkpoint was judged
    attr.per_modality_evidence = {**(attr.per_modality_evidence or {}), "modality_evidence": modality_evidence}

    # Standardize label output
    attr.label = canonicalize_label(attr.label)
    attr.breach_depth = determine_breach_depth(journey.checkpoints) if not disable_seals else "none"
    return attr
