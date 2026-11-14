"""Regression tests for the gaps found in the November 2026 project review."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trinetra_link.baselines.b3_unlinked import predict_b3_unlinked
from trinetra_link.eval.pipeline import predict_trinetra_link
from trinetra_link.fit import fit_thresholds
from trinetra_link.quality.provenance import glare_reported, identifiers_independent_of_photos
from trinetra_link.reconcile.seals import reconcile_seal_layers
from trinetra_link.schema.models import CheckpointObservation, ImageRef, Journey, SealObservation

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _cp(k, serial="SN-1", seals=None, weights=(500.0, 500.0, 500.0), photos=True, **extra):
    images = [ImageRef(side="TOP", path=f"missing/J_{k}.jpg", sha256=f"{k:064x}", w=1280, h=720)] if photos else []
    return CheckpointObservation(
        journey_code="J-1", cp_index=k, ts_utc=T0 + timedelta(hours=k), device_id="d", operator_id="o",
        weights_g=list(weights), scale_id="S1", scale_status="OK", serial=serial, seals=seals or [],
        images=images, **extra,
    )


def test_unrecorded_seal_layer_is_unknown_not_intact():
    ref = [SealObservation(layer="L2_BOX", seal_id_read="BOX-1", state="INTACT")]
    cps = [_cp(1, seals=ref), _cp(2, seals=ref), _cp(3, seals=[]), _cp(4, seals=ref)]
    assert reconcile_seal_layers(cps, 3)["L2_BOX"] == "UNK"
    assert reconcile_seal_layers(cps, 4)["L2_BOX"] == "INTACT"


def test_no_seals_ablation_keeps_serial_and_imei_checks():
    journey = Journey(journey_code="J-1", checkpoints=[_cp(1), _cp(2), _cp(3, serial="SN-SWAP"), _cp(4, serial="SN-SWAP")])
    full = predict_trinetra_link(journey, theta=0.4).label
    no_seals = predict_trinetra_link(journey, theta=0.4, disable_seals=True).label
    assert full == "ATTR_STAGE_CONSUMER_CUSTODY"
    assert no_seals == full


def test_fit_refuses_empty_calibration_split(tmp_path):
    with pytest.raises(ValueError, match="NO CALIBRATION DATA"):
        fit_thresholds([], split_name="calibration", output_dir=tmp_path)


def test_b3_treats_missing_weights_as_no_evidence():
    cps = [_cp(1), _cp(2, weights=()), _cp(3, weights=()), _cp(4)]
    journey = Journey(journey_code="J-1", checkpoints=cps)
    assert predict_b3_unlinked(journey).label == "ATTR_CONFIRMED_LEGITIMATE"


def test_structured_provenance_fields_take_precedence_over_notes():
    noted = _cp(2, carrier_log="glare noted, serial typed manually")
    assert glare_reported(noted) and identifiers_independent_of_photos(noted)  # legacy fallback
    explicit = _cp(2, carrier_log="glare noted, serial typed manually", glare_reported=False, identifier_source="photo")
    assert not glare_reported(explicit)
    assert not identifiers_independent_of_photos(explicit)
    scanned = _cp(2, identifier_source="scanned")
    assert identifiers_independent_of_photos(scanned)
