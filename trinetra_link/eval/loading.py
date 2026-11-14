"""Loading of evaluation journeys for experiments E1, E2 and E3.

Experiments must run on the captured observations held in the SQLite store.
Rebuilding a journey from its staging-log row (``generate_benchmark_journey_from_staging``)
plants the ground truth in the evidence, so it is permitted only as an explicit
pipeline self-test whose outputs are watermarked as not being results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from trinetra_link.schema.models import Journey

SELF_TEST_WATERMARK = "PIPELINE SELF-TEST ON LABEL-BUILT JOURNEYS — NOT A RESULT"


class MissingCapturedJourneysError(RuntimeError):
    """Raised when test journeys have no captured observations in the store."""


def load_evaluation_journeys(
    staging_rows: List[Dict[str, Any]],
    store_path: Optional[Path | str] = None,
    allow_label_rebuild: bool = False,
) -> List[Journey]:
    """Return one captured journey per staging row, in the same order.

    Raises ``MissingCapturedJourneysError`` when any journey is absent from the
    store, unless ``allow_label_rebuild`` is set (pipeline self-tests only).
    """
    from trinetra_link.eval.e1 import generate_benchmark_journey_from_staging
    from trinetra_link.store.database import DEFAULT_DB_PATH, Store

    db_path = Path(store_path) if store_path else DEFAULT_DB_PATH
    store = Store(db_path) if db_path.exists() else None

    journeys: List[Journey] = []
    missing: List[str] = []
    for row in staging_rows:
        code = row["journey_code"]
        journey = store.get_journey(code) if store else None
        if journey is None:
            missing.append(code)
            if allow_label_rebuild:
                journey = generate_benchmark_journey_from_staging(row)
        journeys.append(journey)

    if missing and not allow_label_rebuild:
        shown = ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else "")
        raise MissingCapturedJourneysError(
            f"{len(missing)} of {len(staging_rows)} test journeys have no captured observations "
            f"in the store at {db_path} ({shown}). Capture them first; experiments never "
            f"rebuild evidence from ground-truth labels outside a pipeline self-test."
        )
    return journeys
