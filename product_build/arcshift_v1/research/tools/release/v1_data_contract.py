"""Offline candidate-contract checks. No fetch, fit, serving, or rights grants."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker


DIRECTORY = Path(__file__).resolve().parents[2] / "08_product_handoff/v1_data_contract"


def load_contract():
    return json.loads((DIRECTORY / "candidate_contract.json").read_text(encoding="utf-8"))


def _aware(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include a UTC offset")
    return parsed


def _same_dimensions(actual, expected):
    return json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)


def validate_observation(record):
    schema = json.loads((DIRECTORY / "observation.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    contract = load_contract()
    candidates = {entry["series_id"]: entry for entry in contract["raw_series"]}
    if record["series_id"] not in candidates:
        raise ValueError("Unknown raw series")
    series = candidates[record["series_id"]]
    for key in ("resource_id", "units"):
        if record[key] != series[key]:
            raise ValueError(f"Wrong {key} for {series['series_id']}")
    if not _same_dimensions(record["dimensions"], series["dimensions"]):
        raise ValueError("Wrong dimensions")
    if record["source_timezone"] != series["timezone"]:
        raise ValueError("Wrong source timezone")
    ZoneInfo(record["source_timezone"])
    if record["value"] is not None and not math.isfinite(record["value"]):
        raise ValueError("Nonfinite value")
    if record["reference_start"] > record["reference_end"]:
        raise ValueError("Reversed reference period")
    lower_bound = series.get("history_not_before")
    if lower_bound and record["reference_start"] < lower_bound:
        raise ValueError("Observation predates this series definition")
    if series["frequency"] in {"official_daily_rate", "policy_effective_daily"} and record["effective_date"] is None:
        raise ValueError("This series requires an effective date")
    received = _aware(record["received_at"])
    if record["published_at"] is not None and _aware(record["published_at"]) > received:
        raise ValueError("An actually observed publication cannot follow its receipt")
    if series["legacy_column"] == "inflation":
        start, end = date.fromisoformat(record["reference_start"]), date.fromisoformat(record["reference_end"])
        next_day = end.toordinal() + 1
        if start.day != 1 or (start.year, start.month) != (end.year, end.month) or date.fromordinal(next_day).month == end.month:
            raise ValueError("CPI needs a complete monthly reference period")
        if record["effective_date"] is not None:
            raise ValueError("Monthly CPI uses reference period and release time not an invented effective date")
    return series


def normalize_cpi_yoy(index_percent, dimensions):
    """Normalize canonical verified dimensions; does not map provider codes."""
    series = next(s for s in load_contract()["raw_series"] if s["legacy_column"] == "inflation")
    if not _same_dimensions(dimensions, series["dimensions"]):
        raise ValueError("Expected national all-items monthly CPI versus same month last year")
    if isinstance(index_percent, bool) or not isinstance(index_percent, (int, float)) or not math.isfinite(index_percent) or index_percent <= 0:
        raise ValueError("CPI index must be a finite positive number")
    return index_percent - 100.0


def select_curve_points(maturity_headers, values):
    """Select normalized maturity labels, never infer tenor from cell position."""
    if len(maturity_headers) != len(values):
        raise ValueError("Curve header and value lengths differ")
    columns = {}
    for header, value in zip(maturity_headers, values):
        try:
            maturity = Decimal(str(header).strip().replace(",", "."))
        except InvalidOperation as exc:
            raise ValueError("Invalid maturity label") from exc
        if not maturity.is_finite() or maturity <= 0 or maturity in columns:
            raise ValueError("Ambiguous maturity header")
        columns[maturity] = value
    selected = {}
    for years in (1, 2, 5, 10):
        if Decimal(years) not in columns:
            raise ValueError("Required curve maturity is missing")
        value = columns[Decimal(years)]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Required curve value is not a finite number")
        selected[f"ofz_{years}y"] = value
    return selected


def known_and_effective_by(record, origin):
    """Receipt/effective-time check only; not a freshness or production verdict."""
    validate_observation(record)
    as_of = _aware(origin)
    if record["quality"] != "observed":
        return False
    if _aware(record["received_at"]) > as_of:
        return False
    if record["published_at"] is not None and _aware(record["published_at"]) > as_of:
        return False
    local_date = as_of.astimezone(ZoneInfo(record["source_timezone"])).date()
    if date.fromisoformat(record["reference_end"]) > local_date:
        return False
    if record["effective_date"] is not None and date.fromisoformat(record["effective_date"]) > local_date:
        return False
    return True


def assert_candidate_usage_blocked(record, mode):
    """Validate a candidate and refuse public/model use; not an approval API."""
    validate_observation(record)
    contract = load_contract()
    if mode not in contract["usage_modes"]:
        raise ValueError("Unknown usage mode")
    raise PermissionError("Candidate contract is not a source admission; production usage remains blocked")
