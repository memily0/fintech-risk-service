"""Synthetic-only operationalization of the new-onset business task.

The imported future-presence target is kept intact. Restricting origins to
known non-stress dates makes its future event a new threshold episode, rather
than continuation of an episode already active at the forecast origin.
"""

from dataclasses import replace

import pandas as pd

from arcshift_v1.task_definition import PRIMARY_HORIZON_DAYS
from .product import prepare_validation


LEGACY_ONSET_TARGET = "composite_stress_onset_candidate.1"


def prepare_onset_validation(frame, *, data_snapshot_id, threshold, outcomes_available_through, synthetic):
    prepared = prepare_validation(
        frame, data_snapshot_id=data_snapshot_id, horizon_days=PRIMARY_HORIZON_DAYS,
        threshold=threshold, outcomes_available_through=outcomes_available_through,
        synthetic=synthetic,
    )
    result = prepared.frame.copy()
    current_known = result.stress_event.notna()
    eligible = result.stress_event.eq(0).fillna(False)
    state = pd.Series("current_state_unknown", index=result.index, dtype="string")
    state.loc[current_known & ~eligible] = "already_in_stress"
    state.loc[eligible] = "at_risk"
    result["onset_origin_state"] = state
    result["onset_risk_set"] = eligible.astype(bool)
    result["target"] = result.target.where(eligible).astype("Int64")
    return replace(prepared, frame=result, target_definition_id=LEGACY_ONSET_TARGET)
