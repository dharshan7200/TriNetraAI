"""Structured evidence-provenance flags for a checkpoint observation.

The capture schema records how identifiers were obtained (``identifier_source``) and whether the
operator reported glare (``glare_reported``). Records created before these fields existed fall back
to keywords in the free-text carrier note, which is the only place older captures recorded them.
"""

from __future__ import annotations

from trinetra_link.schema.models import CheckpointObservation


def glare_reported(observation: CheckpointObservation) -> bool:
    """True when the operator reported glare over a defect or seal at this checkpoint."""
    if observation.glare_reported is not None:
        return bool(observation.glare_reported)
    return "glare" in (observation.carrier_log or "").lower()


def identifiers_independent_of_photos(observation: CheckpointObservation) -> bool:
    """True when seal QR, serial and IMEI were scanned or typed rather than read off a photo."""
    if observation.identifier_source is not None:
        return observation.identifier_source.strip().lower() in ("scanned", "typed")
    return "manual" in (observation.carrier_log or "").lower()
