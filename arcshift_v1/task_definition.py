"""Approved business scope, distinct from a frozen measurement or accepted model."""

from dataclasses import dataclass
from typing import Literal

from .stress_definition import MEASUREMENT_SHA256, STRESS_DEFINITION


TASK = "ru_market_stress_onset_v1"
TARGET = STRESS_DEFINITION.target_definition_id
TASK_CONTRACT_VERSION = "v1-task.2"
PRIMARY_HORIZON_DAYS = STRESS_DEFINITION.forecast_horizon_calendar_days
APPROVED_HORIZONS = (PRIMARY_HORIZON_DAYS,)
LEGACY_CANDIDATE_HORIZONS = (7, 30, 90)


@dataclass(frozen=True)
class TaskDefinition:
    task_contract_version: Literal["v1-task.2"] = TASK_CONTRACT_VERSION
    task_id: Literal["ru_market_stress_onset_v1"] = TASK
    business_scope_status: Literal["user_confirmed"] = "user_confirmed"
    approved_on: Literal["2026-11-06"] = "2026-11-06"
    geography: Literal["RU"] = "RU"
    intended_user: Literal["risk_analyst"] = "risk_analyst"
    objective: Literal["warning_of_new_market_stress_episode"] = "warning_of_new_market_stress_episode"
    intended_action: Literal["investigate_external_risk_and_record_review"] = "investigate_external_risk_and_record_review"
    primary_horizon_days: Literal[30] = PRIMARY_HORIZON_DAYS
    approved_horizons_days: tuple[Literal[30]] = APPROVED_HORIZONS
    horizon_unit: Literal["calendar_days"] = "calendar_days"
    future_window: Literal["(t, t + 30 days]"] = "(t, t + 30 days]"
    onset_risk_set: Literal["current_stress_known_absent"] = "current_stress_known_absent"
    already_in_stress: Literal["monitor_current_state_do_not_score_onset"] = "monitor_current_state_do_not_score_onset"
    unknown_policy: Literal["unavailable_never_zero"] = "unavailable_never_zero"
    target_definition_id: Literal["ru_domestic_stress_onset.1"] = TARGET
    measurement_id: Literal["ru-domestic-market-stress.1"] = STRESS_DEFINITION.measurement_id
    measurement_sha256: str = MEASUREMENT_SHA256
    measurement_status: Literal["design_frozen_not_validated"] = STRESS_DEFINITION.status
    calendar_alignment_status: Literal["design_frozen_provider_verification_pending"] = "design_frozen_provider_verification_pending"
    forecast_cutoff_status: Literal["design_frozen_provider_verification_pending"] = "design_frozen_provider_verification_pending"
    model_validation_status: Literal["not_run"] = "not_run"
    operating_warning_policy_status: Literal["pending"] = "pending"
    decision_impact_validated: Literal[False] = False
    horizon_optimality_established: Literal[False] = False
    production_ready: Literal[False] = False
    excluded_claims: tuple[str, ...] = (
        "systemic_banking_crisis_probability", "borrower_PD_or_expected_loss",
        "automatic_investment_credit_or_regulatory_decision", "other_country_forecast_coverage",
    )


TASK_DEFINITION = TaskDefinition()
