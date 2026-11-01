from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from trinetra_link.schema.models import CheckpointObservation, SealObservation


def reconcile_seal_layers(
    checkpoints: Sequence[CheckpointObservation], target_cp_index: int
) -> Dict[str, str]:
    """
    Reconciles layered tamper-evident seals for a given checkpoint against references.
    
    Returns {layer_name: "INTACT" | "ANOM" | "UNK"} for each of:
    - L1_FWD: Forward courier flyer seal
    - L1_RET: Return courier flyer seal
    - L2_BOX: Box opening tamper sticker
    - L3_ITEM: Numbered item tag / tie
    
    Rules:
      - L1_FWD: check seal_id_read at CP2 against l1_fwd_seal recorded at CP1
                UNLESS carrier_log at CP2 contains "flyer replaced ... new seal <ID>"
                and the new ID matches — then NOT anomalous.
      - L2_BOX, L3_ITEM: check at every checkpoint CP2–CP4 against CP1 recorded IDs.
      - L1_RET: check at CP4 against l1_ret_seal recorded at CP3.
      - TORN or MISSING state → ANOM
      - seal_id_read differs from reference ID → ANOM
      - UNREADABLE → UNK (never INTACT)
    """
    result: Dict[str, str] = {
        "L1_FWD": "INTACT",
        "L1_RET": "INTACT",
        "L2_BOX": "INTACT",
        "L3_ITEM": "INTACT",
    }

    cp_by_idx = {cp.cp_index: cp for cp in checkpoints}
    target_cp = cp_by_idx.get(target_cp_index)
    if not target_cp:
        return {k: "UNK" for k in result}

    cp1 = cp_by_idx.get(1)
    cp3 = cp_by_idx.get(3)

    # Reference IDs from CP1
    ref_l1_fwd: Optional[str] = None
    ref_l2_box: Optional[str] = None
    ref_l3_item: Optional[str] = None
    if cp1 and cp1.seals:
        for s in cp1.seals:
            if s.layer == "L1_FWD" and s.seal_id_read:
                ref_l1_fwd = s.seal_id_read
            elif s.layer == "L2_BOX" and s.seal_id_read:
                ref_l2_box = s.seal_id_read
            elif s.layer == "L3_ITEM" and s.seal_id_read:
                ref_l3_item = s.seal_id_read

    # Reference ID from CP3
    ref_l1_ret: Optional[str] = None
    if cp3 and cp3.seals:
        for s in cp3.seals:
            if s.layer == "L1_RET" and s.seal_id_read:
                ref_l1_ret = s.seal_id_read

    obs_by_layer = {s.layer: s for s in target_cp.seals}

    # Evaluate L1_FWD
    if "L1_FWD" in obs_by_layer:
        obs = obs_by_layer["L1_FWD"]
        if obs.state == "UNREADABLE":
            result["L1_FWD"] = "UNK"
        elif obs.state in ("TORN", "MISSING"):
            result["L1_FWD"] = "ANOM"
        elif target_cp_index == 2:
            carrier_log = target_cp.carrier_log or ""
            # Check for logged flyer replacement note
            # e.g. "flyer replaced at hub, new seal <ID>" or "flyer replaced ... new seal <ID>"
            match = re.search(r"flyer replaced.*?new seal\s+([A-Za-z0-9_\-]+)", carrier_log, re.IGNORECASE)
            if match and obs.seal_id_read and obs.seal_id_read.strip() == match.group(1).strip():
                result["L1_FWD"] = "INTACT"
            elif ref_l1_fwd and obs.seal_id_read:
                if obs.seal_id_read.strip() == ref_l1_fwd.strip():
                    result["L1_FWD"] = "INTACT"
                else:
                    result["L1_FWD"] = "ANOM"
            elif not ref_l1_fwd:
                result["L1_FWD"] = "INTACT"
            else:
                result["L1_FWD"] = "ANOM"
        else:
            result["L1_FWD"] = "INTACT"

    # Evaluate L1_RET
    if "L1_RET" in obs_by_layer:
        obs = obs_by_layer["L1_RET"]
        if obs.state == "UNREADABLE":
            result["L1_RET"] = "UNK"
        elif obs.state in ("TORN", "MISSING"):
            result["L1_RET"] = "ANOM"
        elif target_cp_index == 4:
            if ref_l1_ret and obs.seal_id_read:
                if obs.seal_id_read.strip() == ref_l1_ret.strip():
                    result["L1_RET"] = "INTACT"
                else:
                    result["L1_RET"] = "ANOM"
            elif not ref_l1_ret:
                result["L1_RET"] = "INTACT"
            else:
                result["L1_RET"] = "ANOM"
        else:
            result["L1_RET"] = "INTACT"

    # Evaluate L2_BOX
    if "L2_BOX" in obs_by_layer:
        obs = obs_by_layer["L2_BOX"]
        if obs.state == "UNREADABLE":
            result["L2_BOX"] = "UNK"
        elif obs.state in ("TORN", "MISSING"):
            result["L2_BOX"] = "ANOM"
        elif target_cp_index in (2, 3, 4):
            if ref_l2_box and obs.seal_id_read:
                if obs.seal_id_read.strip() == ref_l2_box.strip():
                    result["L2_BOX"] = "INTACT"
                else:
                    result["L2_BOX"] = "ANOM"
            elif not ref_l2_box:
                result["L2_BOX"] = "INTACT"
            else:
                result["L2_BOX"] = "ANOM"
        else:
            result["L2_BOX"] = "INTACT"

    # Evaluate L3_ITEM
    if "L3_ITEM" in obs_by_layer:
        obs = obs_by_layer["L3_ITEM"]
        if obs.state == "UNREADABLE":
            result["L3_ITEM"] = "UNK"
        elif obs.state in ("TORN", "MISSING"):
            result["L3_ITEM"] = "ANOM"
        elif target_cp_index in (2, 3, 4):
            if ref_l3_item and obs.seal_id_read:
                if obs.seal_id_read.strip() == ref_l3_item.strip():
                    result["L3_ITEM"] = "INTACT"
                else:
                    result["L3_ITEM"] = "ANOM"
            elif not ref_l3_item:
                result["L3_ITEM"] = "INTACT"
            else:
                result["L3_ITEM"] = "ANOM"
        else:
            result["L3_ITEM"] = "INTACT"

    return result


def determine_breach_depth(checkpoints: Sequence[CheckpointObservation]) -> str:
    """
    Determines physical breach depth across all checkpoints in a journey.
    
    Returns one of:
      - "none": No layer breached or anomalous.
      - "L1_only": Only courier flyer seal breached (L2 box and L3 item intact).
      - "box_entered": Box opened/damaged (L2 or L3 breached, but not full replacement of all layers).
      - "full_substitution": All layers breached / replaced with decoy or different IDs.
    """
    anom_layers = set()
    all_observed_changed = False

    for cp in checkpoints:
        if cp.cp_index >= 2:
            res = reconcile_seal_layers(checkpoints, cp.cp_index)
            for layer, state in res.items():
                if state == "ANOM":
                    anom_layers.add(layer)
            
            # Check if all seals observed at this checkpoint are anomalous
            observed_layers = [s.layer for s in cp.seals]
            if observed_layers and all(res.get(ly) == "ANOM" for ly in observed_layers):
                if len(observed_layers) >= 2:
                    all_observed_changed = True

    l1_anom = ("L1_FWD" in anom_layers) or ("L1_RET" in anom_layers)
    l2_anom = "L2_BOX" in anom_layers
    l3_anom = "L3_ITEM" in anom_layers

    if (l1_anom and l2_anom and l3_anom) or all_observed_changed:
        return "full_substitution"
    if l2_anom or l3_anom:
        return "box_entered"
    if l1_anom:
        return "L1_only"
    return "none"
