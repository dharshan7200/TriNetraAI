"""
TriNetra-Link comparison baselines B1, B2, B3 and B5.

B4 (a language-model judge) was dropped from the project; see docs/decisions.md.
"""
from trinetra_link.baselines.b1_cp4 import predict_b1_cp4
from trinetra_link.baselines.b2_endpoints import predict_b2_endpoints
from trinetra_link.baselines.b3_unlinked import predict_b3_unlinked
from trinetra_link.baselines.b5_v3_rules import predict_b5_v3_rules

__all__ = [
    "predict_b1_cp4",
    "predict_b2_endpoints",
    "predict_b3_unlinked",
    "predict_b5_v3_rules",
]
