from __future__ import annotations

from typing import Tuple


# Normative operational policy. Stage meanings follow the protocol:
#   S1 forward transit (CP1 origin hub -> CP2 carrier facility)
#   S2 customer custody (CP2 -> CP3 doorstep / return pickup)
#   S3 reverse transit (CP3 -> CP4 return hub)
_POLICY = {
    "ATTR_CONFIRMED_LEGITIMATE": (
        "DEC_REFUND",
        "Physical integrity confirmed at every trusted checkpoint. Approve the claim.",
    ),
    "ATTR_STAGE_FORWARD_TRANSIT": (
        "DEC_INVESTIGATE_FORWARD_CARRIER",
        "Change isolated to forward transit (CP1 to CP2). Open an audit with the origin hub and forward carrier.",
    ),
    "ATTR_STAGE_CONSUMER_CUSTODY": (
        "DEC_REVIEW_CUSTOMER_CLAIM",
        "Change isolated to customer custody (CP2 to CP3). Refer to a human reviewer before any action on the claim.",
    ),
    "ATTR_STAGE_REVERSE_TRANSIT": (
        "DEC_INVESTIGATE_REVERSE_CARRIER",
        "Change isolated to reverse transit (CP3 to CP4). File a claim against the reverse carrier; do not penalise the customer.",
    ),
    "ATTR_ABSTAIN_DEGRADED": (
        "DEC_ESCALATE_MANUAL",
        "Evidence at a bounding checkpoint is degraded or missing. Escalate to a human investigator.",
    ),
    "ATTR_ABSTAIN_INDISTINGUISHABLE": (
        "DEC_ESCALATE_MANUAL",
        "Trusted evidence cannot separate the candidate stages. Escalate for manual custody reconciliation.",
    ),
}

_ALIASES = {
    "LEGITIMATE": "ATTR_CONFIRMED_LEGITIMATE",
    "STAGE(1)": "ATTR_STAGE_FORWARD_TRANSIT",
    "ATTR_STAGE(1)": "ATTR_STAGE_FORWARD_TRANSIT",
    "STAGE(2)": "ATTR_STAGE_CONSUMER_CUSTODY",
    "ATTR_STAGE(2)": "ATTR_STAGE_CONSUMER_CUSTODY",
    "STAGE(3)": "ATTR_STAGE_REVERSE_TRANSIT",
    "ATTR_STAGE(3)": "ATTR_STAGE_REVERSE_TRANSIT",
    "ABSTAIN_DEGRADED": "ATTR_ABSTAIN_DEGRADED",
    "ABSTAIN_INDISTINGUISHABLE": "ATTR_ABSTAIN_INDISTINGUISHABLE",
}


def map_attribution_to_decision(label: str, confidence: float = 1.0) -> Tuple[str, str]:
    """
    Map an attribution label to (decision_code, explanation).
    Kept separate from the attribution algorithms; accepts canonical ATTR_* labels and their short aliases.
    No decision penalises a person automatically: customer-custody findings go to human review.
    """
    lbl = label.strip()
    canonical = _ALIASES.get(lbl, lbl)
    if canonical in _POLICY:
        return _POLICY[canonical]
    return (
        "DEC_HOLD",
        f"Unrecognized attribution label '{label}'. Place journey on investigative hold.",
    )
