"""Pure parsers for synthetic provider-shaped payloads.

The functions accept bytes and return dictionaries. They never open URLs, write
files, guess unknown dimension codes, or grant permission to use a source.
"""

import calendar
import csv
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import io
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
    source_timezone="Europe/Moscow",
    published_at=None,
):
    received_time = _parse_received_time(received_at)
    if published_at is not None:
        published_time = _parse_received_time(published_at)
        if published_time > received_time:
            raise ValueError("published_at cannot follow received_at")
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
        "published_at": published_at,
        "publication_status": "known" if published_at is not None else "unknown",
        "received_at": received_at,
        "source_timezone": source_timezone,
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
                effective_date=effective_date if is_synthetic else None,
                received_at=received_at,
                snapshot_id=snapshot_id,
                raw_payload=raw_payload,
                dimensions={
                    "currency_id": currency_id,
                    "unit_nominal": 1,
                    "provider_date": effective_date,
                },
                is_synthetic=is_synthetic,
            )
        )

    if not observations:
        raise ValueError("Currency payload contains no records")
    return observations


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = None
        self.current_row = None
        self.current_cell = None
        self.outside_text = []

    def handle_starttag(self, tag, attributes):
        tag = tag.lower()
        if tag == "table":
            self.current_table = {
                "context": " ".join(self.outside_text[-12:]),
                "rows": [],
                "text": [],
            }
            self.outside_text = []
        elif tag == "tr" and self.current_table is not None:
            self.current_row = []
        elif tag in {"th", "td"} and self.current_row is not None:
            cell_attributes = dict(attributes)
            try:
                rowspan = int(cell_attributes.get("rowspan", "1"))
                colspan = int(cell_attributes.get("colspan", "1"))
            except ValueError as error:
                raise ValueError("Curve table has an invalid cell span") from error
            if rowspan < 1 or colspan < 1:
                raise ValueError("Curve table cell spans must be positive")
            self.current_cell = {
                "parts": [],
                "rowspan": rowspan,
                "colspan": colspan,
            }

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell["parts"].append(data)
        elif self.current_table is not None:
            self.current_table["text"].append(data)
        elif data.strip():
            self.outside_text.append(data.strip())

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"th", "td"} and self.current_cell is not None:
            self.current_cell["text"] = "".join(self.current_cell.pop("parts")).strip()
            self.current_row.append(self.current_cell)
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if self.current_row:
                self.current_table["rows"].append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.current_table is not None:
            self.tables.append(self.current_table)
            self.current_table = None


def _expand_table(rows):
    occupied = {}
    width = 0
    for row_number, row in enumerate(rows):
        column_number = 0
        for cell in row:
            while (row_number, column_number) in occupied:
                column_number += 1
            for row_offset in range(cell["rowspan"]):
                for column_offset in range(cell["colspan"]):
                    position = (row_number + row_offset, column_number + column_offset)
                    if position in occupied:
                        raise ValueError("Curve table has overlapping cells")
                    occupied[position] = cell["text"]
            column_number += cell["colspan"]
        width = max(width, column_number)
    return [
        [occupied.get((row_number, column_number), "") for column_number in range(width)]
        for row_number in range(len(rows))
    ]


def _normalize_maturity_header(raw_header):
    normalized_header = raw_header.strip().replace(",", ".")
    maturity_number = _parse_number(normalized_header, "curve maturity header")
    if maturity_number <= 0:
        raise ValueError("Curve maturity must be positive")
    return f"{maturity_number:g}"


def _curve_table_candidate(table):
    rows = _expand_table(table["rows"])
    for header_number, header_row in enumerate(rows):
        if not header_row or header_row[0].strip().lower() not in {"date", "дата"}:
            continue
        maturity_to_column = {}
        try:
            for column_number, raw_header in enumerate(header_row[1:], start=1):
                normalized_header = _normalize_maturity_header(raw_header)
                if normalized_header in maturity_to_column:
                    raise ValueError("Curve table has a duplicate maturity header")
                maturity_to_column[normalized_header] = column_number
        except ValueError:
            continue
        if set(CURVE_SERIES).issubset(maturity_to_column):
            return rows, header_number, maturity_to_column
    return None


def _curve_context(table):
    text = " ".join((table["context"], *table["text"])).lower()
    text = " ".join(text.split())
    curve_words = ("zero-coupon", "zero coupon", "yield curve", "zcyc", "бескупон", "кривой доходн")
    unit_words = ("% годовых", "процентов годовых", "percent per annum", "% p.a.")
    wrong_units = ("basis point", "базисн")
    return any(word in text for word in curve_words), any(word in text for word in unit_words), any(
        word in text for word in wrong_units
    )


def parse_cbr_curve_html(raw_payload, received_at, snapshot_id, is_synthetic):
    """Parse a provider-shaped curve table by tenor headers, never positions."""
    try:
        html_text = raw_payload.decode("utf-8")
    except (AttributeError, UnicodeDecodeError) as error:
        raise ValueError("Curve payload must be UTF-8 bytes") from error

    table_parser = _TableParser()
    table_parser.feed(html_text)
    candidates = []
    for table in table_parser.tables:
        candidate = _curve_table_candidate(table)
        if candidate is None:
            continue
        has_context, has_units, has_wrong_units = _curve_context(table)
        if not has_wrong_units:
            candidates.append((candidate, has_context, has_units))
    if not candidates:
        raise ValueError("Curve payload has no 1/2/5/10Y table")
    if len(candidates) > 1:
        candidates = [candidate for candidate in candidates if candidate[1] and candidate[2]]
    if len(candidates) != 1:
        raise ValueError("Curve payload does not identify one unambiguous percent-per-annum table")

    (rows, header_number, maturity_to_column), _, _ = candidates[0]
    header_row = rows[header_number]

    observations = []
    seen_dates = set()
    for data_row in rows[header_number + 1 :]:
        if len(data_row) != len(header_row):
            raise ValueError("Curve data row has the wrong number of columns")
        try:
            reference_date = datetime.strptime(data_row[0], "%d.%m.%Y").date().isoformat()
        except ValueError as error:
            raise ValueError("Curve data row has an invalid date") from error
        if reference_date in seen_dates:
            raise ValueError("Curve table has a duplicate date")
        seen_dates.add(reference_date)

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
    if not observations:
        raise ValueError("Curve table has no data rows")
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


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def parse_cbr_key_rate_xml(raw_payload, received_at, snapshot_id, is_synthetic):
    """Parse genuine CBR DailyInfo KeyRate rows without a refinancing fallback."""
    try:
        root = ElementTree.fromstring(raw_payload)
    except (ElementTree.ParseError, TypeError) as error:
        raise ValueError("Key-rate payload is not valid XML") from error

    observations = []
    seen_dates = set()
    for row in root.iter():
        children = {_local_name(child.tag): child.text for child in row}
        if "DT" not in children or "Rate" not in children:
            continue
        try:
            effective_date = datetime.fromisoformat(children["DT"].strip().replace("Z", "+00:00")).date()
        except (AttributeError, ValueError) as error:
            raise ValueError("Key-rate row has an invalid DT") from error
        if effective_date.isoformat() < "2013-09-17":
            raise ValueError("Genuine key-rate history cannot start before 2013-09-17")
        if effective_date in seen_dates:
            raise ValueError("Key-rate payload contains a duplicate effective date")
        seen_dates.add(effective_date)

        rate = _parse_number(children["Rate"], "KeyRate Rate")
        if rate <= 0 or rate > 100:
            raise ValueError("KeyRate Rate must be within (0, 100]")
        date_text = effective_date.isoformat()
        observations.append(
            _base_observation(
                series_id="ru.policy.cbr.key_rate",
                resource_id="cbr:DailyInfo:KeyRate",
                units="percent_per_annum",
                value=rate,
                reference_start=date_text,
                reference_end=date_text,
                effective_date=date_text,
                received_at=received_at,
                snapshot_id=snapshot_id,
                raw_payload=raw_payload,
                dimensions={"rate_type": "key_rate"},
                is_synthetic=is_synthetic,
            )
        )
    if not observations:
        raise ValueError("Key-rate payload contains no DailyInfo KeyRate rows")
    return observations


def parse_moex_imoex_json(
    raw_payload,
    received_at,
    snapshot_id,
    is_synthetic,
    published_at=None,
):
    """Parse MOEX ISS IMOEX history rows by named fields."""
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("IMOEX payload is not valid UTF-8 JSON") from error
    history = payload.get("history")
    if not isinstance(history, dict):
        raise ValueError("IMOEX payload has no history block")
    columns = history.get("columns")
    rows = history.get("data")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ValueError("IMOEX history columns and data must be lists")
    if not all(isinstance(column, str) and column for column in columns):
        raise ValueError("IMOEX history columns must be non-empty strings")
    required = {"SECID", "TRADEDATE", "CLOSE"}
    if not required.issubset(columns) or len(columns) != len(set(columns)):
        raise ValueError("IMOEX history must contain unique SECID, TRADEDATE and CLOSE columns")

    metadata = history.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict) or any(
            not isinstance(metadata.get(field_name), dict) for field_name in required
        ):
            raise ValueError("IMOEX history metadata must describe the required fields")
        metadata_status = "present"
    else:
        metadata_status = "absent"

    observations = []
    seen_dates = set()
    for values in rows:
        if not isinstance(values, list) or len(values) != len(columns):
            raise ValueError("IMOEX history row does not match its columns")
        row = dict(zip(columns, values))
        if row["SECID"] != "IMOEX":
            raise ValueError("IMOEX payload contains another security")
        if "BOARDID" in row and row["BOARDID"] != "SNDX":
            raise ValueError("IMOEX payload contains another board")
        try:
            trade_date = datetime.strptime(row["TRADEDATE"], "%Y-%m-%d").date().isoformat()
        except (TypeError, ValueError) as error:
            raise ValueError("IMOEX TRADEDATE must use YYYY-MM-DD") from error
        if trade_date in seen_dates:
            raise ValueError("IMOEX payload contains a duplicate trading date")
        seen_dates.add(trade_date)
        close = _parse_number(row["CLOSE"], "IMOEX CLOSE")
        if close <= 0:
            raise ValueError("IMOEX CLOSE must be positive")
        dimensions = {
            "security": "IMOEX",
            "field": "CLOSE",
            "metadata_status": metadata_status,
            "final_close_status": "unconfirmed",
        }
        if "BOARDID" in row:
            dimensions["board"] = row["BOARDID"]
        if "TRADINGSESSION" in row:
            if row["TRADINGSESSION"] in (None, ""):
                raise ValueError("IMOEX TRADINGSESSION cannot be empty when present")
            dimensions["trading_session"] = str(row["TRADINGSESSION"])
        observations.append(
            _base_observation(
                series_id="ru.equity.imoex.close",
                resource_id="moex:stock:index:IMOEX:history:CLOSE",
                units="index_points",
                value=close,
                reference_start=trade_date,
                reference_end=trade_date,
                effective_date=None,
                received_at=received_at,
                snapshot_id=snapshot_id,
                raw_payload=raw_payload,
                dimensions=dimensions,
                is_synthetic=is_synthetic,
                published_at=published_at,
            )
        )
    if not observations:
        raise ValueError("IMOEX payload contains no history rows")
    return observations


def parse_cboe_vix_csv(
    raw_payload,
    received_at,
    snapshot_id,
    is_synthetic,
    published_at=None,
):
    """Parse the official Cboe VIX history CSV and keep daily CLOSE only."""
    try:
        text = raw_payload.decode("utf-8-sig")
    except (AttributeError, UnicodeDecodeError) as error:
        raise ValueError("VIX payload must be UTF-8 CSV bytes") from error
    reader = csv.DictReader(io.StringIO(text))
    expected = {"DATE", "OPEN", "HIGH", "LOW", "CLOSE"}
    if reader.fieldnames is None or {name.strip().upper() for name in reader.fieldnames} != expected:
        raise ValueError("VIX CSV must contain DATE, OPEN, HIGH, LOW and CLOSE")

    observations = []
    seen_dates = set()
    for raw_row in reader:
        row = {key.strip().upper(): value for key, value in raw_row.items()}
        raw_date = row["DATE"].strip()
        trade_date = None
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                trade_date = datetime.strptime(raw_date, date_format).date().isoformat()
                break
            except ValueError:
                pass
        if trade_date is None:
            raise ValueError("VIX DATE must use MM/DD/YYYY or YYYY-MM-DD")
        if trade_date in seen_dates:
            raise ValueError("VIX CSV contains a duplicate trading date")
        seen_dates.add(trade_date)
        close = _parse_number(row["CLOSE"], "VIX CLOSE")
        if close <= 0:
            raise ValueError("VIX CLOSE must be positive")
        observations.append(
            _base_observation(
                series_id="global.volatility.cboe.vix.close",
                resource_id="cboe:VIX:daily_close",
                units="index_points",
                value=close,
                reference_start=trade_date,
                reference_end=trade_date,
                effective_date=None,
                received_at=received_at,
                snapshot_id=snapshot_id,
                raw_payload=raw_payload,
                dimensions={"index": "VIX", "field": "CLOSE"},
                is_synthetic=is_synthetic,
                source_timezone="America/New_York",
                published_at=published_at,
            )
        )
    if not observations:
        raise ValueError("VIX CSV contains no rows")
    return observations
