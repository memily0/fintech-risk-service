"""Strict synthetic preparation boundary around Mila's unchanged temporal core."""

from dataclasses import dataclass
import math
from numbers import Real

import pandas as pd

from .temporal import build_complete_composite_stress, build_future_event_labels, temporal_training_mask


COMPONENTS = ("vix_zscore", "usd_rub_volatility_zscore", "imoex_volatility_zscore", "imoex_drawdown_zscore", "ofz_inversion_zscore")
TARGET_DEFINITION = "future_composite_stress_event_candidate.1"


@dataclass(frozen=True)
class PreparedValidation:
    data_snapshot_id: str
    horizon_days: int
    frame: pd.DataFrame
    target_definition_id: str = TARGET_DEFINITION
    synthetic: bool = True
    model_quality_validated: bool = False
    calendar_snapshot_id: str | None = None
    measurement_sha256: str | None = None


def calendar_date(value, name):
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is not None or timestamp != timestamp.normalize():
        raise ValueError(name + " must be a timezone-free calendar date")
    return timestamp


def prepare_validation(frame, *, data_snapshot_id, horizon_days, threshold, outcomes_available_through, synthetic):
    if synthetic is not True:
        raise ValueError("This integration accepts synthetic preparation only")
    if not isinstance(data_snapshot_id, str) or not data_snapshot_id.strip() or len(data_snapshot_id) > 256:
        raise ValueError("An explicit snapshot identity is required")
    if isinstance(threshold, bool) or not isinstance(threshold, Real) or not math.isfinite(threshold):
        raise ValueError("Threshold must be a finite number")
    if frame.empty or not frame.index.is_unique or not {"date", *COMPONENTS} <= set(frame.columns):
        raise ValueError("Require unique rows and all five standardized components")
    dates = pd.to_datetime(frame["date"], errors="raise")
    if dates.dt.tz is not None or not dates.equals(dates.dt.normalize()):
        raise ValueError("Origins must be calendar dates, not intraday timestamps")
    for name in COMPONENTS:
        if any(isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) for value in frame[name].dropna()):
            raise ValueError("Components must be finite numeric values or missing")
    as_of = calendar_date(outcomes_available_through, "outcomes_available_through")
    composite = build_complete_composite_stress({name: frame[name] for name in COMPONENTS}, threshold=threshold)
    labels = build_future_event_labels(dates, composite.event, horizon_days=horizon_days, outcomes_available_through=as_of)
    prepared = pd.DataFrame({"date": dates, "stress_score": composite.score, "stress_event": composite.event, "target": labels.target, "label_end": labels.label_end, "mature": labels.mature, "complete_window": labels.complete_window}, index=frame.index)
    return PreparedValidation(data_snapshot_id=data_snapshot_id, horizon_days=horizon_days, frame=prepared)


def training_rows(prepared, *, cutoff):
    frame = prepared.frame
    cutoff_date = calendar_date(cutoff, "cutoff")
    mask = temporal_training_mask(frame["date"], frame["target"], frame["label_end"], cutoff=cutoff_date)
    return frame.loc[mask].copy()
