# Baseline XGBoost — результаты

Сгенерировано: 2026-06-10  ·  скрипт: `scripts/train_baseline_xgboost.py`

## Конфигурация

- **Признаки** (17): `vix_mean`, `vix_zscore`, `vix_delta`, `fed_rate`, `fed_rate_delta`, `fed_rate_delta3`, `cbr_rate`, `cbr_rate_delta`, `cbr_rate_delta3`, `cpi_russia`, `usdrub_vol`, `usdrub_zscore`, `usdrub_accel`, `imoex_return`, `imoex_vol`, `imoex_drawdown`, `ofz_spread_filled`
- **Целевая переменная:** `label` (0/1/2)
- **Split по времени:**
  - train: 2003-01-01 .. 2018-12-01 (192 строк, 2003-01-01..2018-12-01)
  - test:  2019-01-01 .. 2026-06-01 (90 строк)

### Распределение классов
- train: 0=161 (83.9%), 1=17 (8.9%), 2=14 (7.3%)
- test:  0=76 (84.4%), 1=3 (3.3%), 2=11 (12.2%)

### Балансировка
`scale_pos_weight` — биномиальный параметр, для multiclass использованы **sample_weight** из `sklearn.utils.class_weight.compute_class_weight(class_weight='balanced')`:

| class | weight |
|---|---:|
| 0 | 0.398 |
| 1 | 3.765 |
| 2 | 4.571 |

### Параметры модели
- n_estimators = 200
- max_depth = 4
- learning_rate = 0.05
- objective = `multi:softprob`, num_class = 3
- eval_metric = `mlogloss`
- tree_method = `hist`, random_state = 42

## Classification report (test)

| class | precision | recall | f1 | support |
|---|---:|---:|---:|---:|
| 0 (норма) | 0.882 | 0.987 | 0.932 | 76 |
| 1 (стресс) | 0.000 | 0.000 | 0.000 | 3 |
| 2 (кризис) | 0.750 | 0.273 | 0.400 | 11 |
| macro avg | 0.544 | 0.420 | 0.444 | 90 |
| weighted avg | 0.837 | 0.867 | 0.836 | 90 |
| **accuracy** | | | **0.867** | 90 |

## Confusion matrix (test)

| true \ pred | 0 | 1 | 2 |
|---|---:|---:|---:|
| 0 | 75 | 0 | 1 |
| 1 | 3 | 0 | 0 |
| 2 | 7 | 1 | 3 |

## Feature importance (gain, top 10)

| feature | importance |
|---|---:|
| cbr_rate | 0.2003 |
| fed_rate | 0.1212 |
| imoex_vol | 0.0912 |
| vix_zscore | 0.0843 |
| cbr_rate_delta | 0.0814 |
| cpi_russia | 0.0729 |
| usdrub_zscore | 0.0670 |
| cbr_rate_delta3 | 0.0638 |
| fed_rate_delta3 | 0.0477 |
| ofz_spread_filled | 0.0352 |
| vix_mean | 0.0340 |
| imoex_return | 0.0308 |
| imoex_drawdown | 0.0301 |
| vix_delta | 0.0164 |
| fed_rate_delta | 0.0118 |
| usdrub_vol | 0.0063 |
| usdrub_accel | 0.0056 |

## Замечания

- В `test` всего 90 строк, из них минорные классы — крайне малая выборка → метрики имеют большой доверительный интервал.
- Период обучения (2003–2018) включает 3 из 4 размеченных кризисов (GFC 2008-09, Крым 2014-12, исключая COVID 2020 и 2022). Тест видит COVID и санкционный шок 2022 — это честная проверка обобщения.
- XGBoost нативно обрабатывает NaN в признаках — `dropna` не делался.
