"""Command-line runner for the simulation study.

    python -m trinetra_link.sim.run_study main  --out results/sim            # benchmark, fit, E1, ablations
    python -m trinetra_link.sim.run_study sweep --out results/sim --param sigma_multiplier --value 2

Every output is SIMULATED and carries that watermark.
"""

from __future__ import annotations

import argparse
import json
import time
import zlib
from dataclasses import replace
from pathlib import Path

import cv2

from trinetra_link.sim import study
from trinetra_link.sim.simulator import SimConfig, simulate_benchmark

MAIN_SEED = 2026
MAIN_MULTIPLIER = 8          # 960 journeys: 192 calibration / 768 test
SWEEP_MULTIPLIER = 2         # 240 journeys per sweep point, all evaluated with the main fit
NUISANCE_KEYS = ("p_scale_fault", "p_dark", "p_blur", "p_unusable", "p_glare_unflagged",
                 "p_misread_photo", "p_misread_typed")


def run_main(out: Path) -> None:
    t0 = time.time()
    bench = out / "main"
    info = simulate_benchmark(bench, SimConfig(seed=MAIN_SEED, cell_multiplier=MAIN_MULTIPLIER))
    print("benchmark", info, f"{time.time() - t0:.0f}s", flush=True)
    params = {m: study.fit_params(bench, m) for m in ("local", "global")}
    (out / "fit_params.json").write_text(json.dumps(params, indent=1, default=float))
    print("fit", {m: (p["theta"], p["visual_threshold"]) for m, p in params.items()}, f"{time.time() - t0:.0f}s", flush=True)
    for mask in ("full", "field"):
        study.evaluate(bench, params, mask=mask, which="methods", out_dir=out / "results")
        print("E1", mask, f"{time.time() - t0:.0f}s", flush=True)
    study.evaluate(bench, params, mask="full", which="ablations", out_dir=out / "results")
    print("E3 done", f"{time.time() - t0:.0f}s", flush=True)


def sweep_config(param: str, value: float, seed: int) -> SimConfig:
    base = SimConfig(seed=seed, cell_multiplier=SWEEP_MULTIPLIER)
    if param == "nuisance_scale":
        return replace(base, **{k: min(1.0, getattr(base, k) * value) for k in NUISANCE_KEYS})
    return replace(base, **{param: value})


def run_sweep(out: Path, param: str, value: float) -> None:
    seed = 5000 + zlib.crc32(f"{param}={value:g}".encode()) % 1000  # deterministic per sweep point
    tag = f"{param}={value:g}"
    bench = out / "sweeps" / tag
    simulate_benchmark(bench, sweep_config(param, value, seed))
    while not (out / "fit_params.json").exists():  # parameters come from the main calibration fit
        time.sleep(30)
    params = json.loads((out / "fit_params.json").read_text())
    res = study.evaluate(bench, params, mask="full", which="methods", out_dir=bench / "results",
                         bootstrap=0, split="all")
    res["param"], res["value"] = param, value
    (out / "sweeps" / f"{tag}.json").write_text(json.dumps(res, indent=1, default=float))
    print("sweep", tag, "done", flush=True)


if __name__ == "__main__":
    cv2.setNumThreads(1)
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["main", "sweep"])
    ap.add_argument("--out", default="results/sim")
    ap.add_argument("--param")
    ap.add_argument("--value", type=float)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    run_main(out) if a.mode == "main" else run_sweep(out, a.param, a.value)
