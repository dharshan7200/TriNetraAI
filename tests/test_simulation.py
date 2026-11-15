"""Tests for the simulation study components and the visual / reference-trust changes."""

from __future__ import annotations

import random

import numpy as np

from trinetra_link.reconcile.visual import compute_local_change_score
from trinetra_link.sim import simulator as sm
from trinetra_link.staging.determinability import derive_ground_truth


def _face(side: str, seed: int, strength: float = 0.0, glare: bool = False, rng_seed: int = 0):
    rng = np.random.default_rng(rng_seed)
    base = sm._base_scene(side, "B12AB342", "SN1", rng)
    base = np.clip(base + sm._surface_texture(base.shape, seed), 0, 255).astype(np.uint8)
    if strength:
        base = sm._apply_marks(base, side, strength, 0.0, rng)
    return sm._capture(base, sm.SimConfig(), rng, dark=False, blur=False, glare=glare)


def test_local_score_ignores_pose_change_and_flags_tamper():
    a = _face("TOP", 1, rng_seed=1)
    b = _face("TOP", 1, rng_seed=2)            # same parcel, new pose and exposure
    c = _face("TOP", 1, strength=0.6, rng_seed=3)
    assert compute_local_change_score(a, b) < 0.04
    assert compute_local_change_score(a, c) > 0.10


def test_local_score_masks_glare_that_appears_in_one_capture():
    a = _face("SEAL", 4, rng_seed=1)
    g = _face("SEAL", 4, glare=True, rng_seed=5)
    assert compute_local_change_score(a, g) < 0.05


def test_nuisance_degradation_changes_truth_only_at_bounding_checkpoints():
    cfg = sm.SimConfig()
    plan = sm._plan_journey("SIM-T-1", "customer_tamper", cfg, random.Random(0))
    plan["unusable_cps"] = [4]                 # S2 is bounded by CP1, CP2, CP3: CP4 does not matter
    assert derive_ground_truth(sm._staging_row(plan))[0] == "OBS_DETERMINABLE"
    plan["unusable_cps"] = [3]
    assert derive_ground_truth(sm._staging_row(plan))[0] == "OBS_DEGRADED_INCOMPLETE"


def test_single_modality_faults_never_change_truth():
    cfg = sm.SimConfig()
    plan = sm._plan_journey("SIM-T-2", "reverse_transit_tamper", cfg, random.Random(1))
    plan.update(unusable_cps=[], scale_fault_cps=[3, 4], dark_cps=[4], blur_cps=[3], unflagged_glare_cps=[4])
    omega, label, _ = derive_ground_truth(sm._staging_row(plan))
    assert (omega, label) == ("OBS_DETERMINABLE", "ATTR_STAGE_REVERSE_TRANSIT")


def test_mass_change_never_exceeds_item_mass():
    cfg = sm.SimConfig(p_weight_matched=0.0, p_small_mass=0.0)
    rng = random.Random(3)
    for i in range(200):
        plan = sm._plan_journey(f"SIM-T-{i}", "customer_tamper", cfg, rng)
        assert plan["mass_change_g"] <= 0.9 * plan["item"][1] + 1e-9


def test_generated_manifests_are_refused_without_explicit_permission(tmp_path):
    import json

    import pytest

    from trinetra_link.eval.e2 import evaluate_e2
    from trinetra_link.eval.e3 import evaluate_e3
    from trinetra_link.eval.loading import manifest_is_synthetic

    assert manifest_is_synthetic({"test_journey_codes": ["PLACEHOLDER-120-00001"]})
    assert manifest_is_synthetic({"placeholder": True})
    assert not manifest_is_synthetic({"test_journey_codes": ["JRN-2026-0001"]})

    manifest = tmp_path / "split_manifest.json"
    manifest.write_text(json.dumps({"placeholder": True, "test_journey_codes": ["PLACEHOLDER-1-00001"]}))
    for fn in (evaluate_e2, evaluate_e3):
        with pytest.raises(RuntimeError, match="allow-synthetic-dry-run"):
            fn(split_manifest_path=manifest, output_dir=tmp_path / fn.__name__)
