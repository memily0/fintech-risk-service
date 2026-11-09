"""Offline synthetic implementation of the frozen domestic stress measurement.

Each native value is fixed by its own next-day cutoff. Later receipts/revisions
cannot repair history. Explicit calendars distinguish holidays from outages;
no provider is contacted and no model is trained or loaded.
"""

from dataclasses import dataclass
import math
from numbers import Real

import numpy as np
import pandas as pd

from arcshift_v1.stress_definition import MEASUREMENT_SHA256, STRESS_DEFINITION as POLICY
from .product import PreparedValidation
from .temporal import build_future_event_labels


@dataclass(frozen=True)
class MeasuredStress:
    data_snapshot_id: str
    calendar_snapshot_id: str
    frame: pd.DataFrame
    native_frames: dict[str, pd.DataFrame]
    measurement_id: str = POLICY.measurement_id
    measurement_sha256: str = MEASUREMENT_SHA256
    synthetic: bool = True
    empirical_validity_established: bool = False


def _identity(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(name + " must be an explicit snapshot identity")


def _aware(value, name):
    result = pd.Timestamp(value)
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError(name + " must include a timezone")
    return result.tz_convert("UTC")


def _dates(values, name):
    result = pd.to_datetime(values, errors="raise")
    if result.isna().any() or result.dt.tz is not None or not result.equals(result.dt.normalize()):
        raise ValueError(name + " must contain timezone-free calendar dates")
    return result


def _cutoffs(dates):
    local_clock = pd.DatetimeIndex(dates) + pd.Timedelta(hours=POLICY.cutoff_hour)
    return local_clock.tz_localize(POLICY.timezone).tz_convert("UTC")


def prior_midrank(values):
    """Current value is never included in its own reference distribution."""
    array = np.asarray(values, dtype=float)
    result = np.full(len(array), np.nan)
    for position, value in enumerate(array):
        history = array[max(0, position - POLICY.rank_window):position]
        history = history[np.isfinite(history)]
        if np.isfinite(value) and len(history) >= POLICY.rank_min_history:
            result[position] = (np.count_nonzero(history < value) + .5 * np.count_nonzero(history == value)) / len(history)
    return pd.Series(result, index=values.index, dtype="Float64")


def domestic_event(segments):
    """Require all three known, with at least two above the fixed threshold."""
    if tuple(segments.columns) != POLICY.mandatory_segments:
        raise ValueError("Require exactly fx, equity and rates in contract order")
    for column in segments:
        if any(isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) for value in segments[column].dropna()):
            raise ValueError("Segment ranks must be finite numbers or missing")
    if ((segments < 0) | (segments > 1)).any().any():
        raise ValueError("Segment ranks must be within [0, 1]")
    available = segments.notna().all(axis=1)
    intensity = segments.mean(axis=1, skipna=False).where(available).astype("Float64")
    event = pd.Series(pd.NA, index=segments.index, dtype="Int64")
    event.loc[available] = (segments.loc[available].ge(POLICY.segment_threshold).sum(axis=1) >= POLICY.required_segments).astype(int)
    return intensity, event


def measure_stress(observations, calendar, *, data_snapshot_id, calendar_snapshot_id, available_through, synthetic):
    if synthetic is not True:
        raise ValueError("Only synthetic inputs are accepted before source admission")
    _identity(data_snapshot_id, "data_snapshot_id")
    _identity(calendar_snapshot_id, "calendar_snapshot_id")
    as_of = _aware(available_through, "available_through")
    required = {"date", "known_at", *[item.market for item in POLICY.inputs]}
    if calendar.empty or not required <= set(calendar.columns):
        raise ValueError("An explicit complete provider calendar is required")
    cal = calendar.copy().reset_index(drop=True)
    cal["date"] = _dates(cal.date, "calendar dates")
    dates = pd.DatetimeIndex(cal.date)
    if not dates.equals(pd.date_range(dates.min(), dates.max(), freq="D")):
        raise ValueError("Calendar must be unique sorted and contain every calendar date")
    known_at = pd.DatetimeIndex([_aware(value, "calendar known_at") for value in cal.known_at])
    native_deadlines = _cutoffs(dates + pd.Timedelta(days=1))
    calendar_known = (known_at <= native_deadlines) & (native_deadlines <= as_of)
    for item in POLICY.inputs:
        if not cal[item.market].isin(POLICY.calendar_states).all():
            raise ValueError("Unknown provider calendar state")
        cal.loc[~calendar_known, item.market] = "unknown"

    required = {"date", "series_id", "resource_id", "units", "value", "received_at", "published_at", "receipt_sha256", "quality", "is_synthetic"}
    if not required <= set(observations.columns):
        raise ValueError("Normalized observations need explicit identity, units, receipt and publication metadata")
    native_frames = {}
    origins = dates + pd.Timedelta(days=1)
    result = pd.DataFrame({"date": origins, "forecast_cutoff": _cutoffs(origins)})
    for item in POLICY.inputs:
        rows = observations.loc[observations.series_id == item.series_id].copy()
        if any(value is not True for value in rows.is_synthetic):
            raise ValueError("Every input row must explicitly be synthetic")
        if not rows.resource_id.eq(item.resource_id).all() or not rows.units.eq(item.units).all():
            raise ValueError("Exact resource and unit binding required")
        rows["date"] = _dates(rows.date, "observation dates")
        if not rows.date.isin(dates).all():
            raise ValueError("Observations outside the supplied calendar are not allowed")
        if not rows.quality.isin(("observed", "missing", "rejected")).all():
            raise ValueError("Unknown observation quality")
        for row in rows.itertuples():
            if not isinstance(row.receipt_sha256, str) or len(row.receipt_sha256) != 64 or any(c not in "0123456789abcdef" for c in row.receipt_sha256):
                raise ValueError("A receipt SHA-256 is required")
            if row.quality == "observed":
                if isinstance(row.value, bool) or not isinstance(row.value, Real) or not math.isfinite(row.value):
                    raise ValueError("Observed values must be finite numbers")
                if item.market in ("fx", "equity") and row.value <= 0:
                    raise ValueError("Price and FX levels must be strictly positive")
            elif not pd.isna(row.value):
                raise ValueError("Missing or rejected values must be null")
        rows["received_at"] = pd.to_datetime([_aware(value, "received_at") for value in rows.received_at], utc=True)
        rows["published_at"] = pd.to_datetime([_aware(value, "published_at") if not pd.isna(value) else None for value in rows.published_at], utc=True)
        if (rows.published_at > rows.received_at).any():
            raise ValueError("Publication cannot follow receipt of a published observation")
        if rows.duplicated(["date", "received_at"]).any():
            raise ValueError("Ambiguous simultaneous revisions are not allowed")
        own_deadlines = _cutoffs(pd.DatetimeIndex(rows.date) + pd.Timedelta(days=1))
        rows = rows.loc[(pd.DatetimeIndex(rows.received_at) <= own_deadlines) & (pd.DatetimeIndex(rows.received_at) <= as_of)]
        fixed = rows.sort_values("received_at").drop_duplicates("date", keep="last").set_index("date")
        state = pd.Series(cal[item.market].values, index=dates)
        if state.reindex(fixed.index).eq("scheduled_closed").any():
            raise ValueError("An observation conflicts with a scheduled closure")
        slots = dates[state.ne("scheduled_closed")]
        values = fixed.value.where(fixed.quality.eq("observed")).reindex(slots).astype(float)
        values = values.where(state.reindex(slots).eq("open"))
        native = pd.DataFrame({"value": values}, index=slots)
        native[["received_at", "published_at", "receipt_sha256", "quality"]] = fixed[["received_at", "published_at", "receipt_sha256", "quality"]].reindex(slots)
        if item.market in ("fx", "equity"):
            log_return = np.log(values).diff()
            native["volatility"] = log_return.rolling(POLICY.volatility_window, min_periods=POLICY.volatility_window).std(ddof=1)
            native["volatility_rank"] = prior_midrank(native.volatility)
            segment = native.volatility_rank
            if item.market == "equity":
                peak = values.rolling(POLICY.drawdown_window, min_periods=POLICY.drawdown_window).max()
                native["drawdown"] = 1 - values / peak
                native["drawdown_rank"] = prior_midrank(native.drawdown)
                segment = native[["volatility_rank", "drawdown_rank"]].mean(axis=1, skipna=False)
        else:
            complete = values.rolling(POLICY.yield_change_window + 1, min_periods=POLICY.yield_change_window + 1).count().eq(POLICY.yield_change_window + 1)
            native["yield_increase"] = (values - values.shift(POLICY.yield_change_window)).clip(lower=0).where(complete)
            native["yield_increase_rank"] = prior_midrank(native.yield_increase)
            segment = native.yield_increase_rank
        native["segment"] = segment
        native_frames[item.market] = native
        # Carry an already computed state across scheduled closures only. Missing
        # open slots remain in the index and therefore cannot be filled over.
        positions = slots.searchsorted(dates, side="right") - 1
        selected = np.full(len(dates), np.nan)
        reference_dates = []
        for position, slot_index in enumerate(positions):
            reference = slots[slot_index] if slot_index >= 0 else pd.NaT
            reference_dates.append(reference)
            if slot_index >= 0 and (origins[position] - reference).days <= POLICY.max_reference_age_calendar_days:
                value = native.segment.iloc[slot_index]
                if pd.notna(value):
                    selected[position] = value
        result[item.market] = pd.Series(selected, dtype="Float64")
        result[item.market + "_reference_date"] = reference_dates
        result[item.market + "_calendar_state"] = cal[item.market].values
    result["stress_intensity"], result["stress_event"] = domestic_event(result[list(POLICY.mandatory_segments)])
    result["measurement_available"] = result.stress_event.notna()
    result["onset_risk_set"] = result.stress_event.eq(0).fillna(False).astype(bool)
    result["onset_origin_state"] = "current_state_unknown"
    result.loc[result.stress_event.eq(0).fillna(False), "onset_origin_state"] = "at_risk"
    result.loc[result.stress_event.eq(1).fillna(False), "onset_origin_state"] = "already_in_stress"
    local_as_of = as_of.tz_convert(POLICY.timezone)
    mature_through = local_as_of.tz_localize(None).normalize()
    if local_as_of.hour < POLICY.cutoff_hour:
        mature_through -= pd.Timedelta(days=1)
    labels = build_future_event_labels(result.date, result.stress_event, horizon_days=POLICY.forecast_horizon_calendar_days, outcomes_available_through=mature_through)
    result["target"] = labels.target.where(result.onset_risk_set).astype("Int64")
    result["label_end"] = labels.label_end
    result["mature"] = labels.mature
    result["complete_window"] = labels.complete_window
    result["episode_start"] = (result.stress_event.eq(1) & result.stress_event.shift(1).eq(0)).astype("boolean")
    result.loc[result.stress_event.isna() | result.stress_event.shift(1).isna(), "episode_start"] = pd.NA
    return MeasuredStress(data_snapshot_id=data_snapshot_id, calendar_snapshot_id=calendar_snapshot_id, frame=result, native_frames=native_frames)


def prepared_onset(measured):
    return PreparedValidation(
        data_snapshot_id=measured.data_snapshot_id,
        horizon_days=POLICY.forecast_horizon_calendar_days,
        frame=measured.frame.copy(),
        target_definition_id=POLICY.target_definition_id,
        calendar_snapshot_id=measured.calendar_snapshot_id,
        measurement_sha256=measured.measurement_sha256,
    )
