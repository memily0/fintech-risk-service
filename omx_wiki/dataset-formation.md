# Dataset Formation

This document describes how `data/final_dataset.csv` is formed for MVP-1.0.
The current goal is not to maximize the number of variables, but to build a
long, auditable daily macrofinancial history for the first crisis early-warning
model.

## Output

The final file is `data/final_dataset.csv`.

Current rebuilt range:

- start: `2003-01-01`;
- end: `2026-06-07`;
- frequency: daily calendar index;
- rows: `8559`;
- columns: `20`.

The dataset is rebuilt by:

```bash
python scripts/build_final_dataset.py --start-date 2003-01-01
python scripts/train_crisis_model.py
```

## Raw Sources

### USD/RUB and EUR/RUB

Source: Bank of Russia XML currency API.

- URL: `https://www.cbr.ru/scripts/XML_dynamic.asp`
- USD/RUB id: `R01235`
- EUR/RUB id: `R01239`
- fields used: `Record/@Date`, `VunitRate` or `Value/Nominal`
- transformation: normalize to one unit of currency, parse as daily rate.

### Key Rate

Source: Bank of Russia monetary policy rates table.

- URL: `https://www.cbr.ru/eng/hd_base/procstav/ir_chg_mpo/full/`
- query range: from `2003-01-01` to requested end date;
- field used after key-rate launch: `Key rate`;
- fallback before key-rate history: `Refinancing Rate`;
- transformation: one policy-rate series named `key_rate`.

Current source coverage:

- first observation: `2003-02-17`;
- last observation: `2026-04-27`.

### Inflation

Source: Rosstat CPI data exposed through NSEDC.

- dataset: `rsdocs_1031000110063`;
- dataset page: `https://repository.nsedc.ru/dataset/rsdocs_1031000110063`;
- source publication: `https://rosstat.gov.ru/compendium/document/50802`;
- loaded resource: newest matching `rsdocs_1031000110063_ind_*.csv.gz`;
- required columns: `date`, `obs`, `frequency`.

The loader intentionally uses the separate CPI index dataset, not the wider CPI
goods/services dataset, because the wider dataset contains several comparison
bases in the same month without enough structure for safe automatic selection.

For each month this CPI dataset has two monthly rows. The second row is the CPI
year-over-year index. The dataset stores:

```text
inflation = CPI YoY index - 100
```

To reduce look-ahead bias, the period-end monthly CPI value is shifted to the
first day of the next month before daily forward-fill.

Current final coverage:

- first available final date: `2003-01-01`;
- missing values after merge: `0`.

### Brent

Source: EIA Europe Brent Spot Price FOB.

- URL: `https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls`;
- source key: `RBRTE`;
- units: dollars per barrel;
- transformation: read the `Data 1` worksheet and keep the daily spot price.

This replaced Yahoo Finance futures ticker `BZ=F`, because the futures history
started too late for the current historical dataset.

Current final coverage:

- first final date: `2003-01-02`;
- missing values after merge: `1`.

### Gold, VIX, and S&P 500

Source: Yahoo Finance through `yfinance`.

- gold ticker: `GC=F`;
- VIX ticker: `^VIX`;
- S&P 500 ticker: `^GSPC`;
- field: daily `Close`, falling back to `Adj Close` if needed.

These are acceptable MVP market proxies, but they should be source-hardened
later if the project moves toward a production research dataset.

### IMOEX

Source: MOEX ISS history endpoint.

- URL: `https://iss.moex.com/iss/history/engines/stock/markets/index/securities/IMOEX.json`;
- fields: `TRADEDATE`, `CLOSE`;
- pagination: `start` and `limit=100`.

Current final coverage:

- first final date: `2003-01-04`;
- missing values after merge: `15`.

### OFZ / Zero-Coupon Yield Curve

Primary source: Bank of Russia zero-coupon yield curve for government bonds.

- URL: `https://cbr.ru/hd_base/zcyc_params/`;
- available source history observed in the page: from `04.01.2003`;
- units: percent per annum;
- maturities used:
  - `1` year -> `ofz_1y`;
  - `2` years -> `ofz_2y`;
  - `5` years -> `ofz_5y`;
  - `10` years -> `ofz_10y`.

The CBR page does not reliably return the full 2003-2026 range in one request.
The loader therefore downloads the table by calendar-year chunks and parses the
HTML table directly.

Local MOEX files in `data/moex/ofz_*.csv` are now used as an overlap check, not
as the primary source. On the 2014-2026 overlap, the rebuilt CBR series matched
the local MOEX files closely:

- `ofz_1y`: max absolute difference `0.0100` percentage points;
- `ofz_2y`: max absolute difference `0.0100` percentage points;
- `ofz_5y`: max absolute difference `0.0300` percentage points;
- `ofz_10y`: max absolute difference `0.0300` percentage points.

Current final coverage:

- first final date: `2003-01-04`;
- source last date: `2026-06-05`;
- final daily coverage after 14-day forward-fill extends to `2026-06-07`;
- missing values after merge: `12` per OFZ column.

## Merge Rules

The builder creates a daily calendar index from `START_DATE` to the selected
dataset end date.

Dataset end is selected from the latest available market source among:

- gold;
- Brent;
- USD/RUB;
- EUR/RUB;
- IMOEX;
- VIX;
- S&P 500.

Daily merge rules:

- market and OFZ series use forward-fill with a maximum limit of `14` calendar days;
- macro policy series (`key_rate`, `inflation`) use unlimited forward-fill;
- every raw source is normalized to one row per date before merge;
- duplicate dates are collapsed by keeping the last parsed value for that date.

The 14-day limit is a guard against silently carrying stale market data for too
long. It preserves weekends and short holidays, but it exposes longer source
gaps as missing values.

## Derived Features

The final dataset includes raw series plus derived market stress inputs:

- `ofz_spread_10_2 = ofz_10y - ofz_2y`;
- `usd_volatility`: 30-day rolling standard deviation of USD/RUB daily returns;
- `imoex_volatility`: 30-day rolling standard deviation of IMOEX daily returns;
- `imoex_drawdown`: current IMOEX level divided by historical cumulative maximum minus 1;
- `imoex_zscore`: 252-day rolling z-score of IMOEX;
- `real_key_rate = key_rate - inflation`.

These derived fields are still model-engineering features, not final economic
definitions. Their purpose in MVP-1.0 is to support a transparent baseline
early-warning model.

## Current Coverage Snapshot

After the latest rebuild:

| Column | First final date | Last final date | Missing count | Missing pct |
| --- | --- | --- | ---: | ---: |
| `gold` | `2003-01-02` | `2026-06-07` | `1` | `0.01` |
| `brent` | `2003-01-02` | `2026-06-07` | `1` | `0.01` |
| `usd_rub` | `2003-01-01` | `2026-06-07` | `0` | `0.00` |
| `eur_rub` | `2003-01-01` | `2026-06-07` | `0` | `0.00` |
| `imoex` | `2003-01-04` | `2026-06-07` | `15` | `0.18` |
| `vix` | `2003-01-02` | `2026-06-07` | `1` | `0.01` |
| `sp500` | `2003-01-02` | `2026-06-07` | `1` | `0.01` |
| `ofz_1y` | `2003-01-04` | `2026-06-07` | `12` | `0.14` |
| `ofz_2y` | `2003-01-04` | `2026-06-07` | `12` | `0.14` |
| `ofz_5y` | `2003-01-04` | `2026-06-07` | `12` | `0.14` |
| `ofz_10y` | `2003-01-04` | `2026-06-07` | `12` | `0.14` |
| `key_rate` | `2003-02-17` | `2026-06-07` | `47` | `0.55` |
| `inflation` | `2003-01-01` | `2026-06-07` | `0` | `0.00` |
| `ofz_spread_10_2` | `2003-01-04` | `2026-06-07` | `12` | `0.14` |
| `real_key_rate` | `2003-02-17` | `2026-06-07` | `47` | `0.55` |

## Validation

`scripts/build_final_dataset.py` validates the final CSV before saving:

- required columns exist;
- no duplicate dates;
- dates are sorted;
- daily index has no missing calendar dates;
- important columns are not fully empty;
- currency values are not below a sanity threshold;
- positive market columns are positive;
- recent market series are not stuck in the last 60 calendar days;
- source freshness is printed and stale sources are reported as warnings;
- missing-value table is printed;
- numeric min/max table is printed.

The latest rebuild had no critical validation errors.

Remaining warnings:

- `key_rate` source last real update is `41` days before dataset end;
- `inflation` source last real update is `67` days before dataset end.

## Known Limitations

- Gold, VIX, and S&P 500 still depend on Yahoo Finance via `yfinance`.
- Inflation publication dates are approximated by shifting period-end values to
  the first day of the next month. A future production dataset should use exact
  historical release dates where available.
- The key-rate/refinancing-rate bridge is a practical policy-rate proxy. It is
  appropriate for MVP history extension, but should be explicitly evaluated in
  model sensitivity tests.
- Current source freshness depends on external publication schedules and local
  network availability.

## Model Artifacts

After rebuilding the dataset, `scripts/train_crisis_model.py` regenerates:

- `data/model_predictions.csv`;
- `data/model_metrics.json`;
- `models/artifacts/crisis_logreg_7d.joblib`;
- `models/artifacts/crisis_logreg_30d.joblib`;
- `models/artifacts/crisis_logreg_90d.joblib`.

Latest probabilities after the current dataset rebuild:

- `7d`: `0.010`, regime `Normal`, mean ROC-AUC `0.842`;
- `30d`: `0.092`, regime `Normal`, mean ROC-AUC `0.747`;
- `90d`: `0.251`, regime `Watch`, mean ROC-AUC `0.618`.
