from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from trinetra_link.config import DERIVED_DATA_DIR, RESULTS_DIR
from trinetra_link.schema.models import Journey

# Candidate visual thresholds per visual reconciler ("global" is the preregistered 1 - SSIM score).
VISUAL_GRIDS = {
    "global": [0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70],
    "local": [0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.15],
}


def fit_thresholds(
    journeys: List[Journey],
    split_name: str = "calibration",
    allowed_split_prefix: str = "calibration",
    scales_path: Optional[Path | str] = None,
    staging_log_path: Optional[Path | str] = None,
    floors_path: Optional[Path | str] = None,
    output_dir: Optional[Path | str] = None,
    allow_synthetic_dry_run: bool = False,
    visual_method: str = "global",
) -> Dict[str, Any]:
    """
    Fit TriNetra-Link hyperparameters on calibration split only:
        - theta: Quality score threshold
        - z: Weight reconciliation Gaussian bound multiplier
        - tau: Bayesian posterior probability threshold
        - visual_threshold: SSIM change dissimilarity threshold

    Enforces strict calibration split isolation and synthetic provenance guards.
    """
    if split_name != allowed_split_prefix:
        raise ValueError(
            f"FITTING ISOLATION VIOLATION: Thresholds may only be fitted on '{allowed_split_prefix}', got '{split_name}'."
        )

    if not journeys:
        raise ValueError(
            "NO CALIBRATION DATA: fitting needs the captured calibration journeys; refusing to write default thresholds."
        )

    # Check synthetic provenance guards on scales.json
    sc_file = Path(scales_path) if scales_path else DERIVED_DATA_DIR / "scales.json"
    if sc_file.exists() and not allow_synthetic_dry_run:
        try:
            with open(sc_file, "r", encoding="utf-8") as fp:
                sc_data = json.load(fp)
                if sc_data.get("synthetic") is True or "synthetic" in str(sc_data.get("provenance", "")).lower():
                    raise RuntimeError(
                        f"REFUSAL TO EXECUTE ON REAL DATA:\n"
                        f"Scale parameters at '{sc_file}' have synthetic provenance.\n"
                        f"Real calibration fitting refuses synthetic scale parameters."
                    )
        except RuntimeError:
            raise
        except Exception:
            pass

    # Check synthetic provenance guards on frozen_quality_floors.json
    fl_file = Path(floors_path) if floors_path else DERIVED_DATA_DIR / "frozen_quality_floors.json"
    if fl_file.exists() and not allow_synthetic_dry_run:
        try:
            with open(fl_file, "r", encoding="utf-8") as fp:
                fl_data = json.load(fp)
                if fl_data.get("synthetic") is True or "synthetic" in str(fl_data.get("provenance", "")).lower():
                    raise RuntimeError(
                        f"REFUSAL TO EXECUTE ON REAL DATA:\n"
                        f"Quality floors at '{fl_file}' have synthetic provenance.\n"
                        f"Real calibration fitting refuses synthetic quality floors."
                    )
        except RuntimeError:
            raise
        except Exception:
            pass

    # Verify that no journey IDs belong to the test split
    for j in journeys:
        if "test" in j.journey_code.lower() or j.metadata.get("split") == "test":
            raise ValueError(
                f"FITTING ISOLATION VIOLATION: Test journey '{j.journey_code}' passed to calibration fit function!"
            )

    # Optimization on calibration distribution:
    # Maximise (DET accuracy + AAR on non-DET) as required by research quality gate protocol
    theta_fit = 0.70
    z_fit = 3.00
    tau_fit = 0.80
    visual_threshold_fit = 0.25
    fit_score = 0.0
    fit_acc = 0.0
    fit_aar = 0.0
    fit_uar = 0.0

    if journeys:
        import csv
        from trinetra_link.eval.metrics import compute_abstention_metrics, compute_stage_accuracy
        from trinetra_link.eval.pipeline import canonicalize_label, predict_trinetra_link
        from trinetra_link.staging.determinability import derive_ground_truth

        # Ground truth comes only from the staging log; a journey without a staging row is an error.
        s_path = Path(staging_log_path) if staging_log_path else (DERIVED_DATA_DIR.parent / "restricted" / "staging_log_120.csv")
        if not s_path.exists():
            raise FileNotFoundError(f"Staging log not found at {s_path}; ground truth cannot be derived for fitting.")
        with open(s_path, "r", encoding="utf-8") as f:
            staging_rows = {r["journey_code"]: r for r in csv.DictReader(f)}
        missing = [j.journey_code for j in journeys if j.journey_code not in staging_rows]
        if missing:
            raise ValueError(f"{len(missing)} calibration journeys have no staging-log row (e.g. {missing[:3]}).")

        scales_config = None
        if sc_file.exists():
            with open(sc_file, "r", encoding="utf-8") as f:
                scales_config = json.load(f)

        gts, omegas = [], []
        for j in journeys:
            om, exp, _ = derive_ground_truth(staging_rows[j.journey_code])
            gts.append(canonicalize_label(exp))
            omegas.append(om)

        # Grid search with the evaluation pipeline itself, so fitting and testing cannot drift apart.
        theta_grid = [round(x, 2) for x in np.arange(0.30, 0.91, 0.05)]
        visual_grid = VISUAL_GRIDS[visual_method]
        best_key = None
        for vt in visual_grid:
            for th in theta_grid:
                preds = [
                    canonicalize_label(predict_trinetra_link(
                        j, theta=th, visual_threshold=vt, visual_method=visual_method,
                        scales_config=scales_config, scales_path=sc_file if sc_file.exists() else None,
                    ).label)
                    for j in journeys
                ]
                acc, _, _ = compute_stage_accuracy(preds, gts, omegas)
                abs_m = compute_abstention_metrics(preds, gts, omegas)
                score = acc + abs_m["aar"]
                key = (score, -abs_m["uar"], -abs(th - 0.70), -abs(vt - visual_grid[len(visual_grid) // 2]))
                if best_key is None or key > best_key:
                    best_key = key
                    theta_fit, visual_threshold_fit = float(th), float(vt)
                    fit_score, fit_acc, fit_aar, fit_uar = score, acc, abs_m["aar"], abs_m["uar"]

    thresholds = {
        "theta": theta_fit,
        "z_weight": z_fit,
        "tau_bayes": tau_fit,
        "visual_threshold": visual_threshold_fit,
        "visual_method": visual_method,
        "fit_score": round(fit_score, 4),
        "fit_det_acc": round(fit_acc, 4),
        "fit_non_det_aar": round(fit_aar, 4),
        "fit_det_uar": round(fit_uar, 4),
        "fitted_on_split": split_name,
        "num_calibration_journeys": len(journeys),
        "fitted_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    if allow_synthetic_dry_run or any(j.metadata.get("synthetic") for j in journeys):
        thresholds["watermark"] = "SYNTHETIC DRY RUN — NOT A RESULT"
        thresholds["synthetic"] = True

    # Write output to results/<run_id>/thresholds.json
    run_id = f"fit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    target_dir = Path(output_dir) if output_dir else RESULTS_DIR / run_id
    target_dir.mkdir(parents=True, exist_ok=True)

    out_file = target_dir / "thresholds.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(thresholds, f, indent=2)
        f.write("\n")

    thresholds["run_id"] = run_id
    thresholds["saved_path"] = str(out_file)
    return thresholds
