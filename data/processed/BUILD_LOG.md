# BUILD_LOG — dataset_monthly.csv

Сгенерировано: 2026-06-10  (скрипт `scripts/build_monthly_dataset.py`)

## Что загружено и откуда

- yfinance ^VIX → vix_mean, vix_zscore (2003-01-02..2026-06-09, 5897 дневных строк)
- yfinance USDRUB=X → usdrub_vol, usdrub_zscore (2003-12-01..2026-06-10, 5735 дневных строк)
- yfinance IMOEX.ME → imoex_return, imoex_vol (2013-03-05..2024-06-14, 2795 дневных строк)
- ^IRX (fallback) → fed_rate
- data/inflation_key_rate.csv → cbr_rate (2013+), cpi_russia (2014-01-01..2025-12-01)
- data/refin_index.csv → cbr_rate (2003..2014-01-01, ставка рефинансирования ЦБ РФ, ffill по месяцам)
- data/moex/ofz_2y.csv + ofz_10y.csv → ofz_spread (среднее (10y-2y) за месяц), 2014-01-06..2026-05-08
- MOEX ISS API (iss.moex.com) → gap-fill IMOEX после 2024-06-14 (дневные свечи)

## Что не получилось (и почему)

_всё, что предполагалось, загрузилось_

## Итоговый датасет

- **Shape:** 282 rows × 23 cols
- **Диапазон дат:** 2003-01-01 .. 2026-06-01
- **Гранулярность:** месячная, `date` = первый день месяца

### % NaN по каждой колонке

| колонка | % NaN |
|---|---:|
| date | 0.00 |
| vix_mean | 0.00 |
| vix_zscore | 12.41 |
| vix_delta | 0.35 |
| fed_rate | 0.00 |
| fed_rate_delta | 0.35 |
| fed_rate_delta3 | 1.06 |
| cbr_rate | 2.13 |
| cbr_rate_delta | 2.48 |
| cbr_rate_delta3 | 3.19 |
| cpi_russia | 48.94 |
| usdrub_vol | 4.96 |
| usdrub_zscore | 26.60 |
| usdrub_accel | 6.38 |
| imoex_return | 0.35 |
| imoex_vol | 0.00 |
| imoex_drawdown | 1.06 |
| ofz_spread | 47.16 |
| ofz_spread_proxy | 2.13 |
| ofz_spread_filled | 0.35 |
| bis_credit_gap | 100.00 |
| news_sentiment | 100.00 |
| label | 0.00 |

## Что нужно добавить вручную

- **bis_credit_gap** — выкачать BIS credit-to-GDP gap (квартальные данные, www.bis.org/statistics/c_gaps.htm), линейно интерполировать на месяцы
- **news_sentiment** — собрать через GDELT или RSS-архив РБК/Коммерсанта/Интерфакса + FinBERT/LLM-разметку
- **label (0/1/2)** — выбрать определение кризиса (например, по imoex_drawdown, vix_zscore, ofz_spread) и проставить
- **imoex после 2024-06-14** — yfinance не отдаёт; источник MOEX ISS API (`iss.moex.com/iss/history/.../IMOEX.json`)

## Замечания по агрегации

- `vix_mean` — среднее дневного `Close` за месяц
- `vix_zscore`, `usdrub_zscore` — скользящее окно 36 мес (первые 35 значений NaN — это нормально)
- `usdrub_vol`, `imoex_vol` — std дневных log-returns внутри месяца
- `imoex_return` — % изменение last-of-month `Close`
- `cbr_rate` — last значение за месяц; до 2014-01-01 — refinancing rate (ffill событий по дням), с 2014-01-01 — ключевая ставка из inflation_key_rate.csv
- `cpi_russia` — month-end значение из inflation_key_rate.csv (как есть)
- `ofz_spread` — среднее (period_10.0 − period_2.0) за месяц
