# Crisis Prediction Service

ML-сервис ежемесячного сигнала рыночных условий 🟢 / 🟡 / 🔴 для финтех-команд риск-менеджмента.

## Что это

Сервис принимает на вход ежемесячные макро- и рыночные данные (VIX, ставки ФРС/ЦБ, инфляция, курс RUB, спред ОФЗ, доходность IMOEX) и возвращает один из трёх сигналов: 🟢 норма, 🟡 стресс, 🔴 кризис. Горизонт — текущий месяц. Целевая аудитория — финтех-стартапы и финансовые подразделения, которым нужен дешёвый, объяснимый индикатор «когда поджимать лимиты».

В основе — ансамбль из XGBoost (учится на верифицированных кризисах: GFC 2008, Крым 2014, COVID 2020, санкции 2022) и IsolationForest (учится только на «нормальных» месяцах и помечает аномалии). Soft-voting объединяет их в один сигнал.

## Как устроен проект

```
.
├── app/                              # Streamlit-дашборд
│   └── dashboard.py                  # запуск: streamlit run app/dashboard.py
├── data/
│   ├── inflation_key_rate.csv        # CPI + ключевая ставка ЦБ РФ (2014+, ежемес.)
│   ├── refin_index.csv               # ставка рефинансирования ЦБ РФ (1992-2015)
│   ├── moex/                         # дневная кривая ZCYC ОФЗ (1y/2y/5y/10y)
│   ├── yahoo/                        # дневные котировки yfinance (VIX, USDRUB, ...)
│   └── processed/
│       ├── dataset_monthly.csv       # финальный месячный датасет (282 × 23)
│       └── BUILD_LOG.md              # журнал сборки данных
├── docs/
│   └── LABELING_METHODOLOGY.md       # методология разметки label
├── model/                            # обученные модели и отчёты
│   ├── baseline_xgboost.pkl          # 3-классовый XGBoost
│   ├── binary_xgboost.pkl            # бинарный XGBoost (норма / тревога)
│   ├── isolation_forest.pkl          # IsolationForest + median-imputer
│   ├── soft_voting.pkl               # α=0.4 + threshold
│   ├── tuned_xgboost.pkl             # XGBoost с custom-весами (вариант A)
│   └── *.md, *.png                   # отчёты и кривые
├── scripts/
│   ├── build_monthly_dataset.py      # сборка dataset_monthly.csv
│   ├── train_models.py               # обучение всех моделей одной командой
│   ├── train_baseline_xgboost.py     # отдельные эксперименты по моделям
│   ├── train_binary_xgboost.py
│   ├── train_isolation_forest.py
│   ├── tune_xgboost.py
│   ├── ensemble_eval.py
│   └── soft_voting_ensemble.py
├── AUDIT.md                          # аудит исходных данных
├── README.md                         # этот файл
└── requirements.txt
```

## Данные

Финальная месячная сетка — `data/processed/dataset_monthly.csv`, 282 строки (2003-01-01 … 2026-06-01), 17 фич + label.

| фича | источник | покрытие |
|---|---|---|
| `vix_mean`, `vix_zscore`, `vix_delta` | yfinance `^VIX` | 2003-01 → сегодня |
| `fed_rate`, `fed_rate_delta`, `fed_rate_delta3` | yfinance `^IRX` (прокси FEDFUNDS) | 2003-01 → сегодня |
| `cbr_rate`, `cbr_rate_delta`, `cbr_rate_delta3` | `refin_index.csv` (2003-2013) + `inflation_key_rate.csv` (2014+) | 2003-01 → 2025-12 |
| `cpi_russia` | `inflation_key_rate.csv` | 2014-01 → 2025-12 |
| `usdrub_vol`, `usdrub_zscore`, `usdrub_accel` | yfinance `USDRUB=X` | 2003-12 → сегодня |
| `imoex_return`, `imoex_vol`, `imoex_drawdown` | yfinance `IMOEX.ME` + MOEX ISS API (2003-2013, 2024+) | 2003-02 → сегодня |
| `ofz_spread_filled` | `data/moex/ofz_*.csv` (2014+) + прокси `cbr_rate − fed_rate` (2003-2013) | 2003-01 → 2026-05 |
| `bis_credit_gap` | placeholder | — |
| `news_sentiment` | placeholder | — |
| `label` | NBER + ЦБ РФ + ист. события (см. `docs/LABELING_METHODOLOGY.md`) | вся серия |

Подробный журнал сборки и % NaN по каждой колонке — `data/processed/BUILD_LOG.md`.

## Модели

Сравнение на тесте (90 строк, 2019-01 … 2026-06; alarm = `label ∈ {1, 2}`):

| модель | recall (тревога) | precision (тревога) | f1 (тревога) | macro f1 | accuracy |
|---|---:|---:|---:|---:|---:|
| multiclass XGBoost | 0.286 | 0.800 | 0.421 | 0.676 | 0.878 |
| binary XGBoost | 0.357 | 0.417 | 0.385 | 0.640 | 0.822 |
| IsolationForest | 0.786 | 0.256 | 0.386 | 0.551 | 0.611 |
| Ансамбль AND | 0.286 | 0.800 | 0.421 | 0.676 | 0.878 |
| Ансамбль OR | 0.786 | 0.256 | 0.386 | 0.551 | 0.611 |
| **Soft voting α=0.4** | **0.714** | **0.556** | **0.625** | **0.772** | **0.867** |

**Финальная модель — soft voting α=0.4.** XGBoost-classifier хорошо отличает уже знакомые кризисы (GFC-like, Крым-like), но проваливает COVID-2020 и 2022 — они out-of-distribution. IsolationForest, наоборот, ловит любые отклонения от нормы, но шумит. Линейная комбинация `0.4 · P_xgb + 0.6 · iso_score` берёт лучшее: 10 из 14 alarm-месяцев пойманы при всего 8 ложных тревогах — почти в 4 раза меньше шума, чем у IsoForest.

## Разметка

**Красные периоды (🔴 кризис)** определены **по официальным источникам**:
NBER Business Cycle Dating Committee — для глобальных рецессий (GFC 2008-09, COVID 2020), и ЦБ РФ + Росстат — для российских кризисов с экстренным повышением ключевой ставки (Крым 2014-12, санкционный шок 2022-02). Это исключает label leakage: метка не вычислялась из признаков модели.

**Жёлтые периоды (🟡 стресс)** выбраны экспертно по задокументированным событиям, **не** по порогам VIX или другим фичам: pre-GFC 2008 (нефть на пике, Bear Stearns), кризис еврозоны 2011-08 (S&P даунгрейд США), taper tantrum 2013-05 (Bernanke), санкции против Русала 2018-04 (OFAC), pre-invasion buildup 2021-10. Каждый период привязан к источнику (S&P press release, OFAC, ЦБ РФ — Обзор финансовой стабильности и т.д.).

Полные обоснования, источники по каждому эпизоду и ограничения подхода — в `docs/LABELING_METHODOLOGY.md`.

## Ограничения

1. **Малая выборка минорных классов.** В train (2003–2018) всего **4 кризиса** (GFC + Крым на 14 строк класса 2) и **5 стресс-эпизодов** (17 строк класса 1). Любая метрика по этим классам имеет широкий доверительный интервал; одно случайное смещение разбивки может сильно изменить выводы.
2. **Look-ahead bias в разметке.** Границы кризисов сегодня известны, в реальном времени — нет. При расширении модели обязателен **walk-forward** (rolling/expanding window), а не случайный k-fold. Метрики на train-test split — оптимистичная оценка верхней границы.
3. **Порог soft voting подобран на TRAIN.** XGBoost в train переобучен → `P_xgb` там завышен → порог слегка смещён. Честная оценка требует hold-out внутри train (например, отложенный 2017-2018 как validation).
4. **Нет `news_sentiment` и `bis_credit_gap`.** Колонки оставлены заглушками (100% NaN). Без них модель опирается только на ценовые и макро-фичи; добавление текстового сигнала и кредитного зазора BIS — приоритетные улучшения.

## Воспроизводимость

```bash
pip install -r requirements.txt
python scripts/build_monthly_dataset.py     # собирает data/processed/dataset_monthly.csv
python scripts/train_models.py              # обучает все модели и печатает таблицу сравнения
```

После этого `model/*.pkl` готовы к загрузке через `pickle`, а Streamlit-дашборд запускается командой `streamlit run app/dashboard.py`.

## Авторы

- [имя] — [роль]
- [школа/университет]
- [год]
