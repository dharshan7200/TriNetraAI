from __future__ import annotations

from datetime import datetime, timezone
import pytest

from trinetra_link.schema.models import CheckpointObservation, SealObservation
from trinetra_link.reconcile.seals import reconcile_seal_layers, determine_breach_depth


def make_checkpoint(
    cp_index: int,
    seals: list[SealObservation],
    carrier_log: str | None = None,
) -> CheckpointObservation:
    """Helper fixture to create a valid CheckpointObservation for seal testing."""
    return CheckpointObservation(
        journey_code="JRN-SEAL-TEST-001",
        cp_index=cp_index,
        ts_utc=datetime.now(timezone.utc),
        device_id="DEV-001",
        operator_id="OP-001",
        scale_id="SCALE-001",
        scale_status="OK",
        weights_g=[500.0, 500.0, 500.0],
        seals=seals,
        carrier_log=carrier_log,
    )


def test_torn_l2_yields_box_entered():
    """CP2 has L2 state='TORN', L3 intact -> determine_breach_depth returns 'box_entered'."""
    cp1 = make_checkpoint(
        cp_index=1,
        seals=[
            SealObservation(layer="L1_FWD", seal_id_read="SEAL-L1-001", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-L2-001", state="INTACT"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-L3-001", state="INTACT"),
        ],
    )
    cp2 = make_checkpoint(
        cp_index=2,
        seals=[
            SealObservation(layer="L1_FWD", seal_id_read="SEAL-L1-001", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-L2-001", state="TORN"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-L3-001", state="INTACT"),
        ],
    )

    reconciled = reconcile_seal_layers([cp1, cp2], target_cp_index=2)
    assert reconciled["L1_FWD"] == "INTACT"
    assert reconciled["L2_BOX"] == "ANOM"
    assert reconciled["L3_ITEM"] == "INTACT"

    depth = determine_breach_depth([cp1, cp2])
    assert depth == "box_entered"


def test_all_ids_changed_yields_full_substitution():
    """CP2 has L1, L2, L3 all with altered seal IDs -> determine_breach_depth returns 'full_substitution'."""
    cp1 = make_checkpoint(
        cp_index=1,
        seals=[
            SealObservation(layer="L1_FWD", seal_id_read="SEAL-L1-ORIG", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-L2-ORIG", state="INTACT"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-L3-ORIG", state="INTACT"),
        ],
    )
    cp2 = make_checkpoint(
        cp_index=2,
        seals=[
            SealObservation(layer="L1_FWD", seal_id_read="SEAL-L1-DECOY", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-L2-DECOY", state="INTACT"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-L3-DECOY", state="INTACT"),
        ],
    )

    reconciled = reconcile_seal_layers([cp1, cp2], target_cp_index=2)
    assert reconciled["L1_FWD"] == "ANOM"
    assert reconciled["L2_BOX"] == "ANOM"
    assert reconciled["L3_ITEM"] == "ANOM"

    depth = determine_breach_depth([cp1, cp2])
    assert depth == "full_substitution"


def test_flyer_replaced_logged_note_not_anomalous():
    """CP2 has carrier_log='flyer replaced at hub, new seal SEAL-NEW', L1 has ID SEAL-NEW -> L1_FWD is INTACT."""
    cp1 = make_checkpoint(
        cp_index=1,
        seals=[
            SealObservation(layer="L1_FWD", seal_id_read="SEAL-L1-ORIG", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-L2-ORIG", state="INTACT"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-L3-ORIG", state="INTACT"),
        ],
    )
    cp2 = make_checkpoint(
        cp_index=2,
        seals=[
            SealObservation(layer="L1_FWD", seal_id_read="SEAL-NEW-999", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-L2-ORIG", state="INTACT"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-L3-ORIG", state="INTACT"),
        ],
        carrier_log="flyer replaced at hub, new seal SEAL-NEW-999",
    )

    reconciled = reconcile_seal_layers([cp1, cp2], target_cp_index=2)
    assert reconciled["L1_FWD"] == "INTACT"
    assert reconciled["L2_BOX"] == "INTACT"
    assert reconciled["L3_ITEM"] == "INTACT"

    depth = determine_breach_depth([cp1, cp2])
    assert depth == "none"


def test_dark_photo_unreadable_yields_unk():
    """CP2 has seal with state='UNREADABLE' -> reconcile_seal_layers returns 'UNK', not 'ANOM'."""
    cp1 = make_checkpoint(
        cp_index=1,
        seals=[
            SealObservation(layer="L1_FWD", seal_id_read="SEAL-L1-001", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-L2-001", state="INTACT"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-L3-001", state="INTACT"),
        ],
    )
    cp2 = make_checkpoint(
        cp_index=2,
        seals=[
            SealObservation(layer="L1_FWD", seal_id_read="SEAL-L1-001", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read=None, state="UNREADABLE"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-L3-001", state="INTACT"),
        ],
    )

    reconciled = reconcile_seal_layers([cp1, cp2], target_cp_index=2)
    assert reconciled["L2_BOX"] == "UNK"
    assert reconciled["L2_BOX"] != "ANOM"
    assert reconciled["L1_FWD"] == "INTACT"
    assert reconciled["L3_ITEM"] == "INTACT"


def test_l1_ret_reconciliation_at_cp4():
    """CP4 reconciles L1_RET against CP3 reference."""
    cp1 = make_checkpoint(
        cp_index=1,
        seals=[
            SealObservation(layer="L1_FWD", seal_id_read="SEAL-FWD-1", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-BOX-1", state="INTACT"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-ITEM-1", state="INTACT"),
        ],
    )
    cp3 = make_checkpoint(
        cp_index=3,
        seals=[
            SealObservation(layer="L1_RET", seal_id_read="SEAL-RET-ORIG", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-BOX-1", state="INTACT"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-ITEM-1", state="INTACT"),
        ],
    )
    cp4_tampered = make_checkpoint(
        cp_index=4,
        seals=[
            SealObservation(layer="L1_RET", seal_id_read="SEAL-RET-DIFFERENT", state="INTACT"),
            SealObservation(layer="L2_BOX", seal_id_read="SEAL-BOX-1", state="INTACT"),
            SealObservation(layer="L3_ITEM", seal_id_read="SEAL-ITEM-1", state="INTACT"),
        ],
    )

    reconciled = reconcile_seal_layers([cp1, cp3, cp4_tampered], target_cp_index=4)
    assert reconciled["L1_RET"] == "ANOM"
    assert reconciled["L2_BOX"] == "INTACT"

    depth = determine_breach_depth([cp1, cp3, cp4_tampered])
    assert depth == "L1_only"
