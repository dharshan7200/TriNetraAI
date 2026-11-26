"""Simulation study driver: fit on the calibration split, evaluate on the test split.

All numbers produced here are SIMULATED. They characterise the method under the generative
model in ``simulator.py`` and must be reported as a simulation study.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from trinetra_link.baselines.b1_cp4 import predict_b1_cp4
from trinetra_link.baselines.b2_endpoints import predict_b2_endpoints
from trinetra_link.baselines.b3_unlinked import predict_b3_unlinked
from trinetra_link.baselines.b5_v3_rules import predict_b5_v3_rules
from trinetra_link.eval.metrics import (
    compute_abstention_metrics,
    compute_macro_f1,
    compute_stage_accuracy,
    exact_mcnemar_test,
)
from trinetra_link.eval.pipeline import canonicalize_label, predict_trinetra_link
from trinetra_link.schema.models import Journey
from trinetra_link.staging.determinability import derive_ground_truth
from trinetra_link.store.database import Store

S2 = "ATTR_STAGE_CONSUMER_CUSTODY"
LEGIT = "ATTR_CONFIRMED_LEGITIMATE"
THETA_GRID = [round(x, 2) for x in np.arange(0.30, 0.91, 0.05)]
VISUAL_GRIDS = {
    "global": [0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70],
    "local": [0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.15],
}


def load_benchmark(bench_dir: Path | str, split: str) -> Dict[str, Any]:
    d = Path(bench_dir)
    manifest = json.loads((d / "split_manifest.json").read_text())
    codes = set(manifest[f"{split}_journey_codes"])
    rows = [r for r in csv.DictReader(open(d / "staging_log.csv", encoding="utf-8")) if r["journey_code"] in codes]
    store = Store(d / "store.db")
    journeys = [store.get_journey(r["journey_code"]) for r in rows]
    scales = json.loads((d / "scales.json").read_text())
    return {"rows": rows, "journeys": journeys, "scales": scales, "scales_path": str(d / "scales.json")}


def field_mask(j: Journey) -> Journey:
    """Weights only at CP1 and CP4 (no scales at the carrier facility or the doorstep)."""
    cps = []
    for cp in j.checkpoints:
        c = cp.model_copy(deep=True)
        if c.cp_index in (2, 3):
            c.weights_g = []
        cps.append(c)
    return Journey(journey_code=j.journey_code, checkpoints=cps, metadata=dict(j.metadata or {}))


def _metrics(preds: List[str], gts: List[str], omegas: List[str]) -> Dict[str, Any]:
    acc, correct, n_det = compute_stage_accuracy(preds, gts, omegas)
    ab = compute_abstention_metrics(preds, gts, omegas)
    not_s2 = [i for i, (g, o) in enumerate(zip(gts, omegas)) if not (o == "OBS_DETERMINABLE" and g == S2)]
    legit = [i for i, (g, o) in enumerate(zip(gts, omegas)) if o == "OBS_DETERMINABLE" and g == LEGIT]
    return {
        "stage_acc_det": acc, "n_det": n_det, "macro_f1": compute_macro_f1(preds, gts, omegas),
        "aar": ab["aar"], "ubr": ab["ubr"], "uar": ab["uar"], "n_non_det": ab["non_det_total"],
        "customer_misblame": round(sum(preds[i] == S2 for i in not_s2) / max(1, len(not_s2)), 4),
        "false_accusation_legit": round(sum(preds[i].startswith("ATTR_STAGE") for i in legit) / max(1, len(legit)), 4),
    }


def _bootstrap(preds, gts, omegas, key: str, b: int = 2000, seed: int = 7):
    rng = np.random.default_rng(seed)
    n = len(preds)
    vals = []
    for _ in range(b):
        idx = rng.integers(0, n, n)
        vals.append(_metrics([preds[i] for i in idx], [gts[i] for i in idx], [omegas[i] for i in idx])[key])
    return round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)


def _kw(p: Dict[str, Any], scales: Dict[str, Any], scales_path: str) -> Dict[str, Any]:
    return dict(theta=p["theta"], visual_threshold=p["visual_threshold"], visual_method=p["visual_method"],
                scales_config=scales, scales_path=scales_path)


def methods_for(params: Dict[str, Dict[str, Any]], scales: Dict[str, Any], scales_path: str) -> Dict[str, Callable[[Journey], Any]]:
    """``params`` maps visual method ("local", "global") to its fitted parameters."""
    loc, glo = _kw(params["local"], scales, scales_path), _kw(params["global"], scales, scales_path)
    return {
        "TriNetra-Link (Alg. 1)": lambda j: predict_trinetra_link(j, mode="algorithm1", **loc),
        "TriNetra-Link (Bayes)": lambda j: predict_trinetra_link(j, mode="bayes", **loc),
        "TriNetra-Link (Alg. 1, global SSIM)": lambda j: predict_trinetra_link(j, mode="algorithm1", **glo),
        "B1 CP4-only": predict_b1_cp4,
        "B2 endpoints": predict_b2_endpoints,
        "B3 detection = origin": predict_b3_unlinked,
        "B5 legacy rules": predict_b5_v3_rules,
    }


def ablations_for(params: Dict[str, Dict[str, Any]], scales: Dict[str, Any], scales_path: str) -> Dict[str, Callable[[Journey], Any]]:
    kw = _kw(params["local"], scales, scales_path)
    return {
        "Full (Alg. 1)": lambda j: predict_trinetra_link(j, **kw),
        "No quality gate": lambda j: predict_trinetra_link(j, disable_quality_gate=True, **kw),
        "No visual": lambda j: predict_trinetra_link(j, disable_visual=True, **kw),
        "No layered seals": lambda j: predict_trinetra_link(j, disable_seals=True, **kw),
        "Fixed 10 g weight threshold": lambda j: predict_trinetra_link(j, fixed_weight_threshold=10.0, **kw),
    }


def _truth(rows, mask: str):
    gts, omegas = [], []
    for r in rows:
        om, lab, _ = derive_ground_truth(r, mask=mask)
        gts.append(canonicalize_label(lab))
        omegas.append(om)
    return gts, omegas


def fit_params(bench_dir: Path | str, visual_method: str = "local") -> Dict[str, Any]:
    """Grid-search theta and the visual threshold on the calibration split with the real pipeline."""
    cal = load_benchmark(bench_dir, "calibration")
    gts, omegas = _truth(cal["rows"], "full")
    best = None
    grid = VISUAL_GRIDS[visual_method]
    mid = grid[len(grid) // 2]
    for vt in grid:
        for th in THETA_GRID:
            preds = [canonicalize_label(predict_trinetra_link(
                j, theta=th, visual_threshold=vt, visual_method=visual_method,
                scales_config=cal["scales"], scales_path=cal["scales_path"]).label)
                for j in cal["journeys"]]
            m = _metrics(preds, gts, omegas)
            score = m["stage_acc_det"] + m["aar"]
            key = (score, -m["uar"], -abs(th - 0.70), -abs(vt - mid))
            if best is None or key > best[0]:
                best = (key, {"theta": th, "visual_threshold": vt, "visual_method": visual_method,
                              "cal_score": round(score, 4), **m})
    out = best[1]
    out["n_calibration"] = len(cal["journeys"])
    return out


def evaluate(bench_dir: Path | str, params: Dict[str, Dict[str, Any]], mask: str = "full", which: str = "methods",
             out_dir: Optional[Path | str] = None, bootstrap: int = 2000, split: str = "test") -> Dict[str, Any]:
    if split == "all":
        cal_part, test_part = load_benchmark(bench_dir, "calibration"), load_benchmark(bench_dir, "test")
        test = {**test_part, "rows": cal_part["rows"] + test_part["rows"],
                "journeys": cal_part["journeys"] + test_part["journeys"]}
    else:
        test = load_benchmark(bench_dir, split)
    rows = test["rows"]
    journeys = [field_mask(j) for j in test["journeys"]] if mask == "field" else test["journeys"]
    gts, omegas = _truth(rows, mask)
    fns = (methods_for if which == "methods" else ablations_for)(params, test["scales"], test["scales_path"])
    preds = {name: [canonicalize_label(fn(j).label) for j in journeys] for name, fn in fns.items()}

    ref = next(iter(preds))
    det = [o == "OBS_DETERMINABLE" for o in omegas]
    table = []
    for name, p in preds.items():
        m = _metrics(p, gts, omegas)
        if bootstrap:
            m["stage_acc_ci"] = _bootstrap(p, gts, omegas, "stage_acc_det", b=bootstrap)
            m["customer_misblame_ci"] = _bootstrap(p, gts, omegas, "customer_misblame", b=bootstrap)
        if name != ref:
            b_, c_, pv = exact_mcnemar_test(preds[ref], p, gts, filter_mask=det)
            m["mcnemar_vs_ref"] = {"ref_only_correct": b_, "other_only_correct": c_, "p": pv}
        table.append({"method": name, **m})

    subgroups = {}
    for col in ("assigned_cell", "seal_action", "mass_band", "serial_changed"):
        groups: Dict[str, List[int]] = {}
        for i, r in enumerate(rows):
            groups.setdefault(r.get(col, "n/a"), []).append(i)
        subgroups[col] = {
            g: {name: _metrics([p[i] for i in idx], [gts[i] for i in idx], [omegas[i] for i in idx]) for name, p in preds.items()}
            | {"n": len(idx)}
            for g, idx in sorted(groups.items())
        }
    nuisance_idx = [i for i, r in enumerate(rows) if any(r[c] for c in r if c.startswith("nuisance_"))]
    clean_idx = [i for i in range(len(rows)) if i not in set(nuisance_idx)]
    subgroups["nuisance"] = {
        label: {name: _metrics([p[i] for i in idx], [gts[i] for i in idx], [omegas[i] for i in idx]) for name, p in preds.items()}
        | {"n": len(idx)}
        for label, idx in (("any nuisance", nuisance_idx), ("no nuisance", clean_idx))
    }
    result = {"mask": mask, "which": which, "params": params, "n_test": len(rows), "table": table, "subgroups": subgroups,
              "omega_counts": {o: omegas.count(o) for o in sorted(set(omegas))},
              "watermark": "SIMULATION STUDY — NOT PHYSICAL DATA"}
    if out_dir:
        od = Path(out_dir)
        od.mkdir(parents=True, exist_ok=True)
        (od / f"{which}_{mask}.json").write_text(json.dumps(result, indent=1))
        with open(od / f"predictions_{which}_{mask}.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["journey_code", "assigned_cell", "omega", "truth", *preds.keys()])
            for i, r in enumerate(rows):
                wr.writerow([r["journey_code"], r["assigned_cell"], omegas[i], gts[i], *[p[i] for p in preds.values()]])
    return result
