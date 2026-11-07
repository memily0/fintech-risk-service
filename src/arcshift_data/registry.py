"""Load the source registry without doing any network requests."""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "config/arcshift_source_registry.json"
EXACT_BINDING_SOURCES = {"cbr_key_rate", "rosstat_cpi_yoy", "moex_imoex", "cboe_vix"}


def load_source_registry(registry_path=DEFAULT_REGISTRY_PATH):
    """Read and validate the small ArcShift source registry."""
    registry_file = Path(registry_path)
    registry = json.loads(registry_file.read_text(encoding="utf-8"))

    if registry.get("schema_version") != "candidate.1":
        raise ValueError("Source registry must use schema version candidate.1")
    if registry.get("network_requests_allowed") is not False:
        raise ValueError("Candidate registry must keep network requests disabled")

    source_ids = set()
    for source in registry.get("sources", []):
        source_id = source.get("source_id")
        if not source_id or source_id in source_ids:
            raise ValueError("Every source_id must be present and unique")
        source_ids.add(source_id)

        rights = source.get("rights", {})
        expected_rights = {"display", "model_use", "export", "api_redistribution"}
        if set(rights) != expected_rights:
            raise ValueError(f"Incomplete rights matrix for {source_id}")

        request_budget = source.get("request_budget", {})
        for budget_name in ("technical_probe", "backfill", "incremental_per_run"):
            budget_value = request_budget.get(budget_name)
            if not isinstance(budget_value, int) or budget_value < 0:
                raise ValueError(f"Invalid {budget_name} request budget for {source_id}")

        if source.get("production_admitted") is not False:
            raise ValueError(f"Candidate source {source_id} cannot be production admitted")

        if source_id in EXACT_BINDING_SOURCES:
            binding = source.get("exact_binding")
            required = {
                "definition_id",
                "observation_time",
                "calendar_id",
                "availability_rule",
                "publication_time_rule",
            }
            if not isinstance(binding, dict) or not all(
                isinstance(binding.get(field), str) and binding[field].strip()
                for field in required
            ):
                raise ValueError(f"Incomplete exact binding for {source_id}")

    return registry
