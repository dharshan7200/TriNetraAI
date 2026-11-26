from __future__ import annotations

from trinetra_link.attribution.policy import map_attribution_to_decision
from trinetra_link.attribution.rationale import generate_attribution_rationale


def test_policy_mapping():
    assert map_attribution_to_decision("LEGITIMATE")[0] == "DEC_REFUND"
    assert map_attribution_to_decision("STAGE(1)")[0] == "DEC_INVESTIGATE_FORWARD_CARRIER"
    assert map_attribution_to_decision("STAGE(2)")[0] == "DEC_REVIEW_CUSTOMER_CLAIM"
    assert map_attribution_to_decision("STAGE(3)")[0] == "DEC_INVESTIGATE_REVERSE_CARRIER"
    assert map_attribution_to_decision("ABSTAIN_DEGRADED")[0] == "DEC_ESCALATE_MANUAL"
    assert map_attribution_to_decision("ABSTAIN_INDISTINGUISHABLE")[0] == "DEC_ESCALATE_MANUAL"


def test_policy_accepts_the_labels_the_method_emits():
    """Every canonical label produced by Algorithm 1 and the Bayesian rule maps to a real decision, never DEC_HOLD."""
    expected = {
        "ATTR_CONFIRMED_LEGITIMATE": "DEC_REFUND",
        "ATTR_STAGE_FORWARD_TRANSIT": "DEC_INVESTIGATE_FORWARD_CARRIER",
        "ATTR_STAGE_CONSUMER_CUSTODY": "DEC_REVIEW_CUSTOMER_CLAIM",
        "ATTR_STAGE_REVERSE_TRANSIT": "DEC_INVESTIGATE_REVERSE_CARRIER",
        "ATTR_ABSTAIN_DEGRADED": "DEC_ESCALATE_MANUAL",
        "ATTR_ABSTAIN_INDISTINGUISHABLE": "DEC_ESCALATE_MANUAL",
    }
    for label, decision in expected.items():
        assert map_attribution_to_decision(label)[0] == decision
    assert map_attribution_to_decision("SOMETHING_ELSE")[0] == "DEC_HOLD"


def test_rationale_generation():
    text = generate_attribution_rationale(
        journey_code="JRN-RAT-01",
        label="STAGE(2)",
        interval=[2, 3],
        trusted_set=[1, 2, 3, 4],
        per_modality_evidence={
            "q_k": {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0},
            "z_k": {1: "INTACT", 2: "INTACT", 3: "ANOM", 4: "ANOM"},
        },
        decision="DEC_INVESTIGATE_CARRIER",
    )
    assert "JRN-RAT-01" in text
    assert "STAGE(2)" in text
    assert "DEC_INVESTIGATE_CARRIER" in text
    assert "CP2 -> CP3" in text
