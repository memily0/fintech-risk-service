"""Candidate API envelopes around the shared v1-handoff.1 UI fixtures."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


API_CONTRACT_VERSION = "v1-fixture.1"
SCENARIO_IDS = ("loading", "empty", "stale", "unsupported", "error", "historical_demo")
ScenarioID = Literal["loading", "empty", "stale", "unsupported", "error", "historical_demo"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SyntheticModel(ContractModel):
    synthetic: Literal[True] = True

    @field_validator("synthetic", mode="before")
    @classmethod
    def must_be_boolean_true(cls, value):
        if value is not True:
            raise ValueError("Fixture must be explicitly synthetic=true")
        return value


class DemoSignal(ContractModel):
    task_id: Literal["synthetic:future_stress_proxy"]
    horizon_value: Literal[30]
    horizon_unit: Literal["calendar_days"]
    score: Annotated[float, Field(ge=0, le=1)]
    score_kind: Literal["synthetic_uncalibrated_score"]
    calibration_status: Literal["not_validated"]
    validity_status: Literal["historical_demo"]
    snapshot_id: Literal["synthetic-ui-001"]
    model_version: Literal["synthetic-no-fitted-model"]
    forecast_origin: AwareDatetime
    information_as_of: AwareDatetime
    drivers: Annotated[tuple[dict, ...], Field(max_length=0)]

    @field_validator("score", mode="before")
    @classmethod
    def numeric_score_only(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Score must be numeric, not a string or boolean")
        return value

    @model_validator(mode="after")
    def chronological_information(self):
        if self.information_as_of > self.forecast_origin:
            raise ValueError("Information cannot follow the forecast origin")
        return self


class DemoScenario(SyntheticModel):
    id: ScenarioID
    state: ScenarioID
    signal: DemoSignal | None
    message: Annotated[str, Field(min_length=1, max_length=512)]

    @model_validator(mode="after")
    def consistent_state(self):
        if self.id != self.state:
            raise ValueError("Scenario ID and state differ")
        if (self.state == "historical_demo") != (self.signal is not None):
            raise ValueError("Only historical_demo may carry a synthetic signal")
        return self


class FixtureDataset(SyntheticModel):
    fixture_version: Literal["v1-handoff.1"]
    not_training_or_provider_data: Literal[True]
    scenarios: Annotated[tuple[DemoScenario, ...], Field(min_length=6, max_length=6)]

    @model_validator(mode="before")
    @classmethod
    def explicit_fixture_labels(cls, value):
        if isinstance(value, dict):
            if value.get("synthetic") is not True or value.get("not_training_or_provider_data") is not True:
                raise ValueError("Dataset needs explicit synthetic and non-provider labels")
            if any(row.get("synthetic") is not True for row in value.get("scenarios", []) if isinstance(row, dict)):
                raise ValueError("Each scenario needs an explicit synthetic label")
        return value

    @model_validator(mode="after")
    def complete_scenario_set(self):
        if {row.id for row in self.scenarios} != set(SCENARIO_IDS):
            raise ValueError("Expected all six distinct fixture scenarios")
        return self


class APIEnvelope(SyntheticModel):
    api_contract_version: Literal["v1-fixture.1"] = API_CONTRACT_VERSION
    fixture_version: Literal["v1-handoff.1"] = "v1-handoff.1"
    data_mode: Literal["synthetic"] = "synthetic"
    production_ready: Literal[False] = False
    source_rights_status: Literal["not_admitted"] = "not_admitted"


class ScenarioListResponse(APIEnvelope):
    scenarios: tuple[DemoScenario, ...]


class ScenarioResponse(APIEnvelope):
    scenario: DemoScenario


class HealthResponse(APIEnvelope):
    status: Literal["ok"] = "ok"
    environment: Literal["local", "test"]
    readiness_scope: Literal["fixture_development_only"] = "fixture_development_only"


class CapabilitiesResponse(APIEnvelope):
    scenario_ids: tuple[ScenarioID, ...] = SCENARIO_IDS
    public_registration_implemented: Literal[False] = False
    live_ingest_implemented: Literal[False] = False
    accepted_model_available: Literal[False] = False
    private_state_implemented: Literal[False] = False
