"""Build monthly crisis-prediction dataset.

Output: data/processed/dataset_monthly.csv
Log:    data/processed/BUILD_LOG.md
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
RAW = DATA / "raw"
PROCESSED.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

START = "2003-01-01"
END = date.today().isoformat()

LOG: list[str] = []
WARN: list[str] = []


def log(msg: str) -> None:
    print(msg)
    LOG.append(msg)


def warn(msg: str) -> None:
    print(f"WARN: {msg}")
    WARN.append(msg)


# ---------------------------------------------------------------- monthly grid
months = pd.date_range(start=START, end=END, freq="MS")
grid = pd.DataFrame({"date": months})
log(f"Monthly grid: {months.min().date()} .. {months.max().date()}  ({len(months)} rows)")


# ---------------------------------------------------------------- yfinance helpers
def yf_download(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, start=START, end=END, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df.index = pd.to_datetime(df.index)
    return df


def month_start(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return idx.to_period("M").to_timestamp()


# ---------------------------------------------------------------- ^VIX
log("\n=== ^VIX ===")
vix = yf_download("^VIX")
if vix.empty:
    warn("yfinance returned empty for ^VIX")
    grid["vix_mean"] = np.nan
else:
    log(f"  rows={len(vix)}  range={vix.index.min().date()}..{vix.index.max().date()}")
    s = vix["Close"].copy()
    s.index = month_start(s.index)
    vix_mean = s.groupby(level=0).mean().rename("vix_mean")
    grid = grid.merge(vix_mean.reset_index().rename(columns={"index": "date", "Date": "date"}), on="date", how="left")

grid["vix_zscore"] = (
    (grid["vix_mean"] - grid["vix_mean"].rolling(36, min_periods=36).mean())
    / grid["vix_mean"].rolling(36, min_periods=36).std()
)


# ---------------------------------------------------------------- USDRUB=X
log("\n=== USDRUB=X ===")
usd = yf_download("USDRUB=X")
if usd.empty:
    warn("yfinance returned empty for USDRUB=X")
    grid["usdrub_vol"] = np.nan
else:
    log(f"  rows={len(usd)}  range={usd.index.min().date()}..{usd.index.max().date()}")
    px = usd["Close"].dropna().astype(float)
    logret = np.log(px / px.shift(1))
    logret.index = month_start(logret.index)
    usdrub_vol = logret.groupby(level=0).std().rename("usdrub_vol")
    grid = grid.merge(usdrub_vol.reset_index().rename(columns={"index": "date", "Date": "date"}), on="date", how="left")

grid["usdrub_zscore"] = (
    (grid["usdrub_vol"] - grid["usdrub_vol"].rolling(36, min_periods=36).mean())
    / grid["usdrub_vol"].rolling(36, min_periods=36).std()
)


# ---------------------------------------------------------------- IMOEX.ME
log("\n=== IMOEX.ME ===")
imoex = yf_download("IMOEX.ME")
if imoex.empty:
    warn("yfinance returned empty for IMOEX.ME — imoex_return/imoex_vol = NaN")
    grid["imoex_return"] = np.nan
    grid["imoex_vol"] = np.nan
else:
    last_dt = imoex.index.max().date()
    log(f"  rows={len(imoex)}  range={imoex.index.min().date()}..{last_dt}")
    if last_dt < date.today().replace(day=1):
        warn(f"IMOEX.ME data ends {last_dt} — months after that will be NaN")
    px = imoex["Close"].dropna().astype(float)
    logret = np.log(px / px.shift(1))
    logret.index = month_start(logret.index)
    imoex_vol = logret.groupby(level=0).std().rename("imoex_vol")

    monthly_last = px.copy()
    monthly_last.index = month_start(monthly_last.index)
    monthly_last = monthly_last.groupby(level=0).last()
    imoex_return = (monthly_last.pct_change() * 100.0).rename("imoex_return")

    grid = grid.merge(imoex_return.reset_index().rename(columns={"index": "date", "Date": "date"}), on="date", how="left")
    grid = grid.merge(imoex_vol.reset_index().rename(columns={"index": "date", "Date": "date"}), on="date", how="left")


# ---------------------------------------------------------------- IMOEX gap-fill via MOEX ISS
# yfinance covers только 2013-03..2024-06; MOEX ISS отдаёт IMOEX начиная с 2003-01-04
# (биржа ретроспективно достроила индекс). Альтернативный тикер MICEXINDEXCF в ISS
# пустой — проверено (см. лог), поэтому используем сам IMOEX.
log("\n=== IMOEX gap-fill via MOEX ISS ===")
try:
    import urllib.request

    # quick probe of the historical fallback ticker MICEXINDEXCF, log result
    try:
        probe_url = "https://iss.moex.com/iss/history/engines/stock/markets/index/securities/MICEXINDEXCF.json?from=2003-01-01&till=2013-03-01"
        with urllib.request.urlopen(probe_url, timeout=30) as r:
            probe = json.load(r)
        probe_total = probe.get("history.cursor", {}).get("data", [[0, 0, 0]])[0][1]
        log(f"  probe MICEXINDEXCF 2003..2013: total rows={probe_total} → {'use it' if probe_total else 'empty, fall back to IMOEX'}")
    except Exception as _e:
        log(f"  probe MICEXINDEXCF failed: {_e!r}")

    iss_from = "2003-01-01"
    iss_till = END
    iss_base = "https://iss.moex.com/iss/history/engines/stock/markets/index/securities/IMOEX.json"

    iss_rows: list[list] = []
    iss_cols: list[str] | None = None
    start_idx = 0
    while True:
        url = f"{iss_base}?from={iss_from}&till={iss_till}&start={start_idx}"
        with urllib.request.urlopen(url, timeout=60) as r:
            page = json.load(r)
        hist = page["history"]
        if iss_cols is None:
            iss_cols = hist["columns"]
        rows = hist["data"]
        if not rows:
            break
        iss_rows.extend(rows)
        cur = page.get("history.cursor", {}).get("data", [[0, 0, 100]])[0]
        idx, total, pagesize = cur
        if idx + pagesize >= total:
            break
        start_idx = idx + pagesize

    if iss_rows:
        iss_df = pd.DataFrame(iss_rows, columns=iss_cols)
        iss_df["TRADEDATE"] = pd.to_datetime(iss_df["TRADEDATE"])
        iss_df = iss_df[["TRADEDATE", "CLOSE"]].dropna().sort_values("TRADEDATE")
        log(f"  ISS daily rows={len(iss_df)}  range={iss_df['TRADEDATE'].min().date()}..{iss_df['TRADEDATE'].max().date()}")

        iss_px = iss_df.set_index("TRADEDATE")["CLOSE"].astype(float)
        iss_logret = np.log(iss_px / iss_px.shift(1))
        iss_logret.index = month_start(iss_logret.index)
        iss_vol = iss_logret.groupby(level=0).std()

        iss_pm = iss_px.copy()
        iss_pm.index = month_start(iss_pm.index)
        iss_last = iss_pm.groupby(level=0).last()
        iss_ret = iss_last.pct_change() * 100.0

        fill = pd.DataFrame({"date": iss_vol.index, "imoex_vol_iss": iss_vol.values, "imoex_return_iss": iss_ret.reindex(iss_vol.index).values})
        grid = grid.merge(fill, on="date", how="left")
        grid["imoex_return"] = grid["imoex_return"].fillna(grid["imoex_return_iss"])
        grid["imoex_vol"] = grid["imoex_vol"].fillna(grid["imoex_vol_iss"])
        grid = grid.drop(columns=["imoex_return_iss", "imoex_vol_iss"])
    else:
        warn("MOEX ISS returned empty")
except Exception as e:
    warn(f"MOEX ISS gap-fill failed: {e!r}")


# ---------------------------------------------------------------- FED FUNDS
log("\n=== fed_rate ===")
fed_loaded = False
try:
    from pandas_datareader import data as pdr  # type: ignore

    fed = pdr.DataReader("FEDFUNDS", "fred", START, END)
    fed.index = month_start(fed.index)
    grid = grid.merge(
        fed["FEDFUNDS"].rename("fed_rate").reset_index().rename(columns={"DATE": "date", "index": "date"}),
        on="date",
        how="left",
    )
    log(f"  FRED FEDFUNDS: {len(fed)} rows, {fed.index.min().date()}..{fed.index.max().date()}")
    fed_loaded = True
except Exception as e:
    warn(f"pandas_datareader/FRED failed: {e!r}")

if not fed_loaded:
    # fallback: ^IRX (13-week T-bill yield, daily) — close enough as Fed proxy
    try:
        irx = yf_download("^IRX")
        if not irx.empty:
            s = irx["Close"].dropna().astype(float)
            s.index = month_start(s.index)
            fed_rate = s.groupby(level=0).last().rename("fed_rate")
            grid = grid.merge(fed_rate.reset_index().rename(columns={"index": "date", "Date": "date"}), on="date", how="left")
            log(f"  fallback ^IRX: {len(irx)} rows, {irx.index.min().date()}..{irx.index.max().date()}")
            fed_loaded = True
        else:
            warn("^IRX returned empty")
    except Exception as e:
        warn(f"^IRX download failed: {e!r}")

if not fed_loaded:
    grid["fed_rate"] = np.nan
    warn("fed_rate set to NaN (both FRED and ^IRX failed)")


# ---------------------------------------------------------------- CBR key rate + CPI (2013+)
log("\n=== inflation_key_rate.csv → cbr_rate (2013+), cpi_russia ===")
ikr_path = DATA / "inflation_key_rate.csv"
ikr = pd.read_csv(ikr_path, sep=";", decimal=",")
ikr["date"] = pd.to_datetime(ikr["date"], format="%m.%Y")
ikr = ikr.sort_values("date").reset_index(drop=True)
log(f"  rows={len(ikr)}  range={ikr['date'].min().date()}..{ikr['date'].max().date()}")
grid = grid.merge(ikr[["date", "inflation"]].rename(columns={"inflation": "cpi_russia"}), on="date", how="left")
cbr_modern = ikr[["date", "key_rate"]].rename(columns={"key_rate": "cbr_rate_modern"})


# ---------------------------------------------------------------- CBR refinancing rate 2003-2013 (manual file)
log("\n=== data/refin_index.csv → cbr_rate (2003..2013) ===")
cbr_old_path = DATA / "refin_index.csv"
cbr_old_series: pd.Series | None = None

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

def parse_russian_date(s: str):
    s = s.replace("\xa0", " ").replace("г.", "").strip()
    parts = s.split()
    if len(parts) < 3:
        return None
    try:
        d = int(parts[0])
        m = RU_MONTHS.get(parts[1].lower())
        y = int(parts[2])
    except (ValueError, KeyError):
        return None
    if m is None:
        return None
    return pd.Timestamp(year=y, month=m, day=d)

if cbr_old_path.exists():
    try:
        events: list[tuple[pd.Timestamp, float]] = []
        with open(cbr_old_path, encoding="utf-8") as fh:
            lines = fh.readlines()
        # row 0: header, row 1: "С 1 января 2016 г." (transition to key rate) — skip both
        for ln in lines[2:]:
            cols = ln.rstrip("\n").split(";")
            if len(cols) < 2:
                continue
            period_str = cols[0].replace("\xa0", " ").strip()
            rate_str = cols[1].strip().replace(",", ".")
            if not period_str or not rate_str:
                continue
            # split on en-dash U+2013 (or em-dash U+2014 just in case)
            left = period_str.split("–")[0].split("—")[0].strip()
            d = parse_russian_date(left)
            if d is None:
                continue
            try:
                rate = float(rate_str)
            except ValueError:
                continue
            events.append((d, rate))
        events.sort(key=lambda x: x[0])
        if not events:
            warn("refin_index.csv: no parseable rows")
        else:
            ev_df = pd.DataFrame(events, columns=["date", "rate"]).drop_duplicates("date", keep="last")
            daily = pd.Series(ev_df["rate"].values, index=pd.DatetimeIndex(ev_df["date"]))
            full_daily = daily.reindex(pd.date_range(daily.index.min(), date.today(), freq="D")).ffill()
            monthly = full_daily.resample("MS").last()
            cbr_old_series = monthly.rename("cbr_rate_old")
            log(f"  parsed {len(events)} rate-change events, monthly series {monthly.index.min().date()}..{monthly.index.max().date()}")
    except Exception as e:
        warn(f"failed to parse {cbr_old_path}: {e!r}")
else:
    warn(f"{cbr_old_path} not present — cbr_rate for 2003..2013 will be NaN")


# combine: pre-2013-09 use refinancing rate, from 2013-09 onward use key_rate
modern_start = cbr_modern["date"].min() if len(cbr_modern) else pd.Timestamp("2014-01-01")
grid = grid.merge(cbr_modern, on="date", how="left")
if cbr_old_series is not None:
    old_df = cbr_old_series.reset_index()
    old_df.columns = ["date", "cbr_rate_old"]
    grid = grid.merge(old_df, on="date", how="left")
else:
    grid["cbr_rate_old"] = np.nan

grid["cbr_rate"] = np.where(grid["date"] >= modern_start, grid["cbr_rate_modern"], grid["cbr_rate_old"])
grid = grid.drop(columns=["cbr_rate_modern", "cbr_rate_old"])


# ---------------------------------------------------------------- OFZ spread (10y - 2y)
log("\n=== ofz_2y, ofz_10y → ofz_spread ===")
def read_ofz(path: Path) -> pd.Series:
    df = pd.read_csv(path, sep=";", decimal=",", skiprows=2)
    df["date"] = pd.to_datetime(df["tradedate"], format="%d.%m.%Y")
    val_col = [c for c in df.columns if c.startswith("period")][0]
    return df.set_index("date")[val_col].sort_index()

ofz2 = read_ofz(DATA / "moex" / "ofz_2y.csv")
ofz10 = read_ofz(DATA / "moex" / "ofz_10y.csv")
log(f"  ofz_2y:  {len(ofz2)} rows, {ofz2.index.min().date()}..{ofz2.index.max().date()}")
log(f"  ofz_10y: {len(ofz10)} rows, {ofz10.index.min().date()}..{ofz10.index.max().date()}")
spread_daily = (ofz10 - ofz2).dropna()
spread_daily.index = month_start(spread_daily.index)
ofz_spread = spread_daily.groupby(level=0).mean().rename("ofz_spread")
grid = grid.merge(ofz_spread.reset_index().rename(columns={"index": "date", "date": "date"}), on="date", how="left")


# ---------------------------------------------------------------- ofz_spread_proxy / ofz_spread_filled
# ZCYC начинается 2014-01; для 2003..2013 (включая GFC 2008) ofz_spread = NaN.
# Прокси: cbr_rate - fed_rate — грубо отражает разницу страновых ставок и
# часть risk-premium на ОФЗ. Не эквивалент term-spread'у, но лучше пустоты.
log("\n=== ofz_spread_proxy = cbr_rate - fed_rate ===")
grid["ofz_spread_proxy"] = grid["cbr_rate"] - grid["fed_rate"]
grid["ofz_spread_filled"] = grid["ofz_spread"].where(grid["ofz_spread"].notna(), grid["ofz_spread_proxy"])
_n_filled = int(grid["ofz_spread"].isna().sum() - grid["ofz_spread_filled"].isna().sum())
log(f"  proxy values filled: {_n_filled} months; ofz_spread_filled NaN={int(grid['ofz_spread_filled'].isna().sum())}")


# ---------------------------------------------------------------- velocity features
# Скорости/ускорения: ловят момент смены режима лучше, чем уровни.
# Все рассчитываются на отсортированной по date сетке (grid уже отсортирован при создании).
log("\n=== velocity features ===")
grid = grid.sort_values("date").reset_index(drop=True)
grid["cbr_rate_delta"]  = grid["cbr_rate"]  - grid["cbr_rate"].shift(1)
grid["cbr_rate_delta3"] = grid["cbr_rate"]  - grid["cbr_rate"].shift(3)
grid["fed_rate_delta"]  = grid["fed_rate"]  - grid["fed_rate"].shift(1)
grid["fed_rate_delta3"] = grid["fed_rate"]  - grid["fed_rate"].shift(3)
grid["vix_delta"]       = grid["vix_mean"]  - grid["vix_mean"].shift(1)
grid["imoex_drawdown"]  = grid["imoex_return"].rolling(3).sum()
grid["usdrub_accel"]    = grid["usdrub_vol"] - grid["usdrub_vol"].shift(2)
log("  added: cbr_rate_delta, cbr_rate_delta3, fed_rate_delta, fed_rate_delta3, "
    "vix_delta, imoex_drawdown, usdrub_accel")


# ---------------------------------------------------------------- placeholders
grid["bis_credit_gap"] = np.nan
grid["news_sentiment"] = np.nan


# ---------------------------------------------------------------- label
# Метки проставляются по внешним источникам (NBER, ЦБ РФ, исторические события).
# См. docs/LABELING_METHODOLOGY.md для обоснований и источников.
# Правило при пересечении: красный (2) побеждает жёлтый (1).
LABEL_RED = [
    ("2008-09-01", "2009-06-01", "GFC: NBER recession + рецессия в РФ"),
    ("2014-12-01", "2015-03-01", "Крымский кризис, ЦБ → 17%"),
    ("2020-03-01", "2020-05-01", "COVID (NBER recession)"),
    ("2022-02-01", "2022-09-01", "Санкционный шок 2022, ЦБ → 20%"),
]
LABEL_YELLOW = [
    ("2008-05-01", "2008-08-01", "Нарастание перед GFC, нефть на пике"),
    ("2011-08-01", "2011-11-01", "Кризис еврозоны, отток капитала"),
    ("2013-05-01", "2013-08-01", "Taper tantrum ФРС"),
    ("2018-04-01", "2018-08-01", "Санкции против Русала"),
    ("2021-10-01", "2021-12-01", "Геополитическая напряжённость перед 2022"),
]
log("\n=== label ===")
grid["label"] = 0
for s, e, _ in LABEL_YELLOW:
    grid.loc[(grid["date"] >= s) & (grid["date"] <= e), "label"] = 1
for s, e, _ in LABEL_RED:
    grid.loc[(grid["date"] >= s) & (grid["date"] <= e), "label"] = 2
_lc = grid["label"].value_counts().sort_index()
log(f"  label=0: {int(_lc.get(0,0))}  label=1: {int(_lc.get(1,0))}  label=2: {int(_lc.get(2,0))}")


# ---------------------------------------------------------------- final order
final_cols = [
    "date",
    "vix_mean", "vix_zscore", "vix_delta",
    "fed_rate", "fed_rate_delta", "fed_rate_delta3",
    "cbr_rate", "cbr_rate_delta", "cbr_rate_delta3",
    "cpi_russia",
    "usdrub_vol", "usdrub_zscore", "usdrub_accel",
    "imoex_return", "imoex_vol", "imoex_drawdown",
    "ofz_spread", "ofz_spread_proxy", "ofz_spread_filled",
    "bis_credit_gap", "news_sentiment", "label",
]
grid = grid[final_cols].sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------- save
out_csv = PROCESSED / "dataset_monthly.csv"
grid.to_csv(out_csv, index=False)
log(f"\nSaved {out_csv}  shape={grid.shape}")


# ---------------------------------------------------------------- summary
print("\n" + "=" * 70)
print("FIRST 5 ROWS")
print(grid.head().to_string())
print("\nLAST 5 ROWS")
print(grid.tail().to_string())

nan_pct = (grid.isna().sum() / len(grid) * 100).round(2)
print("\nNaN % per column")
for c, v in nan_pct.items():
    print(f"  {c:18s} {v:6.2f}%")

print(f"\nTotal rows: {len(grid)}   Range: {grid['date'].min().date()} .. {grid['date'].max().date()}")


# ---------------------------------------------------------------- BUILD_LOG.md
build_log = PROCESSED / "BUILD_LOG.md"
sources_loaded: list[str] = []
sources_failed: list[str] = []

if not vix.empty:
    sources_loaded.append(f"- yfinance ^VIX → vix_mean, vix_zscore ({vix.index.min().date()}..{vix.index.max().date()}, {len(vix)} дневных строк)")
else:
    sources_failed.append("- yfinance ^VIX — пустой ответ")

if not usd.empty:
    sources_loaded.append(f"- yfinance USDRUB=X → usdrub_vol, usdrub_zscore ({usd.index.min().date()}..{usd.index.max().date()}, {len(usd)} дневных строк)")
else:
    sources_failed.append("- yfinance USDRUB=X — пустой ответ")

if not imoex.empty:
    sources_loaded.append(f"- yfinance IMOEX.ME → imoex_return, imoex_vol ({imoex.index.min().date()}..{imoex.index.max().date()}, {len(imoex)} дневных строк)")
else:
    sources_failed.append("- yfinance IMOEX.ME — пустой ответ")

if fed_loaded:
    sources_loaded.append("- FRED FEDFUNDS (через pandas_datareader) → fed_rate" if "FRED FEDFUNDS" in "\n".join(LOG) else "- ^IRX (fallback) → fed_rate")
else:
    sources_failed.append("- fed_rate — ни FRED, ни ^IRX недоступны; колонка NaN")

sources_loaded.append(f"- data/inflation_key_rate.csv → cbr_rate (2013+), cpi_russia ({ikr['date'].min().date()}..{ikr['date'].max().date()})")

if cbr_old_series is not None:
    sources_loaded.append(f"- data/refin_index.csv → cbr_rate (2003..{modern_start.date()}, ставка рефинансирования ЦБ РФ, ffill по месяцам)")
else:
    sources_failed.append("- data/refin_index.csv не загружен → cbr_rate до 2013 = NaN")

sources_loaded.append(f"- data/moex/ofz_2y.csv + ofz_10y.csv → ofz_spread (среднее (10y-2y) за месяц), {ofz2.index.min().date()}..{ofz2.index.max().date()}")
sources_loaded.append("- MOEX ISS API (iss.moex.com) → gap-fill IMOEX после 2024-06-14 (дневные свечи)")

manual_todo = [
    "- **bis_credit_gap** — выкачать BIS credit-to-GDP gap (квартальные данные, www.bis.org/statistics/c_gaps.htm), линейно интерполировать на месяцы",
    "- **news_sentiment** — собрать через GDELT или RSS-архив РБК/Коммерсанта/Интерфакса + FinBERT/LLM-разметку",
    "- **label (0/1/2)** — выбрать определение кризиса (например, по imoex_drawdown, vix_zscore, ofz_spread) и проставить",
]
if cbr_old_series is None:
    manual_todo.insert(0, "- **cbr_rate 2003..2013** — положить data/refin_index.csv (Период действия;Ставка;Норм. документ)")
if imoex.empty or (not imoex.empty and imoex.index.max().date() < date.today().replace(day=1)):
    last_im = imoex.index.max().date() if not imoex.empty else "—"
    manual_todo.append(f"- **imoex после {last_im}** — yfinance не отдаёт; источник MOEX ISS API (`iss.moex.com/iss/history/.../IMOEX.json`)")

shape_str = f"{grid.shape[0]} rows × {grid.shape[1]} cols"
range_str = f"{grid['date'].min().date()} .. {grid['date'].max().date()}"
nan_table = "| колонка | % NaN |\n|---|---:|\n" + "\n".join(
    f"| {c} | {v:.2f} |" for c, v in nan_pct.items()
)

content = f"""# BUILD_LOG — dataset_monthly.csv

Сгенерировано: {date.today().isoformat()}  (скрипт `scripts/build_monthly_dataset.py`)

## Что загружено и откуда

{chr(10).join(sources_loaded)}

## Что не получилось (и почему)

{chr(10).join(sources_failed) if sources_failed else "_всё, что предполагалось, загрузилось_"}

## Итоговый датасет

- **Shape:** {shape_str}
- **Диапазон дат:** {range_str}
- **Гранулярность:** месячная, `date` = первый день месяца

### % NaN по каждой колонке

{nan_table}

## Что нужно добавить вручную

{chr(10).join(manual_todo)}

## Замечания по агрегации

- `vix_mean` — среднее дневного `Close` за месяц
- `vix_zscore`, `usdrub_zscore` — скользящее окно 36 мес (первые 35 значений NaN — это нормально)
- `usdrub_vol`, `imoex_vol` — std дневных log-returns внутри месяца
- `imoex_return` — % изменение last-of-month `Close`
- `cbr_rate` — last значение за месяц; до {modern_start.date()} — refinancing rate (ffill событий по дням), с {modern_start.date()} — ключевая ставка из inflation_key_rate.csv
- `cpi_russia` — month-end значение из inflation_key_rate.csv (как есть)
- `ofz_spread` — среднее (period_10.0 − period_2.0) за месяц
"""

build_log.write_text(content, encoding="utf-8")
print(f"\nBUILD_LOG written to {build_log}")
