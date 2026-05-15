from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


START_DATE = pd.Timestamp("2014-01-01")
CBR_LOOKBACK_DATE = pd.Timestamp("2013-01-01")
FFILL_LIMIT_DAYS = 14
STALE_SOURCE_DAYS = 14

FINAL_COLUMNS = [
    "date",
    "gold",
    "brent",
    "usd_rub",
    "eur_rub",
    "imoex",
    "vix",
    "sp500",
    "ofz_1y",
    "ofz_2y",
    "ofz_5y",
    "ofz_10y",
    "key_rate",
    "inflation",
    "ofz_spread_10_2",
    "usd_volatility",
    "imoex_volatility",
    "imoex_drawdown",
    "imoex_zscore",
    "real_key_rate",
]

POSITIVE_COLUMNS = ["imoex", "sp500", "gold", "brent", "vix"]
STICKINESS_COLUMNS = ["imoex", "usd_rub", "eur_rub", "brent", "gold", "vix", "sp500"]
REQUIRED_NONEMPTY_COLUMNS = [column for column in FINAL_COLUMNS if column != "date"]

YFINANCE_TICKERS = {
    "gold": "GC=F",
    "brent": "BZ=F",
    "vix": "^VIX",
    "sp500": "^GSPC",
}

CBR_CURRENCIES = {
    "usd_rub": "R01235",
    "eur_rub": "R01239",
}

OFZ_FILES = {
    "ofz_1y": ("data/moex/ofz_1y.csv", "period_1.0"),
    "ofz_2y": ("data/moex/ofz_2y.csv", "period_2.0"),
    "ofz_5y": ("data/moex/ofz_5y.csv", "period_5.0"),
    "ofz_10y": ("data/moex/ofz_10y.csv", "period_10.0"),
}


@dataclass
class SourceStatus:
    name: str
    rows: int
    min_date: pd.Timestamp | None
    max_date: pd.Timestamp | None


@dataclass
class ValidationResult:
    critical_errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.critical_errors


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def cbr_slash_date(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%d/%m/%Y")


def cbr_dot_date(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%d.%m.%Y")


def parse_float(value: object) -> float:
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if text in {"", "None", "nan", "NaN", "null"}:
        return np.nan
    return float(text)


def fetch_url_text(url: str, params: dict[str, object] | None = None, encoding: str = "utf-8") -> str:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; IVR dataset builder)",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode(encoding, errors="replace")


def fetch_url_json(url: str, params: dict[str, object] | None = None) -> dict:
    return json.loads(fetch_url_text(url, params=params, encoding="utf-8"))


def standardize_series(df: pd.DataFrame, column: str) -> pd.DataFrame:
    result = df[["date", column]].copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.normalize()
    result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=["date"]).sort_values("date")
    result = result.groupby("date", as_index=False).last()
    return result


def source_status(name: str, df: pd.DataFrame) -> SourceStatus:
    if df.empty:
        status = SourceStatus(name=name, rows=0, min_date=None, max_date=None)
    else:
        dates = pd.to_datetime(df["date"], errors="coerce").dropna()
        status = SourceStatus(
            name=name,
            rows=len(df),
            min_date=dates.min().normalize() if not dates.empty else None,
            max_date=dates.max().normalize() if not dates.empty else None,
        )
    print_source_status(status)
    return status


def print_source_status(status: SourceStatus) -> None:
    min_date = status.min_date.date().isoformat() if status.min_date is not None else "n/a"
    max_date = status.max_date.date().isoformat() if status.max_date is not None else "n/a"
    print(f"[source] {status.name}: rows={status.rows}, min_date={min_date}, max_date={max_date}")


def fetch_cbr_currency_series(
    currency_id: str,
    column: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    print(f"[download] CBR currency {column} ({currency_id})")
    text = fetch_url_text(
        "https://www.cbr.ru/scripts/XML_dynamic.asp",
        params={
            "date_req1": cbr_slash_date(start_date),
            "date_req2": cbr_slash_date(end_date),
            "VAL_NM_RQ": currency_id,
        },
        encoding="windows-1251",
    )
    root = ET.fromstring(text)
    rows: list[dict[str, object]] = []

    for record in root.findall("Record"):
        date_text = record.attrib.get("Date")
        value_text = record.findtext("VunitRate") or record.findtext("Value")
        nominal_text = record.findtext("Nominal") or "1"
        if not date_text or value_text is None:
            continue

        value = parse_float(value_text)
        if record.findtext("VunitRate") is None:
            nominal = parse_float(nominal_text)
            if pd.notna(nominal) and nominal != 0:
                value = value / nominal

        rows.append(
            {
                "date": pd.to_datetime(date_text, format="%d.%m.%Y", errors="coerce"),
                column: value,
            }
        )

    df = standardize_series(pd.DataFrame(rows), column)
    broken_mask = df[column] < 20
    if broken_mask.any():
        print(f"[warning] {column}: replacing {int(broken_mask.sum())} absurd values < 20 with NaN before ffill")
        df.loc[broken_mask, column] = np.nan
    return df


def fetch_cbr_key_rate(start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    print("[download] CBR key rate")
    text = fetch_url_text(
        "https://www.cbr.ru/hd_base/KeyRate/",
        params={
            "UniDbQuery.Posted": "True",
            "UniDbQuery.From": cbr_dot_date(start_date),
            "UniDbQuery.To": cbr_dot_date(end_date),
        },
        encoding="utf-8",
    )

    rows: list[dict[str, object]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.DOTALL | re.IGNORECASE)
        if len(cells) < 2:
            continue
        date_text = html.unescape(re.sub(r"<[^>]+>", "", cells[0])).strip()
        rate_text = html.unescape(re.sub(r"<[^>]+>", "", cells[1])).strip()
        rows.append(
            {
                "date": pd.to_datetime(date_text, format="%d.%m.%Y", errors="coerce"),
                "key_rate": parse_float(rate_text),
            }
        )

    if not rows:
        raise RuntimeError("CBR key rate table was not found or parsed as empty")
    return standardize_series(pd.DataFrame(rows), "key_rate")


def fetch_yfinance_series(
    ticker: str,
    column: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    print(f"[download] yfinance {column} ({ticker})")
    start_text = start_date.strftime("%Y-%m-%d")
    # yfinance treats end as exclusive. Some tickers reject a tomorrow end date intraday,
    # so retry with the requested date itself before declaring the source unavailable.
    end_candidates = [
        (end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
        (end_date - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
    ]
    end_candidates = list(dict.fromkeys(end_candidates))

    raw = pd.DataFrame()
    for end_text in end_candidates:
        raw = yf.download(
            ticker,
            start=start_text,
            end=end_text,
            interval="1d",
            progress=False,
            auto_adjust=False,
        )
        if not raw.empty:
            break

        history = yf.Ticker(ticker).history(
            start=start_text,
            end=end_text,
            interval="1d",
            auto_adjust=False,
        )
        raw = history.copy()
        if not raw.empty:
            break

    if raw.empty:
        raise RuntimeError(f"yfinance returned empty data for {ticker}")

    if isinstance(raw.columns, pd.MultiIndex):
        if ticker in raw.columns.get_level_values(-1):
            raw = raw.xs(ticker, axis=1, level=-1)
        elif ticker in raw.columns.get_level_values(0):
            raw = raw.xs(ticker, axis=1, level=0)

    price_column = "Close" if "Close" in raw.columns else "Adj Close"
    if price_column not in raw.columns:
        raise RuntimeError(f"Neither Close nor Adj Close is available for {ticker}")

    df = raw[[price_column]].rename(columns={price_column: column}).copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    return standardize_series(df.reset_index(), column)


def fetch_moex_imoex(start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    print("[download] MOEX ISS IMOEX")
    base_url = "https://iss.moex.com/iss/history/engines/stock/markets/index/securities/IMOEX.json"
    start = 0
    all_parts: list[pd.DataFrame] = []

    while True:
        data = fetch_url_json(
            base_url,
            params={
                "from": start_date.strftime("%Y-%m-%d"),
                "till": end_date.strftime("%Y-%m-%d"),
                "start": start,
                "limit": 100,
                "iss.meta": "off",
                "history.columns": "TRADEDATE,CLOSE",
            },
        )
        history = data.get("history", {})
        rows = history.get("data", [])
        columns = history.get("columns", [])
        if not rows:
            break

        all_parts.append(pd.DataFrame(rows, columns=columns))

        cursor = data.get("history.cursor", {}).get("data", [])
        if cursor:
            _, total, page_size = cursor[0]
            start += int(page_size)
            if start >= int(total):
                break
        else:
            start += len(rows)

        time.sleep(0.05)

    if not all_parts:
        raise RuntimeError("MOEX ISS returned empty IMOEX history")

    raw = pd.concat(all_parts, ignore_index=True)
    df = raw.rename(columns={"TRADEDATE": "date", "CLOSE": "imoex"})
    return standardize_series(df, "imoex")


def load_local_inflation(path: Path) -> pd.DataFrame:
    print(f"[load] local inflation: {path}")
    raw = pd.read_csv(path, sep=";")
    if "date" not in raw.columns or "inflation" not in raw.columns:
        raise RuntimeError(f"{path} must contain date and inflation columns")

    month_start = pd.to_datetime("01." + raw["date"].astype(str).str.strip(), format="%d.%m.%Y", errors="coerce")
    df = pd.DataFrame(
        {
            # Publication dates are not present in the local source. To avoid look-ahead bias,
            # each monthly inflation value becomes available from the first day of the next month.
            "date": month_start + pd.offsets.MonthBegin(1),
            "inflation": raw["inflation"].map(parse_float),
        }
    )
    return standardize_series(df, "inflation")


def load_local_ofz(path: Path, period_column: str, column: str) -> pd.DataFrame:
    print(f"[load] local OFZ {column}: {path}")
    raw = pd.read_csv(path, sep=";", skiprows=1)
    if "tradedate" not in raw.columns or period_column not in raw.columns:
        raise RuntimeError(f"{path} must contain tradedate and {period_column} columns")

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["tradedate"], dayfirst=True, errors="coerce"),
            column: raw[period_column].map(parse_float),
        }
    )
    return standardize_series(df, column)


def reindex_and_fill(
    df: pd.DataFrame,
    column: str,
    daily_index: pd.DatetimeIndex,
    *,
    limit: int | None,
) -> pd.Series:
    if df.empty:
        return pd.Series(np.nan, index=daily_index, name=column)

    series = df.set_index("date")[column].sort_index()
    start = min(series.index.min(), daily_index.min())
    extended_index = pd.date_range(start, daily_index.max(), freq="D")
    filled = series.reindex(extended_index).ffill(limit=limit)
    return filled.reindex(daily_index).rename(column)


def choose_dataset_end(source_statuses: dict[str, SourceStatus], requested_end: pd.Timestamp) -> pd.Timestamp:
    market_max_dates = [
        status.max_date
        for column, status in source_statuses.items()
        if column in ["gold", "brent", "usd_rub", "eur_rub", "imoex", "vix", "sp500"] and status.max_date is not None
    ]
    if not market_max_dates:
        raise RuntimeError("No market source produced dated data")

    end_date = min(max(market_max_dates), requested_end).normalize()
    if end_date < START_DATE:
        raise RuntimeError(f"Calculated dataset end date {end_date.date()} is before {START_DATE.date()}")
    print(f"[merge] dataset daily range: {START_DATE.date()} -> {end_date.date()}")
    return end_date


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["ofz_spread_10_2"] = result["ofz_10y"] - result["ofz_2y"]

    usd_return = result["usd_rub"].pct_change(fill_method=None)
    result["usd_volatility"] = usd_return.rolling(30).std()

    imoex_return = result["imoex"].pct_change(fill_method=None)
    result["imoex_volatility"] = imoex_return.rolling(30).std()
    result["imoex_drawdown"] = result["imoex"] / result["imoex"].cummax() - 1

    rolling_mean = result["imoex"].rolling(252).mean()
    rolling_std = result["imoex"].rolling(252).std().replace(0, np.nan)
    result["imoex_zscore"] = (result["imoex"] - rolling_mean) / rolling_std

    result["real_key_rate"] = result["key_rate"] - result["inflation"]
    return result


def validate_final_dataset(
    df: pd.DataFrame,
    source_statuses: dict[str, SourceStatus] | None = None,
) -> ValidationResult:
    print("\n[validate] final dataset")
    critical_errors: list[str] = []
    warnings: list[str] = []

    if "date" not in df.columns:
        critical_errors.append("Column date is missing")
        return ValidationResult(critical_errors, warnings)

    dates = pd.to_datetime(df["date"], errors="coerce")
    duplicate_count = int(dates.duplicated().sum())
    sorted_ok = bool(dates.is_monotonic_increasing)
    expected_index = pd.date_range(dates.min(), dates.max(), freq="D")
    actual_index = pd.DatetimeIndex(dates.dropna())
    missing_dates = expected_index.difference(actual_index)

    print(f"  start date: {dates.min().date()}")
    print(f"  end date: {dates.max().date()}")
    print(f"  number of rows: {len(df)}")
    print(f"  number of columns: {len(df.columns)}")
    print(f"  duplicate dates: {duplicate_count}")
    print(f"  sorted by date: {sorted_ok}")
    print(f"  missing daily dates: {len(missing_dates)}")

    if duplicate_count:
        critical_errors.append(f"Duplicate date rows: {duplicate_count}")
    if not sorted_ok:
        critical_errors.append("Dates are not sorted")
    if len(missing_dates):
        critical_errors.append(f"Daily index has {len(missing_dates)} missing dates")

    missing_columns = [column for column in FINAL_COLUMNS if column not in df.columns]
    if missing_columns:
        critical_errors.append(f"Missing final columns: {', '.join(missing_columns)}")

    for column in REQUIRED_NONEMPTY_COLUMNS:
        if column in df.columns and df[column].isna().all():
            critical_errors.append(f"Important column is fully empty: {column}")

    if "usd_rub" in df.columns and (df["usd_rub"].dropna() < 20).any():
        critical_errors.append("usd_rub has values < 20")
    if "eur_rub" in df.columns and (df["eur_rub"].dropna() < 20).any():
        critical_errors.append("eur_rub has values < 20")

    for column in POSITIVE_COLUMNS:
        if column in df.columns and (df[column].dropna() <= 0).any():
            critical_errors.append(f"{column} has non-positive values")

    print("\n[validate] stickiness check, last 60 calendar days")
    recent_cutoff = dates.max() - pd.Timedelta(days=60)
    for column in STICKINESS_COLUMNS:
        if column not in df.columns:
            continue
        recent = df.loc[dates >= recent_cutoff, column].dropna()
        unique_count = int(recent.nunique())
        print(f"  {column}: unique_last_60d={unique_count}")
        if unique_count <= 5:
            message = f"{column} may be stuck: only {unique_count} unique values in last 60 days"
            warnings.append(message)
            if column == "imoex":
                critical_errors.append("IMOEX is stuck in the last 60 days")

    if source_statuses:
        print("\n[validate] source freshness")
        end_date = dates.max().normalize()
        for column, status in source_statuses.items():
            if status.max_date is None:
                message = f"{column}: source has no real observations"
                warnings.append(message)
                print(f"  WARNING {message}")
                continue
            stale_days = int((end_date - status.max_date.normalize()).days)
            print(f"  {column}: last_real_update={status.max_date.date()}, stale_days={stale_days}")
            if stale_days > STALE_SOURCE_DAYS:
                warnings.append(f"{column}: last real update is {stale_days} days before dataset end")

    print("\n[validate] missing values")
    missing_table = pd.DataFrame(
        {
            "missing_count": df.isna().sum(),
            "missing_pct": (df.isna().sum() / len(df) * 100).round(2),
        }
    )
    print(missing_table.to_string())

    print("\n[validate] numeric min/max")
    numeric_minmax = df.select_dtypes(include=[np.number]).agg(["min", "max"]).T
    print(numeric_minmax.to_string())

    if warnings:
        print("\n[validate] warnings")
        for warning in warnings:
            print(f"  WARNING: {warning}")

    if critical_errors:
        print("\n[validate] critical errors")
        for error in critical_errors:
            print(f"  ERROR: {error}")
    else:
        print("\n[validate] OK: no critical errors")

    return ValidationResult(critical_errors, warnings)


def run_connectivity_checks(end_date: pd.Timestamp) -> None:
    print("[connectivity] CBR API for USD/RUB")
    sample_start = max(START_DATE, end_date - pd.Timedelta(days=14))
    usd = fetch_cbr_currency_series("R01235", "usd_rub", sample_start, end_date)
    print(f"  CBR USD/RUB sample rows={len(usd)}, last={usd.tail(1).to_dict('records')}")

    print("[connectivity] MOEX ISS IMOEX after 2024-07-12")
    data = fetch_url_json(
        "https://iss.moex.com/iss/history/engines/stock/markets/index/securities/IMOEX.json",
        params={
            "from": "2024-07-12",
            "till": end_date.strftime("%Y-%m-%d"),
            "limit": 100,
            "iss.meta": "off",
            "history.columns": "TRADEDATE,CLOSE",
        },
    )
    rows = data.get("history", {}).get("data", [])
    columns = data.get("history", {}).get("columns", [])
    imoex_sample = pd.DataFrame(rows, columns=columns)
    unique_count = int(pd.to_numeric(imoex_sample.get("CLOSE"), errors="coerce").nunique())
    print(f"  MOEX IMOEX sample rows={len(imoex_sample)}, unique_close={unique_count}")
    if unique_count <= 5:
        raise RuntimeError("MOEX IMOEX connectivity check suggests a stuck series")

    print("[connectivity] yfinance for gold/brent/vix/sp500")
    yf_start = max(START_DATE, end_date - pd.Timedelta(days=21))
    for column, ticker in YFINANCE_TICKERS.items():
        sample = fetch_yfinance_series(ticker, column, yf_start, end_date)
        min_date = sample["date"].min().date() if not sample.empty else "n/a"
        max_date = sample["date"].max().date() if not sample.empty else "n/a"
        print(f"  {column} ({ticker}): rows={len(sample)}, min_date={min_date}, max_date={max_date}")


def build_dataset(project_dir: Path, end_date: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, SourceStatus]]:
    source_frames: dict[str, pd.DataFrame] = {}
    source_statuses: dict[str, SourceStatus] = {}

    for column, currency_id in CBR_CURRENCIES.items():
        df = fetch_cbr_currency_series(currency_id, column, START_DATE, end_date)
        source_frames[column] = df
        source_statuses[column] = source_status(column, df)

    key_rate = fetch_cbr_key_rate(CBR_LOOKBACK_DATE, end_date)
    source_frames["key_rate"] = key_rate
    source_statuses["key_rate"] = source_status("key_rate", key_rate)

    inflation = load_local_inflation(project_dir / "data" / "inflation_key_rate.csv")
    source_frames["inflation"] = inflation
    source_statuses["inflation"] = source_status("inflation", inflation)

    for column, ticker in YFINANCE_TICKERS.items():
        df = fetch_yfinance_series(ticker, column, START_DATE, end_date)
        source_frames[column] = df
        source_statuses[column] = source_status(column, df)

    imoex = fetch_moex_imoex(START_DATE, end_date)
    source_frames["imoex"] = imoex
    source_statuses["imoex"] = source_status("imoex", imoex)

    for column, (relative_path, period_column) in OFZ_FILES.items():
        df = load_local_ofz(project_dir / relative_path, period_column, column)
        source_frames[column] = df
        source_statuses[column] = source_status(column, df)

    dataset_end = choose_dataset_end(source_statuses, end_date)
    daily_index = pd.date_range(START_DATE, dataset_end, freq="D")

    market_columns = ["gold", "brent", "usd_rub", "eur_rub", "imoex", "vix", "sp500"]
    ofz_columns = ["ofz_1y", "ofz_2y", "ofz_5y", "ofz_10y"]
    macro_columns = ["key_rate", "inflation"]

    merged = pd.DataFrame(index=daily_index)
    merged.index.name = "date"

    for column in [*market_columns, *ofz_columns]:
        merged[column] = reindex_and_fill(source_frames[column], column, daily_index, limit=FFILL_LIMIT_DAYS)

    for column in macro_columns:
        merged[column] = reindex_and_fill(source_frames[column], column, daily_index, limit=None)

    print("\n[merge] missing values after source merge, before derived features")
    print(merged.isna().sum().to_string())

    final_df = merged.reset_index()
    final_df = add_derived_features(final_df)
    final_df = final_df[FINAL_COLUMNS]
    return final_df, source_statuses


def save_final_dataset(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_df = df.copy()
    save_df["date"] = pd.to_datetime(save_df["date"]).dt.strftime("%Y-%m-%d")
    save_df.to_csv(output_path, index=False)
    print(f"\n[save] wrote {output_path}")


def print_final_checks(df: pd.DataFrame) -> None:
    print("\n[output] first 5 rows")
    print(df.head(5).to_string(index=False))

    print("\n[output] last 10 rows")
    print(df.tail(10).to_string(index=False))

    print("\n[output] last 20 IMOEX values")
    print(df[["date", "imoex"]].tail(20).to_string(index=False))

    recent_cutoff = df["date"].max() - pd.Timedelta(days=60)
    imoex_unique_last_60 = int(df.loc[df["date"] >= recent_cutoff, "imoex"].dropna().nunique())
    print(f"\n[output] IMOEX unique values in last 60 days: {imoex_unique_last_60}")
    print(f"[output] min usd_rub: {df['usd_rub'].min(skipna=True)}")
    print(f"[output] min eur_rub: {df['eur_rub'].min(skipna=True)}")


def print_manual_download_instructions() -> None:
    print("\nManual files needed if internet is unavailable:")
    print("- CBR XML_dynamic USD/RUB: VAL_NM_RQ=R01235, date_req1=01/01/2014, date_req2=<today>")
    print("- CBR XML_dynamic EUR/RUB: VAL_NM_RQ=R01239, date_req1=01/01/2014, date_req2=<today>")
    print("- CBR key rate HTML table: /hd_base/KeyRate/ from 01.01.2013 to <today>")
    print("- MOEX ISS IMOEX history JSON with TRADEDATE,CLOSE and pagination via start")
    print("- Yahoo Finance daily Close for GC=F, BZ=F, ^VIX, ^GSPC")
    print("- Existing local files: data/inflation_key_rate.csv and data/moex/ofz_*.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild data/final_dataset.csv for the IVR dashboard.")
    parser.add_argument("--start-date", default=START_DATE.strftime("%Y-%m-%d"), help="Dataset start date.")
    parser.add_argument("--end-date", default=dt.date.today().isoformat(), help="Latest date to request from sources.")
    parser.add_argument("--skip-connectivity-checks", action="store_true", help="Skip short source connectivity tests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    global START_DATE
    START_DATE = pd.Timestamp(args.start_date).normalize()

    requested_end = pd.Timestamp(args.end_date).normalize()
    today = pd.Timestamp(dt.date.today()).normalize()
    if requested_end > today:
        print(f"[warning] requested end date {requested_end.date()} is in the future; using {today.date()}")
        requested_end = today

    project_dir = project_root()
    output_path = project_dir / "data" / "final_dataset.csv"

    try:
        if not args.skip_connectivity_checks:
            run_connectivity_checks(requested_end)

        df, source_statuses = build_dataset(project_dir, requested_end)
        validation = validate_final_dataset(df, source_statuses)
        if not validation.ok:
            print("\n[save] skipped because validate_final_dataset found critical errors")
            return 2

        save_final_dataset(df, output_path)
        print_final_checks(df)
        return 0
    except Exception as exc:
        print(f"\n[error] Could not rebuild final dataset: {exc}", file=sys.stderr)
        print("[error] data/final_dataset.csv was not saved by this run", file=sys.stderr)
        print_manual_download_instructions()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
