"""Leakage-resistant helpers for calendar-day event targets.

These functions deliberately do not train a model.  They encode the temporal
invariants required by ArcShift M01/M02 so that a later, explicitly approved
fit cannot silently treat warm-up, missing dates, or immature outcomes as
negative observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class CompositeStress:
    """A composite score and its nullable threshold event."""

    score: pd.Series
    event: pd.Series
    available: pd.Series


@dataclass(frozen=True)
class TemporalLabels:
    """A nullable label plus the metadata needed for temporal splitting."""

    target: pd.Series
    label_end: pd.Series
    mature: pd.Series
    complete_window: pd.Series


def _validated_dates(dates: pd.Series) -> pd.Series:
    converted = pd.to_datetime(dates, errors="coerce")
    if converted.isna().any():
        raise ValueError("dates must not contain null or unparseable values")
    if converted.duplicated().any():
        raise ValueError("dates must be unique")
    if not converted.is_monotonic_increasing:
        raise ValueError("dates must be strictly increasing")
    return converted


def _validated_nullable_events(event: pd.Series, index: pd.Index) -> pd.Series:
    if len(event) != len(index):
        raise ValueError("event and dates must have the same length")
    values = pd.Series(event.array, index=index, dtype="Float64")
    invalid = values.dropna().loc[lambda item: ~item.isin([0.0, 1.0])]
    if not invalid.empty:
        raise ValueError("event must contain only 0, 1, boolean, or missing values")
    return values.astype("Int64")


def build_complete_composite_stress(
    components: Mapping[str, pd.Series],
    *,
    threshold: float,
) -> CompositeStress:
    """Average mandatory components without converting warm-up to no event.

    Every supplied component is mandatory.  The score and event stay missing
    until all components are known.  Callers must version a different component
    policy instead of changing this requirement to obtain more usable rows.
    """

    if not components:
        raise ValueError("at least one mandatory stress component is required")
    component_series = list(components.values())
    reference_index = component_series[0].index
    if any(not series.index.equals(reference_index) for series in component_series[1:]):
        raise ValueError("stress components must have identical indexes")
    frame = pd.DataFrame(components, dtype="Float64")
    available = frame.notna().all(axis=1)
    score = frame.mean(axis=1, skipna=False).where(available).astype("Float64")
    event = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    event.loc[available] = (score.loc[available] >= threshold).astype("int64")
    return CompositeStress(score=score, event=event, available=available)


def build_future_event_labels(
    dates: pd.Series,
    event: pd.Series,
    *,
    horizon_days: int,
    outcomes_available_through: pd.Timestamp | str | None = None,
) -> TemporalLabels:
    """Build a target for an event in ``(origin, origin + horizon_days]``.

    The calendar is explicit: every calendar date in the future window must be
    present.  A missing date, unknown component event, or window extending past
    ``outcomes_available_through`` yields an unknown target, never a negative.
    This is intentionally stricter than the legacy row-shift implementation.
    """

    if not isinstance(horizon_days, int) or isinstance(horizon_days, bool) or horizon_days <= 0:
        raise ValueError("horizon_days must be a positive integer")

    converted_dates = _validated_dates(pd.Series(dates, index=dates.index))
    nullable_event = _validated_nullable_events(event, converted_dates.index)
    available_through = (
        converted_dates.max()
        if outcomes_available_through is None
        else pd.Timestamp(outcomes_available_through)
    )
    if pd.isna(available_through):
        raise ValueError("outcomes_available_through must be a valid timestamp")

    label_end = converted_dates + pd.to_timedelta(horizon_days, unit="D")
    mature = label_end <= available_through
    complete_window = pd.Series(False, index=converted_dates.index, dtype=bool)
    target = pd.Series(pd.NA, index=converted_dates.index, dtype="Int64")

    event_by_date = pd.Series(nullable_event.array, index=pd.DatetimeIndex(converted_dates))
    for row_index, (origin, end, is_mature) in enumerate(
        zip(converted_dates, label_end, mature, strict=True)
    ):
        if not is_mature:
            continue
        expected_dates = pd.date_range(
            start=origin + pd.Timedelta(days=1),
            end=end,
            freq="D",
        )
        window = event_by_date.reindex(expected_dates)
        if len(window) != horizon_days or window.isna().any():
            continue
        complete_window.iloc[row_index] = True
        target.iloc[row_index] = int(window.max())

    return TemporalLabels(
        target=target,
        label_end=pd.Series(label_end.array, index=converted_dates.index),
        mature=pd.Series(mature.array, index=converted_dates.index, dtype=bool),
        complete_window=complete_window,
    )


def temporal_training_mask(
    dates: pd.Series,
    target: pd.Series,
    label_end: pd.Series,
    *,
    cutoff: pd.Timestamp | str,
) -> pd.Series:
    """Select only known labels whose complete window ends before cutoff."""

    converted_dates = _validated_dates(pd.Series(dates, index=dates.index))
    converted_ends = pd.to_datetime(label_end, errors="coerce")
    if len(target) != len(converted_dates) or len(converted_ends) != len(converted_dates):
        raise ValueError("dates, target, and label_end must have the same length")
    if converted_ends.isna().any():
        raise ValueError("label_end must not contain null or unparseable values")
    if (converted_ends <= converted_dates).any():
        raise ValueError("each label_end must be after its forecast origin")
    cutoff_timestamp = pd.Timestamp(cutoff)
    if pd.isna(cutoff_timestamp):
        raise ValueError("cutoff must be a valid timestamp")
    nullable_target = _validated_nullable_events(target, converted_dates.index)
    return (
        (converted_dates < cutoff_timestamp)
        & (converted_ends < cutoff_timestamp)
        & nullable_target.notna()
    )
