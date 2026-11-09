"""No model loader: explicit serving boundary until source/task/artifact admission."""

from typing import Literal

from .market import MarketStore
from .schemas import ContractModel, SyntheticModel
from .stress_definition import MEASUREMENT_SHA256, STRESS_DEFINITION
from .task_definition import APPROVED_HORIZONS, LEGACY_CANDIDATE_HORIZONS, PRIMARY_HORIZON_DAYS, TASK, TARGET, TASK_CONTRACT_VERSION


MILA_SOURCE = "eb54d6ed10e8337afc6c0221419936be07f6dadc"
TARGET_INPUTS = {item.market: (item.series_id,) for item in STRESS_DEFINITION.inputs}
BLOCKERS = ("measurement_not_validated", "sources_not_admitted", "source_calendars_not_verified", "mandatory_stress_inputs_incomplete", "evaluation_not_run", "accepted_artifact_missing")


class InputCoverage(ContractModel):
    component: str
    required_series: tuple[str, ...]
    missing_series: tuple[str, ...]
    present_in_synthetic_snapshot: bool
    feature_ready: Literal[False] = False


class ModelEnvelope(SyntheticModel):
    model_contract_version: Literal["v1-model-readiness.3"] = "v1-model-readiness.3"
    production_ready: Literal[False] = False
    data_mode: Literal["synthetic"] = "synthetic"
    source_rights_status: Literal["not_admitted"] = "not_admitted"
    data_snapshot_id: str


class ModelStatus(ModelEnvelope):
    task_id: Literal["ru_market_stress_onset_v1"] = TASK
    task_contract_version: Literal["v1-task.2"] = TASK_CONTRACT_VERSION
    task_scope_status: Literal["user_confirmed"] = "user_confirmed"
    target_definition_id: Literal["ru_domestic_stress_onset.1"] = TARGET
    target_measurement_status: Literal["design_frozen_not_validated"] = STRESS_DEFINITION.status
    measurement_sha256: str = MEASUREMENT_SHA256
    source_commit: Literal["eb54d6ed10e8337afc6c0221419936be07f6dadc"] = MILA_SOURCE
    source_commit_scope: Literal["imported_temporal_core_only"] = "imported_temporal_core_only"
    status: Literal["not_admitted"] = "not_admitted"
    geography: Literal["RU"] = "RU"
    candidate_horizons_days: tuple[Literal[7, 30, 90], ...] = LEGACY_CANDIDATE_HORIZONS
    candidate_horizons_scope: Literal["legacy_inventory_not_serving_approval"] = "legacy_inventory_not_serving_approval"
    primary_horizon_days: Literal[30] = PRIMARY_HORIZON_DAYS
    approved_horizons_days: tuple[Literal[30]] = APPROVED_HORIZONS
    horizon_approval_scope: Literal["business_task_not_model_admission"] = "business_task_not_model_admission"
    accepted_artifact_available: Literal[False] = False
    calibration_status: Literal["not_established"] = "not_established"
    coverage_scope: Literal["raw_target_inputs_only_not_feature_readiness"] = "raw_target_inputs_only_not_feature_readiness"
    input_coverage: tuple[InputCoverage, ...]
    missing_input_series: tuple[str, ...]
    blockers: tuple[str, ...]


class CurrentSignal(ModelEnvelope):
    task_id: str
    geography: str
    horizon_days: int
    state: Literal["unavailable", "unsupported"]
    reasons: tuple[str, ...]
    signal: None = None


def model_status(store: MarketStore):
    snapshot = store.read()
    present = {row.observation.series_id for row in snapshot.latest.values()}
    coverage = tuple(InputCoverage(component=component, required_series=required, missing_series=tuple(value for value in required if value not in present), present_in_synthetic_snapshot=all(value in present for value in required)) for component, required in TARGET_INPUTS.items())
    missing = tuple(sorted({value for item in coverage for value in item.missing_series}))
    blockers = tuple(value for value in BLOCKERS if value != "mandatory_stress_inputs_incomplete" or missing)
    return ModelStatus(data_snapshot_id="market-" + snapshot.snapshot_id, input_coverage=coverage, missing_input_series=missing, blockers=blockers)


def current_signal(store, *, geography, horizon_days, task_id):
    status = model_status(store)
    unsupported = []
    if geography != "RU":
        unsupported.append("geography_not_supported")
    if horizon_days not in APPROVED_HORIZONS:
        unsupported.append("horizon_not_approved")
    if task_id != TASK:
        unsupported.append("task_not_supported")
    return CurrentSignal(data_snapshot_id=status.data_snapshot_id, task_id=task_id, geography=geography, horizon_days=horizon_days, state="unsupported" if unsupported else "unavailable", reasons=tuple(unsupported) if unsupported else status.blockers)
