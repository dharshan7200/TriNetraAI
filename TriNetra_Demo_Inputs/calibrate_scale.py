"""Set a scale's noise (sigma) in a journey folder's scales.json from repeated readings of one object.

Usage:
    python TriNetra_Demo_Inputs/calibrate_scale.py Real_Inputs/JRN-2026-BOXA KITCHEN-SCALE-01 502 501 502 502 501 502 503 502 501 502

Weigh one fixed object (e.g. a water bottle) 10 times, lifting it off between readings, and pass the readings.
sigma = standard deviation of the readings, but at least half the scale's display step (0.5 g for a 1 g scale),
because a scale that shows the same number every time still rounds. delta (drift) = half the display step.
"""
import json
import statistics
import sys
from pathlib import Path

if len(sys.argv) < 6:
    print(__doc__)
    sys.exit(1)
folder, scale_id = Path(sys.argv[1]), sys.argv[2]
readings = [float(x) for x in sys.argv[3:]]
step = min((abs(a - b) for a in readings for b in readings if a != b), default=1.0)
sigma = max(statistics.stdev(readings), step / 2)
delta = step / 2
p = folder / "scales.json"
data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"scales": {}}
data.setdefault("scales", {})[scale_id] = {"scale_id": scale_id, "sigma_g": round(sigma, 3), "delta_g": round(delta, 3),
                                          "calibration_readings_g": readings}
data["calibrated"] = True
p.write_text(json.dumps(data, indent=2), encoding="utf-8")
z = 3.0
thr = z * (2 * sigma ** 2) ** 0.5 + 2 * delta
print(f"{scale_id}: sigma = {sigma:.3f} g, delta = {delta:.3f} g -> weight changes above {thr:.1f} g count as real")
