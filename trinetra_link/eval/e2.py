from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — no Tk/display needed
import matplotlib.pyplot as plt
import numpy as np

from trinetra_link.config import DERIVED_DATA_DIR, REPO_ROOT, RESULTS_DIR
from trinetra_link.eval.loading import SELF_TEST_WATERMARK, SYNTHETIC_WATERMARK, load_evaluation_journeys, require_real_or_allowed
from trinetra_link.eval.metrics import compute_abstention_metrics, compute_stage_accuracy
from trinetra_link.eval.pipeline import canonicalize_label, predict_trinetra_link
from trinetra_link.schema.models import Journey
from trinetra_link.staging.determinability import derive_ground_truth
from trinetra_link.staging.log import load_staging_log


def perturb_drop_checkpoint(journey: Journey, drop_k: int) -> Journey:
    """Drop checkpoint k completely from journey observation sequence."""
    j_copy = copy.deepcopy(journey)
    j_copy.checkpoints = [cp for cp in j_copy.checkpoints if cp.cp_index != drop_k]
    return j_copy


def perturb_scale_drift(journey: Journey, drift_g: float, target_cp: int = 3) -> Journey:
    """Add uncalibrated mechanical scale drift offset to readings at and after target_cp."""
    j_copy = copy.deepcopy(journey)
    for cp in j_copy.checkpoints:
        if cp.cp_index >= target_cp:
            cp.weights_g = [round(w + drift_g, 2) for w in cp.weights_g]
    return j_copy


def _resolve_image_path(path: str) -> Optional[Path]:
    """Find an image on disk: as given (absolute or relative to the working directory), else under the repository."""
    candidate = Path(path)
    if candidate.exists():
        return candidate
    candidate = REPO_ROOT / path
    return candidate if candidate.exists() else None


def _perturb_images(
    journey: Journey,
    target_cp: int,
    transform: Callable[[np.ndarray], np.ndarray],
    tag: str,
    out_dir: Optional[Path],
) -> Journey:
    """Apply a pixel transform to every photo at checkpoint target_cp, writing perturbed copies to out_dir."""
    import cv2

    j_copy = copy.deepcopy(journey)
    if out_dir is None:
        return j_copy
    out_dir.mkdir(parents=True, exist_ok=True)
    for cp in j_copy.checkpoints:
        if cp.cp_index != target_cp:
            continue
        for img in cp.images:
            src = _resolve_image_path(img.path)
            if src is None:
                continue
            pixels = cv2.imread(str(src))
            if pixels is None:
                continue
            perturbed = transform(pixels)
            dst = out_dir / f"{journey.journey_code}_CP{cp.cp_index}_{img.side}_{tag}.png"
            cv2.imwrite(str(dst), perturbed)
            img.path = str(dst)
            img.sha256 = hashlib.sha256(dst.read_bytes()).hexdigest()
    return j_copy


def perturb_gamma_darkening(journey: Journey, gamma: float, target_cp: int = 2, out_dir: Optional[Path] = None) -> Journey:
    """Darken the photos at target_cp with a gamma transform: I -> 255 * (I / 255) ** gamma."""
    table = np.array([255.0 * (i / 255.0) ** gamma for i in range(256)]).clip(0, 255).astype(np.uint8)

    def transform(pixels: np.ndarray) -> np.ndarray:
        return table[pixels]

    return _perturb_images(journey, target_cp, transform, f"gamma{gamma:g}", out_dir)


def perturb_blur(journey: Journey, sigma: float, target_cp: int = 2, out_dir: Optional[Path] = None) -> Journey:
    """Blur the photos at target_cp with a Gaussian kernel of standard deviation sigma (pixels)."""
    import cv2

    def transform(pixels: np.ndarray) -> np.ndarray:
        return cv2.GaussianBlur(pixels, (0, 0), sigma)

    return _perturb_images(journey, target_cp, transform, f"blur{sigma:g}", out_dir)


def _bounding_checkpoints(staging_row: Dict[str, Any]) -> set:
    """Checkpoints bounding the staged manipulation interval S_k: {k, k + 1}; empty when nothing was staged."""
    interval = str(staging_row.get("manipulation_interval", "none")).strip().upper()
    if interval.startswith("S") and interval[1:].isdigit():
        k = int(interval[1:])
        return {k, k + 1}
    return set()


def evaluate_e2(
    split_manifest_path: Optional[Path | str] = None,
    staging_log_path: Optional[Path | str] = None,
    output_dir: Optional[Path | str] = None,
    run_id: Optional[str] = None,
    theta: float = 0.70,
    visual_threshold: float = 0.25,
    visual_method: str = "global",
    scales_path: Optional[Path | str] = None,
    store_path: Optional[Path | str] = None,
    allow_label_rebuild: bool = False,
    allow_synthetic_dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute Experiment E2: Controlled Perturbation Robustness Evaluation.
    Applies perturbations to the captured test journeys (pixel-level for blur and darkening):
      - Dropped checkpoint: k in {2, 3}
      - Gaussian blur: sigma in {1.0, 2.0, 4.0}
      - Gamma darkening: gamma in {1.5, 2.5, 4.0}
      - Scale drift: offset in {5.0, 20.0, 50.0} g
    Recomputes Omega* using the determinability rule, and measures method performance.
    """
    rid = run_id or f"e2_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    target_dir = Path(output_dir) if output_dir else RESULTS_DIR / rid
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load split manifest
    s_path = Path(split_manifest_path) if split_manifest_path else DERIVED_DATA_DIR / "split_manifest.json"
    if not s_path.exists():
        raise FileNotFoundError(f"Split manifest not found at {s_path}")

    with open(s_path, "r", encoding="utf-8") as f:
        split_data = json.load(f)

    test_codes = set(split_data.get("test_journey_codes", []))
    is_synthetic = require_real_or_allowed(split_data, s_path, allow_synthetic_dry_run or allow_label_rebuild)

    # 2. Load staging log
    staging_rows = load_staging_log(staging_log_path)
    if not staging_rows:
        raise FileNotFoundError("Staging log not found or empty; ground truth is derived only from the staging log.")

    test_staging = [r for r in staging_rows if r["journey_code"] in test_codes]
    base_journeys = load_evaluation_journeys(test_staging, store_path=store_path, allow_label_rebuild=allow_label_rebuild)
    images_dir = target_dir / "perturbed_images"

    scales_config = None
    sc_path = Path(scales_path) if scales_path else DERIVED_DATA_DIR / "scales.json"
    if sc_path.exists():
        with open(sc_path, "r", encoding="utf-8") as fp:
            scales_config = json.load(fp)

    # Perturbation conditions to evaluate
    # target: the checkpoint whose evidence is perturbed (drift affects it and every later one).
    # degraded: whether the perturbation can make that checkpoint unusable; ground truth becomes
    # DEG only for journeys whose manipulation interval that checkpoint bounds.
    perturbation_specs = [
        {"name": "Clean Baseline", "type": "baseline", "param": "none", "target": None, "fn": lambda j: j, "degraded": False},
        {"name": "Drop CP2", "type": "drop_checkpoint", "param": "k=2", "target": 2, "fn": lambda j: perturb_drop_checkpoint(j, 2), "degraded": True},
        {"name": "Drop CP3", "type": "drop_checkpoint", "param": "k=3", "target": 3, "fn": lambda j: perturb_drop_checkpoint(j, 3), "degraded": True},
        {"name": "Blur (sigma=1.0)", "type": "blur", "param": "1.0", "target": 2, "fn": lambda j: perturb_blur(j, 1.0, out_dir=images_dir), "degraded": False},
        {"name": "Blur (sigma=2.0)", "type": "blur", "param": "2.0", "target": 2, "fn": lambda j: perturb_blur(j, 2.0, out_dir=images_dir), "degraded": False},
        {"name": "Blur (sigma=4.0)", "type": "blur", "param": "4.0", "target": 2, "fn": lambda j: perturb_blur(j, 4.0, out_dir=images_dir), "degraded": True},
        {"name": "Darken (gamma=1.5)", "type": "gamma", "param": "1.5", "target": 2, "fn": lambda j: perturb_gamma_darkening(j, 1.5, out_dir=images_dir), "degraded": False},
        {"name": "Darken (gamma=2.5)", "type": "gamma", "param": "2.5", "target": 2, "fn": lambda j: perturb_gamma_darkening(j, 2.5, out_dir=images_dir), "degraded": True},
        {"name": "Darken (gamma=4.0)", "type": "gamma", "param": "4.0", "target": 2, "fn": lambda j: perturb_gamma_darkening(j, 4.0, out_dir=images_dir), "degraded": True},
        {"name": "Scale Drift (5g)", "type": "drift", "param": "5g", "target": 3, "fn": lambda j: perturb_scale_drift(j, 5.0), "degraded": False},
        {"name": "Scale Drift (20g)", "type": "drift", "param": "20g", "target": 3, "fn": lambda j: perturb_scale_drift(j, 20.0), "degraded": False},
        {"name": "Scale Drift (50g)", "type": "drift", "param": "50g", "target": 3, "fn": lambda j: perturb_scale_drift(j, 50.0), "degraded": False},
    ]

    results_e2: List[Dict[str, Any]] = []

    for spec in perturbation_specs:
        perturbed_journeys = [spec["fn"](j) for j in base_journeys]
        preds = []
        gts = []
        omegas = []

        for j_orig, j_pert, r_stg in zip(base_journeys, perturbed_journeys, test_staging):
            # Recompute ground truth determinability under perturbation
            is_usable = not (spec["degraded"] and spec["target"] in _bounding_checkpoints(r_stg))
            omega_star, exp_label, _ = derive_ground_truth(r_stg, capture_quality_passed=is_usable)

            attr = predict_trinetra_link(j_pert, theta=theta, visual_threshold=visual_threshold, visual_method=visual_method, scales_config=scales_config, scales_path=sc_path if sc_path.exists() else None)
            preds.append(canonicalize_label(attr.label))
            gts.append(canonicalize_label(exp_label))
            omegas.append(omega_star)

        acc, n_corr, n_det = compute_stage_accuracy(preds, gts, omegas)
        abs_m = compute_abstention_metrics(preds, gts, omegas)

        results_e2.append({
            "condition": spec["name"],
            "perturbation_type": spec["type"],
            "parameter": spec["param"],
            "stage_acc_det": acc,
            "aar_non_det": abs_m["aar"],
            "ubr_non_det": abs_m["ubr"],
            "uar_det": abs_m["uar"],
            "n_det": n_det,
        })

    # Save Tables: CSV and LaTeX
    csv_path = target_dir / "table_e2_perturbations.csv"
    with open(csv_path, "w", encoding="utf-8") as fp:
        if allow_label_rebuild:
            fp.write(f"# {SELF_TEST_WATERMARK}\n")
        if is_synthetic:
            fp.write(f"# {SYNTHETIC_WATERMARK}\n")
        fp.write("Condition,Perturbation Type,Parameter,Stage Acc (DET),AAR (Non-DET),UBR (Non-DET),UAR (DET)\n")
        for r in results_e2:
            fp.write(f"{r['condition']},{r['perturbation_type']},{r['parameter']},{r['stage_acc_det']},{r['aar_non_det']},{r['ubr_non_det']},{r['uar_det']}\n")

    latex_path = target_dir / "table_e2_perturbations.tex"
    with open(latex_path, "w", encoding="utf-8") as fp:
        fp.write("% TriNetra-Link Perturbation Robustness (E2)\n\\begin{table}[t]\n\\centering\n\\small\n")
        fp.write("\\begin{tabular}{lcccc}\n\\toprule\n\\textbf{Condition} & \\textbf{Acc (DET)} & \\textbf{AAR} & \\textbf{UBR} & \\textbf{UAR} \\\\\n\\midrule\n")
        for r in results_e2:
            fp.write(f"{r['condition']} & {r['stage_acc_det']:.3f} & {r['aar_non_det']:.3f} & {r['ubr_non_det']:.3f} & {r['uar_det']:.3f} \\\\\n")
        fp.write("\\bottomrule\n\\end{tabular}\n\\caption{Robustness under physical capture perturbations (E2).}\n\\end{table}\n")

    # Generate Figure: Robustness curves across levels
    fig_png = target_dir / "figure_robustness.png"
    fig_pdf = target_dir / "figure_robustness.pdf"

    drift_levels = [0, 5, 20, 50]
    drift_accs = [
        results_e2[0]["stage_acc_det"],
        results_e2[9]["stage_acc_det"],
        results_e2[10]["stage_acc_det"],
        results_e2[11]["stage_acc_det"],
    ]

    plt.figure(figsize=(6, 4.5), dpi=300)
    plt.plot(drift_levels, drift_accs, marker="o", color="#1f77b4", lw=2, label="TriNetra-Link (Weight drift)")
    plt.xlabel("Scale Drift Perturbation (grams)", fontsize=11)
    plt.ylabel("Stage Accuracy (DET)", fontsize=11)
    plt.title("Robustness vs. Scale Linearity Drift (E2)", fontsize=12, fontweight="bold")
    plt.ylim(0.0, 1.05)
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend(loc="lower left")
    plt.tight_layout()
    plt.savefig(fig_png)
    plt.savefig(fig_pdf)
    plt.close()

    manifest = {
        "experiment": "E2",
        "run_id": rid,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_test_journeys": len(base_journeys),
        "conditions_evaluated": len(results_e2),
        "theta": theta,
        "journeys_from": "label rebuild (self-test)" if allow_label_rebuild else "captured store",
        "results": results_e2,
        "artifacts": {
            "csv_table": str(csv_path),
            "latex_table": str(latex_path),
            "figure_png": str(fig_png),
            "figure_pdf": str(fig_pdf),
        },
    }

    if allow_label_rebuild:
        manifest["watermark"] = SELF_TEST_WATERMARK
    elif is_synthetic:
        manifest["watermark"] = SYNTHETIC_WATERMARK

    with open(target_dir / "provenance.json", "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, indent=2)

    return manifest
