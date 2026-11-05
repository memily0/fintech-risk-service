> HISTORICAL REFERENCE ONLY. Later audit found train-label maturity,
> warm-up/unknown-target and fitted/OOS gaps. Old metrics, calibration
> wording and horizon interpretations are NOT renewed validation.
> Do not run old rebuild/train commands automatically. Read current_state.md.

# Model Card: ArcShift MVP-1.0 Crisis Early-Warning Baseline

## Model Details

| Field | Value |
| --- | --- |
| Model version | `mvp_1_balanced_logistic_regression` |
| Model type | Balanced logistic regression |
| Pipeline | Median imputation, standard scaling, logistic regression |
| Regularization | `C = 0.01` |
| Horizons | 7, 30, and 90 days |
| Feature count | 95 |
| Training dataset | `data/final_dataset.csv` |
| Latest dataset date | `2026-06-07` |
| Metrics file | `data/model_metrics.json` |
| Prediction file | `data/model_predictions.csv` |

## Intended Use

The model supports an early-warning dashboard for financial market stress. It is
intended to help analysts monitor changes in macrofinancial conditions, compare
forecast horizons, and inspect the main drivers behind the current signal.

Suitable uses:

- MVP demonstration of early-warning logic;
- analyst-facing monitoring of financial stress probability;
- internal comparison of horizons and model behavior;
- product research and methodology validation.

Unsuitable uses:

- automated lending decisions;
- credit scoring;
- capital allocation or regulatory reporting;
- production crisis prediction without additional validation;
- exact crisis-date prediction.

## Target

The target is a future stress event derived from a transparent composite stress
score.

The stress score is the average of trailing z-score components:

- VIX;
- USD/RUB volatility;
- IMOEX volatility;
- absolute IMOEX drawdown;
- OFZ curve inversion.

An event is marked when:

```text
stress_score >= 1.0
```

For each horizon, the model predicts whether this event occurs within the next
7, 30, or 90 calendar days.

## Input Data

The model consumes 19 daily macrofinancial input series:

- `gold`;
- `brent`;
- `usd_rub`;
- `eur_rub`;
- `imoex`;
- `vix`;
- `sp500`;
- `ofz_1y`;
- `ofz_2y`;
- `ofz_5y`;
- `ofz_10y`;
- `key_rate`;
- `inflation`;
- `ofz_spread_10_2`;
- `usd_volatility`;
- `imoex_volatility`;
- `imoex_drawdown`;
- `imoex_zscore`;
- `real_key_rate`.

The current dataset covers `2003-01-01` through `2026-06-07`.

## Features

For every input series, the model creates:

- trailing level z-score;
- 7, 30, and 90 day return or delta;
- missing-value flag.

The feature transformations use lagged or trailing information. Rolling
z-scores shift the rolling statistics by one day before scoring the current
observation.

## Output

For each horizon, the model produces:

- `probability`: estimated probability of future stress;
- `regime`: product risk regime;
- `top_drivers`: top local linear contribution drivers;
- `cv_probability`: walk-forward probability where available.

Risk regime mapping:

| Probability | Regime |
| ---: | --- |
| `< 0.20` | `Normal` |
| `0.20 - 0.40` | `Watch` |
| `0.40 - 0.60` | `Elevated` |
| `0.60 - 0.80` | `Stress` |
| `>= 0.80` | `Crisis` |

## Current Performance Summary

| Horizon | Training observations | Target positive rate | Mean ROC-AUC | Mean PR-AUC | Mean Brier score | Latest probability | Latest regime |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 7d | 8552 | 13.34% | 0.842 | 0.735 | 0.101 | 0.010 | `Normal` |
| 30d | 8529 | 19.15% | 0.747 | 0.563 | 0.183 | 0.092 | `Normal` |
| 90d | 8469 | 31.10% | 0.618 | 0.528 | 0.294 | 0.251 | `Watch` |

Latest probability date: `2026-06-07`.

## Interpretation

The 7 day model is currently the most reliable MVP demonstration surface. The
30 day model remains useful for medium-horizon monitoring but is less stable.
The 90 day model is retained because the product needs a longer horizon, but it
should be treated as exploratory until the dataset and validation framework are
expanded.

The 2022-2023 validation fold is the weakest period across horizons. This
suggests regime shift sensitivity and should be a priority for future model
work.

## Limitations

- The target is a product stress proxy, not an official crisis label.
- The model is calibrated for a Russia-focused daily market dataset.
- Some historical sources are not exact point-in-time vintages.
- Probability thresholds are display thresholds, not policy thresholds.
- The model is linear and may miss nonlinear interactions.
- Top drivers are linear coefficient contributions, not causal explanations.
- The current dashboard is an MVP and should not be used as a production risk
  control.

## Monitoring Recommendations

Before production use, monitor:

- source freshness;
- missing values by input series;
- stability of latest probabilities by horizon;
- drift in feature distributions;
- changes in positive-rate balance;
- calibration and Brier score over new periods;
- false alarm and missed-stress behavior.

## Rebuild Commands

```bash
python scripts/build_final_dataset.py --start-date 2003-01-01
python scripts/train_crisis_model.py
```

The rebuild generates:

- `data/final_dataset.csv`;
- `data/model_predictions.csv`;
- `data/model_metrics.json`;
- `models/artifacts/crisis_logreg_7d.joblib`;
- `models/artifacts/crisis_logreg_30d.joblib`;
- `models/artifacts/crisis_logreg_90d.joblib`.
