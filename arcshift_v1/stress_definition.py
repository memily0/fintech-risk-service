"""Versioned measurement policy, not empirical validation or source admission."""

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Literal


@dataclass(frozen=True)
class StressInput:
    market: str
    series_id: str
    resource_id: str
    units: str


@dataclass(frozen=True)
class StressDefinition:
    measurement_id: Literal["ru-domestic-market-stress.1"] = "ru-domestic-market-stress.1"
    target_definition_id: Literal["ru_domestic_stress_onset.1"] = "ru_domestic_stress_onset.1"
    frozen_on: Literal["2026-11-08"] = "2026-11-08"
    status: Literal["design_frozen_not_validated"] = "design_frozen_not_validated"
    inputs: tuple[StressInput, ...] = (
        StressInput("fx", "ru.fx.cbr.usd_rub.official", "cbr_xml:R01235", "RUB_per_USD"),
        StressInput("equity", "ru.equity.imoex.close", "moex:stock:index:IMOEX:history:CLOSE", "index_points"),
        StressInput("rates", "ru.curve.cbr.zero_coupon.10y", "cbr:zcyc_params:10Y", "percent_per_annum"),
    )
    timezone: Literal["Europe/Moscow"] = "Europe/Moscow"
    cutoff_hour: Literal[9] = 9
    reference_policy: Literal["strictly_before_origin_date"] = "strictly_before_origin_date"
    fixing_policy: Literal["latest_received_revision_by_next_day_cutoff_then_immutable"] = "latest_received_revision_by_next_day_cutoff_then_immutable"
    volatility_window: Literal[20] = 20
    volatility_returns: Literal["log_returns_sample_std_ddof_1_not_annualized"] = "log_returns_sample_std_ddof_1_not_annualized"
    drawdown_window: Literal[252] = 252
    drawdown_formula: Literal["1_minus_price_over_trailing_max_including_current"] = "1_minus_price_over_trailing_max_including_current"
    yield_change_window: Literal[20] = 20
    yield_change_formula: Literal["positive_part_of_10y_yield_change_in_percentage_points"] = "positive_part_of_10y_yield_change_in_percentage_points"
    rank_window: Literal[756] = 756
    rank_min_history: Literal[252] = 252
    rank_formula: Literal["prior_only_midrank_ecdf"] = "prior_only_midrank_ecdf"
    window_unit: Literal["provider_native_observation_slots_not_calendar_days"] = "provider_native_observation_slots_not_calendar_days"
    equity_aggregation: Literal["mean_of_volatility_and_drawdown_ranks"] = "mean_of_volatility_and_drawdown_ranks"
    segment_threshold: Literal[0.9] = 0.9
    threshold_comparison: Literal["greater_than_or_equal"] = "greater_than_or_equal"
    required_segments: Literal[2] = 2
    mandatory_segments: tuple[str, ...] = ("fx", "equity", "rates")
    intensity_aggregation: Literal["equal_mean_of_three_segments_not_a_probability"] = "equal_mean_of_three_segments_not_a_probability"
    calendar_states: tuple[str, ...] = ("open", "scheduled_closed", "suspended", "unknown")
    closed_day_policy: Literal["carry_state_only_no_new_return_or_rank_observation"] = "carry_state_only_no_new_return_or_rank_observation"
    max_reference_age_calendar_days: Literal[7] = 7
    unknown_policy: Literal["any_mandatory_unknown_makes_event_unknown"] = "any_mandatory_unknown_makes_event_unknown"
    episode_policy: Literal["consecutive_event_ones_unknown_breaks_observation_not_proven_recovery"] = "consecutive_event_ones_unknown_breaks_observation_not_proven_recovery"
    forecast_horizon_calendar_days: Literal[30] = 30
    global_context_in_event: Literal[False] = False
    empirical_validity_established: Literal[False] = False
    source_admission_complete: Literal[False] = False
    production_ready: Literal[False] = False


STRESS_DEFINITION = StressDefinition()
MEASUREMENT_SHA256 = hashlib.sha256(json.dumps(asdict(STRESS_DEFINITION), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")).hexdigest()
