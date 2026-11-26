"""Run one TriNetra-Link demo input through the real pipeline and print the verdict.

Usage (from the TriNetraAI project folder, virtual environment active):
    python TriNetra_Demo_Inputs/run_demo_input.py TriNetra_Demo_Inputs/input1_Legitimate
    python TriNetra_Demo_Inputs/run_demo_input.py TriNetra_Demo_Inputs --all

Uses the parameters fitted in the simulation study: theta = 0.70, local visual score with
gamma = 0.06, weight test z = 3. Writes output.json into the input folder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from trinetra_link.attribution.policy import map_attribution_to_decision
from trinetra_link.eval.pipeline import predict_trinetra_link
from trinetra_link.quality.gate import QualityGate
from trinetra_link.schema.models import CheckpointObservation, Journey

THETA, GAMMA, Z = 0.70, 0.06, 3.0
FRIENDLY = {
    "ATTR_CONFIRMED_LEGITIMATE": "LEGITIMATE - nothing changed, approve the refund",
    "ATTR_STAGE_FORWARD_TRANSIT": "FAULT: STAGE S1 - delivery courier (CP1 -> CP2)",
    "ATTR_STAGE_CONSUMER_CUSTODY": "FAULT: STAGE S2 - customer custody (CP2 -> CP3)",
    "ATTR_STAGE_REVERSE_TRANSIT": "FAULT: STAGE S3 - return courier (CP3 -> CP4)",
    "ATTR_ABSTAIN_DEGRADED": "ABSTAIN (DEGRADED) - evidence too poor to decide, manual review",
    "ATTR_ABSTAIN_INDISTINGUISHABLE": "ABSTAIN (INDISTINGUISHABLE) - evidence cannot separate the stages",
}


def load(folder: Path) -> Journey:
    data = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
    cps = []
    for c in data["checkpoints"]:
        c = {k: v for k, v in c.items() if k in CheckpointObservation.model_fields}
        for im in c["images"]:
            im["path"] = str((folder / im["path"]).resolve())
        cps.append(CheckpointObservation(**c))
    return Journey(journey_code=data["journey_code"], checkpoints=cps,
                   metadata={"synthetic": True, "product": data.get("product", "")})


def run(folder: Path) -> bool:
    folder = folder.resolve()
    meta = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
    journey = load(folder)
    scales_path = folder / "scales.json"
    scales_cfg = json.loads(scales_path.read_text(encoding="utf-8"))
    attr = predict_trinetra_link(journey, mode="algorithm1", theta=THETA, z_weight=Z,
                                 visual_threshold=GAMMA, visual_method="local",
                                 scales_config=scales_cfg, scales_path=scales_path)
    gate = QualityGate(config={"scale": {"scales": scales_cfg["scales"], "sigma_g": 1.0}}, theta=THETA)

    print("=" * 78)
    print(f" {folder.name}   |   product: {meta.get('product')}   |   journey: {journey.journey_code}")
    print("=" * 78)
    ev = attr.per_modality_evidence or {}
    qk, zk = ev.get("q_k", {}), ev.get("z_k", {})
    mods = ev.get("modality_evidence", {})
    print(f" {'Checkpoint':34s} {'weight (median)':>15s} {'trust q':>8s}  state")
    for c in journey.checkpoints:
        k = c.cp_index
        w = sorted(c.weights_g)[1] if len(c.weights_g) == 3 else None
        q = qk.get(k, qk.get(str(k)))
        if q is None:
            q = gate.evaluate(c).q_k
        z = zk.get(k, zk.get(str(k), "-"))
        name = meta["checkpoints"][k - 1].get("checkpoint_name", f"CP{k}")
        wtxt = f"{w:.2f} g" if w is not None else "scale ERROR"
        flag = "trusted" if q >= THETA else "UNTRUSTED"
        if k > 1 and qk.get(1, qk.get("1", 1.0)) < THETA:
            flag = "cannot compare: no trusted CP1 reference"
        print(f" {name:34s} {wtxt:>15s} {q:8.2f}  {('reference' if k == 1 else z):9s} ({flag})")
        m = mods.get(k, mods.get(str(k)))
        if m:
            parts = [f"{key}={val[0]}" for key, val in m.items() if not key.startswith("seal_L")]
            print(f" {'':34s}   evidence: {', '.join(parts)}")
    decision = map_attribution_to_decision(attr.label)
    print("-" * 78)
    print(f" OUTPUT    : {attr.label}")
    print(f"             {FRIENDLY.get(attr.label, '')}")
    print(f" REASON    : {attr.rationale_text}")
    print(f" DECISION  : {decision[0]} - {decision[1]}")

    expected_path = folder / "expected_output.json"
    ok = True
    if expected_path.exists():
        exp = json.loads(expected_path.read_text(encoding="utf-8"))["label"]
        ok = exp == attr.label
        print(f" EXPECTED  : {exp}   ->   {'MATCH' if ok else 'MISMATCH'}")
    simulated = "SIMULATED" in meta
    print(" (simulated demo input - not a real parcel)" if simulated else " (captured input)")
    print()
    out = {"journey_code": journey.journey_code, "product": meta.get("product"), "label": attr.label,
           "meaning": FRIENDLY.get(attr.label, ""), "rationale": attr.rationale_text,
           "interval": attr.interval, "trusted_set": attr.trusted_set,
           "q_k": {str(k): v for k, v in qk.items()}, "z_k": {str(k): v for k, v in zk.items()},
           "decision": decision[0], "simulated": simulated}
    (folder / "output.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    target = Path(sys.argv[1])
    if "--all" in sys.argv:
        folders = sorted(p for p in target.iterdir() if (p / "journey.json").exists())
        results = [run(f) for f in folders]
        print(f"{sum(results)}/{len(results)} demo inputs gave the expected output")
        sys.exit(0 if all(results) else 1)
    sys.exit(0 if run(target) else 1)
