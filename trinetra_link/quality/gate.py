from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from trinetra_link.config import load_quality_config
from trinetra_link.quality.features import (
    compute_image_quality_features,
    score_photo,
    evaluate_scale_readings,
    evaluate_temporal_order,
)
from trinetra_link.quality.provenance import glare_reported, identifiers_independent_of_photos
from trinetra_link.schema.models import CheckpointObservation, QualityReport


_IMAGE_FEATS_CACHE: Dict[str, Dict[str, float]] = {}


class QualityGate:
    """
    Evaluates physical observation telemetry and photographic metadata to produce
    a non-negative trust factor q_k in [0, 1]. Reads metadata only, never ground truth.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, theta: float = 0.70):
        self.config = config or load_quality_config()
        self.theta = theta

    def evaluate(
        self,
        observation: CheckpointObservation,
        previous_observation: Optional[CheckpointObservation] = None,
        image_arrays: Optional[Dict[str, np.ndarray]] = None,
    ) -> QualityReport:
        cfg = self.config
        img_cfg = cfg.get("image", {})
        scale_cfg = cfg.get("scale", {})
        temp_cfg = cfg.get("temporal", {})

        reasons: List[str] = []
        feature_scores: Dict[str, float] = {}

        # 1. Scale Telemetry Gate (using 4*sigma stability rule)
        scale_sigma = None
        if observation.scale_id and "scales" in scale_cfg:
            scale_sigma = scale_cfg["scales"].get(observation.scale_id, {}).get("sigma_g")
        if scale_sigma is None:
            scale_sigma = scale_cfg.get("sigma_g", 1.0)

        q_scale, scale_reasons = evaluate_scale_readings(
            weights_g=observation.weights_g,
            scale_status=observation.scale_status,
            min_readings=scale_cfg.get("min_readings", 3),
            min_weight_g=scale_cfg.get("min_weight_g", 1.0),
            max_spread_g=scale_cfg.get("max_spread_g"),
            scale_sigma=scale_sigma,
            allowed_statuses=scale_cfg.get("allowed_statuses", ["OK", "MANUAL", "SETTLED"]),
        )
        q_weight = q_scale if observation.weights_g else 0.0
        feature_scores["q_scale"] = q_scale
        feature_scores["q_weight"] = q_weight
        reasons.extend(scale_reasons)

        # 2. Temporal Continuity & Calibration Gate
        prev_ts = previous_observation.ts_utc if previous_observation else None
        q_temp, temp_reasons = evaluate_temporal_order(
            current_ts=observation.ts_utc,
            prev_ts=prev_ts,
            calibration_date_str=observation.calibration_date,
            max_cal_age_days=temp_cfg.get("max_calibration_age_days", 365),
        )
        feature_scores["q_temporal"] = q_temp
        reasons.extend(temp_reasons)

        # Seal modality trust: temporal continuity intact + seal/serial presence
        has_seal = bool(observation.seal_qr or observation.serial or observation.imei)
        q_seal = q_temp if has_seal else 0.0
        feature_scores["q_seal"] = q_seal

        # 3. Photographic Asset Metadata Gates
        q_image = 0.0
        if observation.images:
            image_scores: List[float] = []
            for img_ref in observation.images:
                # Resolution check
                w_ok = img_ref.w >= img_cfg.get("min_width", 640)
                h_ok = img_ref.h >= img_cfg.get("min_height", 480)
                res_score = 1.0 if (w_ok and h_ok) else min(
                    img_ref.w / img_cfg.get("min_width", 640),
                    img_ref.h / img_cfg.get("min_height", 480),
                )
                feature_scores[f"q_res_{img_ref.side}"] = res_score

                # Image pixels check if image array is passed or exists
                img_arr = None
                if image_arrays and img_ref.side in image_arrays:
                    img_arr = image_arrays[img_ref.side]
                elif Path(img_ref.path).exists():
                    import cv2
                    img_arr = cv2.imread(str(img_ref.path))

                if img_arr is not None:
                    use_cache = (image_arrays is None) and bool(img_ref.path)
                    cache_key = str(img_ref.path) if use_cache else ""
                    if use_cache and cache_key in _IMAGE_FEATS_CACHE:
                        feats = _IMAGE_FEATS_CACHE[cache_key]
                    else:
                        feats = compute_image_quality_features(img_arr, exif_exposure=img_ref.exposure)
                        if use_cache and cache_key:
                            _IMAGE_FEATS_CACHE[cache_key] = feats
                    scored = score_photo(feats, res_score, img_cfg, side=img_ref.side)
                    reasons.extend(scored["reasons"])
                    img_combined = scored["score"]
                    feature_scores[f"q_lum_{img_ref.side}"] = scored["lum_score"]
                    feature_scores[f"q_sharp_{img_ref.side}"] = scored["sharp_score"]
                    feature_scores[f"q_spec_{img_ref.side}"] = scored["spec_score"]
                    image_scores.append(img_combined)
                else:
                    # Without pixel array available, rely on resolution
                    image_scores.append(res_score)

            if image_scores:
                # Geometric mean across sides
                q_image = float(np.prod(image_scores) ** (1.0 / len(image_scores)))
        q_photo = q_image
        # Glare over defect degrades photo modality trust
        if glare_reported(observation):
            q_photo = min(q_photo, 0.20)
            reasons.append("Camera glare over defect")

        feature_scores["q_photo"] = q_photo
        feature_scores["q_image"] = q_photo

        # Rule: A checkpoint whose photos are untrusted cannot read seal IDs from photos
        # Seal modality is UNREADABLE there unless the ID was typed by a human
        is_human_typed = identifiers_independent_of_photos(observation)
        if (q_photo < self.theta) and not is_human_typed:
            q_seal = 0.0
            feature_scores["q_seal"] = 0.0
            reasons.append(f"Seal unreadable: photos untrusted (q_photo={q_photo:.3f} < {self.theta:.2f})")

        # Checkpoint is TRUSTED for localisation only if modalities that detected or ruled out
        # the change are trusted; a checkpoint with untrusted photo AND untrusted/unknown weight -> untrusted
        has_valid_weights = bool(observation.weights_g) and observation.scale_status in ("OK", "MANUAL", "SETTLED")
        if (q_photo < self.theta) and (q_weight < self.theta or not has_valid_weights):
            q_k = 0.0
        else:
            trusted_scores = []
            if q_photo >= self.theta:
                trusted_scores.append(q_photo)
            if q_weight >= self.theta and has_valid_weights:
                trusted_scores.append(q_weight)
            if q_seal >= self.theta:
                trusted_scores.append(q_seal)
            q_k = float(np.clip(max(trusted_scores) if trusted_scores else 0.0, 0.0, 1.0))

        passed = bool(q_k >= self.theta)

        return QualityReport(
            journey_code=observation.journey_code,
            cp_index=observation.cp_index,
            q_k=round(q_k, 4),
            feature_scores=feature_scores,
            passed=passed,
            reasons=reasons,
        )
