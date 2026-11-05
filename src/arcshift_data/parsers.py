"""Pure parsers for synthetic provider-shaped payloads.

The functions accept bytes and return dictionaries. They never open URLs, write
files, guess unknown dimension codes, or grant permission to use a source.
"""

import calendar
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
import math
import xml.etree.ElementTree as ElementTree


CURRENCY_SERIES = {
    "R01235": {
        "series_id": "ru.fx.cbr.usd_rub.official",
        "resource_id": "cbr_xml:R01235",
        "units": "RUB_per_USD",
    },
    "R01239": {
        "series_id": "ru.fx.cbr.eur_rub.official",
        "resource_id": "cbr_xml:R01239",
        "units": "RUB_per_EUR",
    },
}

CURVE_SERIES = {
    "1": ("ru.curve.cbr.zero_coupon.1y", "cbr:zcyc_params:1Y", 1),
    "2": ("ru.curve.cbr.zero_coupon.2y", "cbr:zcyc_params:2Y", 2),
    "5": ("ru.curve.cbr.zero_coupon.5y", "cbr:zcyc_params:5Y", 5),
    "10": ("ru.curve.cbr.zero_coupon.10y", "cbr:zcyc_params:10Y", 10),
}

CPI_CANONICAL_DIMENSIONS = {
    "territory": "RU_national",
    "coverage": "all_goods_and_services",
    "comparison": "same_month_previous_year",
    "frequency": "monthly",
}


def _parse_number(raw_value, field_name):
    if isinstance(raw_value, bool):
        raise ValueError(f"{field_name} must be a number")
    number_text = str(raw_value).strip().replace(" ", "").replace(",", ".")
    try:
        number = float(number_text)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a number") from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _parse_received_time(received_at):
    try:
        received_time = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ValueError("received_at must be an ISO timestamp") from error
    if received_time.tzinfo is None or received_time.utcoffset() is None:
        raise ValueError("received_at must include a timezone offset")
    return received_time


def _base_observation(
    series_id,
    resource_id,
    units,
    value,
    reference_start,
    reference_end,
    effective_date,
    received_at,
    snapshot_id,
    raw_payload,
    dimensions,
    is_synthetic,
):
    _parse_received_time(received_at)
    if not isinstance(is_synthetic, bool):
        raise ValueError("is_synthetic must be explicitly true or false")
    return {
        "schema_version": "candidate.1",
        "series_id": series_id,
        "definition_version": "candidate.1",
        "resource_id": resource_id,
        "units": units,
        "value": value,
        "quality": "observed",
        "reference_start": reference_start,
        "reference_end": reference_end,
        "effective_date": effective_date,
        "published_at": None,
        "publication_status": "unknown",
        "received_at": received_at,
        "source_timezone": "Europe/Moscow",
        "snapshot_id": snapshot_id,
        "receipt_sha256": hashlib.sha256(raw_payload).hexdigest(),
        "dimensions": dimensions,
        "is_synthetic": is_synthetic,
    }


def parse_cbr_currency_xml(raw_payload, currency_id, received_at, snapshot_id, is_synthetic):
    """Parse official-rate shaped XML and normalize the currency nominal."""
    if currency_id not in CURRENCY_SERIES:
        raise ValueError("Only the exact CBR USD and EUR currency IDs are supported")

    try:
        root = ElementTree.fromstring(raw_payload)
    except (ElementTree.ParseError, TypeError) as error:
        raise ValueError("Currency payload is not valid XML") from error

    observations = []
    for currency_record in root.findall(".//Record"):
        record_currency_id = currency_record.attrib.get("Id")
        if record_currency_id != currency_id:
            raise ValueError("Currency payload contains an unexpected currency ID")

        raw_date = currency_record.attrib.get("Date")
        try:
            effective_date = datetime.strptime(raw_date, "%d.%m.%Y").date().isoformat()
        except (TypeError, ValueError) as error:
            raise ValueError("Currency record has an invalid Date") from error

        currency_nominal = _parse_number(currency_record.findtext("Nominal"), "Nominal")
        currency_value = _parse_number(currency_record.findtext("Value"), "Value")
        if currency_nominal <= 0:
            raise ValueError("Currency Nominal must be positive")

        normalized_value = currency_value / currency_nominal
        raw_unit_rate = currency_record.findtext("VunitRate")
        if raw_unit_rate is not None:
            unit_rate = _parse_number(raw_unit_rate, "VunitRate")
            if not math.isclose(normalized_value, unit_rate, rel_tol=0, abs_tol=0.000001):
                raise ValueError("Value divided by Nominal conflicts with VunitRate")

        series = CURRENCY_SERIES[currency_id]
        observations.append(
            _base_observation(
                series_id=series["series_id"],
                resource_id=series["resource_id"],
                units=series["units"],
                value=normalized_value,
                reference_start=effective_date,
                reference_end=effective_date,
                effective_date=effective_date,
                received_at=received_at,
                snapshot_id=snapshot_id,
                raw_payload=raw_payload,
                dimensions={"currency_id": currency_id, "unit_nominal": 1},
                is_synthetic=is_synthetic,
            )
        )

    if not observations:
        raise ValueError("Currency payload contains no records")
    return observations


class _SimpleTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = None
        self.current_cell = None

    def handle_starttag(self, tag, attributes):
        if tag.lower() == "tr":
            self.current_row = []
        if tag.lower() in {"th", "td"} and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if tag.lower() in {"th", "td"} and self.current_cell is not None:
            cell_text = "".join(self.current_cell).strip()
            self.current_row.append(cell_text)
            self.current_cell = None
        if tag.lower() == "tr" and self.current_row is not None:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = None


def _normalize_maturity_header(raw_header):
    normalized_header = raw_header.strip().replace(",", ".")
    maturity_number = _parse_number(normalized_header, "curve maturity header")
    if maturity_number <= 0:
        raise ValueError("Curve maturity must be positive")
    return f"{maturity_number:g}"


def parse_cbr_curve_html(raw_payload, received_at, snapshot_id, is_synthetic):
    """Parse a provider-shaped curve table by tenor headers, never positions."""
    try:
        html_text = raw_payload.decode("utf-8")
    except (AttributeError, UnicodeDecodeError) as error:
        raise ValueError("Curve payload must be UTF-8 bytes") from error

    table_parser = _SimpleTableParser()
    table_parser.feed(html_text)
    if len(table_parser.rows) < 2:
        raise ValueError("Curve payload must contain a header and at least one row")

    header_row = table_parser.rows[0]
    if not header_row or header_row[0].strip().lower() not in {"date", "дата"}:
        raise ValueError("Curve table first column must be Date")

    maturity_to_column = {}
    for column_number, raw_header in enumerate(header_row[1:], start=1):
        normalized_header = _normalize_maturity_header(raw_header)
        if normalized_header in maturity_to_column:
            raise ValueError("Curve table has a duplicate maturity header")
        maturity_to_column[normalized_header] = column_number

    missing_maturities = set(CURVE_SERIES) - set(maturity_to_column)
    if missing_maturities:
        raise ValueError("Curve table is missing a required maturity header")

    observations = []
    for data_row in table_parser.rows[1:]:
        if len(data_row) != len(header_row):
            raise ValueError("Curve data row has the wrong number of columns")
        try:
            reference_date = datetime.strptime(data_row[0], "%d.%m.%Y").date().isoformat()
        except ValueError as error:
            raise ValueError("Curve data row has an invalid date") from error

        for maturity_header, series_details in CURVE_SERIES.items():
            series_id, resource_id, maturity_years = series_details
            value_column = maturity_to_column[maturity_header]
            curve_value = _parse_number(data_row[value_column], f"{maturity_years}Y curve value")
            observations.append(
                _base_observation(
                    series_id=series_id,
                    resource_id=resource_id,
                    units="percent_per_annum",
                    value=curve_value,
                    reference_start=reference_date,
                    reference_end=reference_date,
                    effective_date=None,
                    received_at=received_at,
                    snapshot_id=snapshot_id,
                    raw_payload=raw_payload,
                    dimensions={"maturity_years": maturity_years, "curve_type": "zero_coupon"},
                    is_synthetic=is_synthetic,
                )
            )
    return observations


def parse_rosstat_cpi_json(
    raw_payload,
    expected_dimension_codes,
    received_at,
    snapshot_id,
    is_synthetic,
):
    """Select CPI by explicit synthetic codes; never select by row order.

    Real Rosstat dimension codes are intentionally not built into this parser.
    The caller must provide codes from a separately approved source binding.
    """
    required_code_names = {"territory", "coverage", "comparison", "frequency"}
    if set(expected_dimension_codes) != required_code_names:
        raise ValueError("All four verified CPI dimension codes are required")

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("CPI payload is not valid UTF-8 JSON") from error

    if payload.get("indicator_id") != "11521100300010200001":
        raise ValueError("CPI payload has an unexpected indicator ID")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("CPI payload rows must be a list")

    matching_rows = []
    for cpi_row in rows:
        if not isinstance(cpi_row, dict):
            raise ValueError("Every CPI row must be an object")
        row_codes = cpi_row.get("dimension_codes")
        if row_codes == expected_dimension_codes:
            matching_rows.append(cpi_row)

    if len(matching_rows) != 1:
        raise ValueError("CPI dimensions must select exactly one row")

    selected_row = matching_rows[0]
    raw_period = selected_row.get("period")
    try:
        period_start = datetime.strptime(raw_period, "%Y-%m").date()
    except (TypeError, ValueError) as error:
        raise ValueError("CPI period must use YYYY-MM") from error
    last_day = calendar.monthrange(period_start.year, period_start.month)[1]
    reference_start = period_start.isoformat()
    reference_end = period_start.replace(day=last_day).isoformat()

    cpi_index_percent = _parse_number(selected_row.get("index_percent"), "CPI index_percent")
    if cpi_index_percent <= 0:
        raise ValueError("CPI index_percent must be positive")
    inflation_percent = cpi_index_percent - 100.0

    return [
        _base_observation(
            series_id="ru.prices.rosstat.cpi_yoy",
            resource_id="rosstat:11521100300010200001:selection_pending",
            units="percent_YoY",
            value=inflation_percent,
            reference_start=reference_start,
            reference_end=reference_end,
            effective_date=None,
            received_at=received_at,
            snapshot_id=snapshot_id,
            raw_payload=raw_payload,
            dimensions=CPI_CANONICAL_DIMENSIONS.copy(),
            is_synthetic=is_synthetic,
        )
    ]
