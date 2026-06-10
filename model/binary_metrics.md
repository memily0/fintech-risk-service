# Binary XGBoost — норма vs тревога

Сгенерировано: 2026-06-10  ·  скрипт: `scripts/train_binary_xgboost.py`

## Конфигурация

- **label_binary** = 1 если `label > 0` (стресс или кризис), иначе 0
- **Признаки** (17): те же, что в трёхклассовой модели
- **Split**: train 2003-01..2018-12 (192 строк), test 2019-01..2026-06-01 (90 строк)
- **scale_pos_weight** = n_neg/n_pos = 161/31 = **5.194**
- XGBoost: n_estimators=200, max_depth=4, lr=0.05, `binary:logistic`, eval=`logloss`, tree=`hist`

### Распределение классов
| split | label=0 (норма) | label=1 (тревога) |
|---|---:|---:|
| train | 161 (83.9%) | 31 (16.1%) |
| test  | 76 (84.4%) | 14 (15.6%) |

## Classification report (test)

| class | precision | recall | f1 | support |
|---|---:|---:|---:|---:|
| 0 (норма) | 0.885 | 0.908 | 0.896 | 76 |
| 1 (тревога) | 0.417 | 0.357 | 0.385 | 14 |
| **accuracy** | | | **0.822** | 90 |
| macro avg | | | 0.640 | |

## Confusion matrix (binary)

| true \ pred | 0 | 1 |
|---|---:|---:|
| 0 | 69 | 7 |
| 1 | 9 | 5 |

## Сравнение: бинарная vs трёхклассовая (спроецированная)

«Тревога» в обоих случаях = pred ∈ {1, 2}, истина = label ∈ {1, 2}.

| метрика | binary | multiclass→binary |
|---|---:|---:|
| precision (норма)  | 0.885 | 0.882 |
| recall (норма)     | 0.908 | 0.987 |
| f1 (норма)         | 0.896 | 0.932 |
| precision (тревога)| 0.417 | 0.800 |
| recall (тревога)   | 0.357 | 0.286 |
| f1 (тревога)       | 0.385 | 0.421 |
| accuracy           | 0.822 | 0.878 |
| macro f1           | 0.640 | 0.676 |

### Confusion matrix — multiclass spectrum collapsed to binary
| true \ pred | 0 | 1 |
|---|---:|---:|
| 0 | 75 | 1 |
| 1 | 10 | 4 |

## Feature importance (топ 10)

| feature | importance |
|---|---:|
| vix_zscore | 0.1362 |
| usdrub_zscore | 0.1246 |
| cpi_russia | 0.1244 |
| fed_rate | 0.1088 |
| cbr_rate_delta | 0.0805 |
| vix_mean | 0.0794 |
| cbr_rate | 0.0728 |
| cbr_rate_delta3 | 0.0636 |
| ofz_spread_filled | 0.0427 |
| imoex_return | 0.0324 |
