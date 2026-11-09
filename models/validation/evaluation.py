"""Synthetic-only fold boundary for the proposed ArcShift V1 evaluation.

The legacy training script remains a separate baseline implementation.  This
module does not create an estimator or write an artifact: it only constructs a
versioned, point-in-time training batch that a recording test double can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Literal

import pandas as pd

from arcshift_v1.stress_definition import MEASUREMENT_SHA256, STRESS_DEFINITION
from arcshift_v1.task_definition import TASK_DEFINITION
from .product import PreparedValidation, training_rows


@dataclass(frozen=True)
class EvaluationManifestCandidate:
    manifest_id: Literal["ru-stress-onset-eval.candidate.1"] = "ru-stress-onset-eval.candidate.1"
    status: Literal["proposed_not_authorized"] = "proposed_not_authorized"
    task_contract_version: str = TASK_DEFINITION.task_contract_version
    task_id: str = TASK_DEFINITION.task_id
    target_definition_id: str = TASK_DEFINITION.target_definition_id
    measurement_id: str = STRESS_DEFINITION.measurement_id
    measurement_sha256: str = MEASUREMENT_SHA256
    horizon_calendar_days: int = TASK_DEFINITION.primary_horizon_days
    forecast_timezone: str = STRESS_DEFINITION.timezone
    forecast_cutoff_hour: int = STRESS_DEFINITION.cutoff_hour
    baseline: Literal["training_prevalence_constant"] = "training_prevalence_constant"
    comparator: Literal["l2_logistic_regression_c_1"] = "l2_logistic_regression_c_1"
    logistic_c: Literal[1.0] = 1.0
    logistic_class_weight: Literal["none"] = "none"
    preprocessing: tuple[str, ...] = ("train_median_imputation", "train_standard_scaling")
    random_seed: Literal[42] = 42
    outer_fold_count: Literal[4] = 4
    inner_fold_count: Literal[3] = 3
    purge_rule: Literal["label_end_strictly_before_fold_cutoff"] = "label_end_strictly_before_fold_cutoff"
    calibration: Literal["sigmoid_from_inner_oof_if_eligible"] = "sigmoid_from_inner_oof_if_eligible"
    calibration_minimum_per_class: Literal[20] = 20
    max_estimator_fits_per_outer_fold: Literal[5] = 5
    matched_origins_required: Literal[True] = True
    exact_outer_cutoffs: tuple[str, ...] = ()
    feature_schema_status: Literal["pending_admitted_snapshot"] = "pending_admitted_snapshot"
    warning_threshold_status: Literal["pending_product_decision"] = "pending_product_decision"
    numeric_acceptance_status: Literal["pending_product_decision"] = "pending_product_decision"
    m04_authorized: Literal[False] = False


MANIFEST_CANDIDATE = EvaluationManifestCandidate()


@dataclass(frozen=True)
class FeatureSnapshot:
    snapshot_id: str
    schema_id: str
    available_through: pd.Timestamp | str
    frame: pd.DataFrame
    synthetic: bool = True


@dataclass(frozen=True)
class FoldTrainingBatch:
    cutoff: pd.Timestamp
    task_id: str
    target_definition_id: str
    horizon_days: int
    data_snapshot_id: str
    calendar_snapshot_id: str
    feature_snapshot_id: str
    feature_schema_id: str
    measurement_sha256: str
    origins: pd.Series
    features: pd.DataFrame
    target: pd.Series
    excluded_feature_unavailable: int


def _identity(value: str | None, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(name + " must be an explicit version identity")
    return value


def _aware_cutoff(value: pd.Timestamp | str, name: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError(name + " must be a timezone-aware timestamp")
    local = timestamp.tz_convert(STRESS_DEFINITION.timezone)
    if any((local.hour != STRESS_DEFINITION.cutoff_hour, local.minute != 0, local.second != 0, local.microsecond != 0)):
        raise ValueError(name + " must be exactly 09:00 Europe/Moscow")
    return timestamp.tz_convert("UTC"), local


def _same_asof(value: pd.Timestamp | str | None, cutoff_utc: pd.Timestamp, name: str) -> None:
    if value is None:
        raise ValueError(name + " must record its point-in-time availability")
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError(name + " must be timezone-aware")
    if timestamp.tz_convert("UTC") != cutoff_utc:
        raise ValueError(name + " must equal the fold cutoff; later snapshots are forbidden")


def fold_training_batch(
    prepared: PreparedValidation,
    feature_snapshot: FeatureSnapshot,
    *,
    cutoff: pd.Timestamp | str,
) -> FoldTrainingBatch:
    """Return matched synthetic rows from snapshots fixed exactly at a fold cutoff."""

    if prepared.synthetic is not True or feature_snapshot.synthetic is not True:
        raise ValueError("Only synthetic fold construction is allowed before M04")
    if prepared.horizon_days != TASK_DEFINITION.primary_horizon_days:
        raise ValueError("Only the approved 30-calendar-day task is supported")
    if prepared.target_definition_id != TASK_DEFINITION.target_definition_id:
        raise ValueError("Prepared target does not match the current task definition")
    if prepared.measurement_sha256 != MEASUREMENT_SHA256:
        raise ValueError("Prepared target does not match the frozen measurement hash")

    data_snapshot_id = _identity(prepared.data_snapshot_id, "data_snapshot_id")
    calendar_snapshot_id = _identity(prepared.calendar_snapshot_id, "calendar_snapshot_id")
    feature_snapshot_id = _identity(feature_snapshot.snapshot_id, "feature_snapshot_id")
    feature_schema_id = _identity(feature_snapshot.schema_id, "feature_schema_id")
    cutoff_utc, cutoff_local = _aware_cutoff(cutoff, "cutoff")
    _same_asof(prepared.available_through, cutoff_utc, "prepared snapshot")
    _same_asof(feature_snapshot.available_through, cutoff_utc, "feature snapshot")

    features = feature_snapshot.frame
    frame = prepared.frame
    if features.empty or not features.index.is_unique:
        raise ValueError("Feature snapshot must contain uniquely indexed rows")
    if not features.index.equals(frame.index):
        raise ValueError("Feature snapshot index must exactly match prepared target index")
    for column in features:
        invalid = [
            value
            for value in features[column].dropna()
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
        ]
        if invalid:
            raise ValueError("Feature values must be finite numbers or missing")

    cutoff_date = cutoff_local.tz_localize(None).normalize()
    eligible = training_rows(prepared, cutoff=cutoff_date)
    eligible_features = features.loc[eligible.index]
    available = eligible_features.notna().all(axis=1)
    selected_index = eligible_features.index[available]
    if selected_index.empty:
        raise ValueError("No matched origins have complete features at this fold")

    return FoldTrainingBatch(
        cutoff=cutoff_utc,
        task_id=TASK_DEFINITION.task_id,
        target_definition_id=TASK_DEFINITION.target_definition_id,
        horizon_days=TASK_DEFINITION.primary_horizon_days,
        data_snapshot_id=data_snapshot_id,
        calendar_snapshot_id=calendar_snapshot_id,
        feature_snapshot_id=feature_snapshot_id,
        feature_schema_id=feature_schema_id,
        measurement_sha256=MEASUREMENT_SHA256,
        origins=frame.loc[selected_index, "date"].copy(),
        features=features.loc[selected_index].copy(),
        target=frame.loc[selected_index, "target"].astype("Int64").copy(),
        excluded_feature_unavailable=int((~available).sum()),
    )
