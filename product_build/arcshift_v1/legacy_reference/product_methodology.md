> HISTORICAL REFERENCE ONLY. Later audit found train-label maturity,
> warm-up/unknown-target and fitted/OOS gaps. Old metrics, calibration
> wording and horizon interpretations are NOT renewed validation.
> Do not run old rebuild/train commands automatically. Read current_state.md.

# Product Methodology

## Purpose

ArcShift MVP-1.0 is an early-warning product for financial market stress. The
product does not claim to predict the exact date of a crisis. It estimates the
probability that a stress event will occur within a selected forward horizon and
shows the market factors that drive that signal.

The current product scope is intentionally conservative:

- daily Russia-focused macrofinancial monitoring;
- forecast horizons of 7, 30, and 90 days;
- interpretable baseline model before heavier ML models;
- reproducible dataset and model artifacts;
- transparent validation and known limitations.

## User Problem

Risk teams often see portfolio deterioration with a delay. Credit outcomes,
model drift, and portfolio stress can mature months after the underlying market
or macro conditions begin to change. ArcShift addresses this gap by giving
analysts an external early-warning view of market and macrofinancial stress.

The MVP is not a credit scoring system and does not make lending decisions. It
is a decision-support layer for monitoring risk regimes, market stress, and
drivers of changing conditions.

## Product Outputs

The dashboard exposes these product outputs:

- probability of future financial stress;
- risk regime: `Normal`, `Watch`, `Elevated`, `Stress`, or `Crisis`;
- horizon: 7, 30, or 90 days;
- latest key drivers of the forecast;
- historical behavior of market indicators and model probabilities;
- walk-forward validation metrics by horizon.

## Data Pipeline

The current product dataset is `data/final_dataset.csv`.

Dataset snapshot:

- start date: `2003-01-01`;
- end date: `2026-06-07`;
- frequency: daily calendar index;
- rows: `8559`;
- columns: `20`.

The dataset is built by `scripts/build_final_dataset.py` and then consumed by
`scripts/train_crisis_model.py`.

The main source groups are:

- CBR: USD/RUB, EUR/RUB, monetary policy rate, and zero-coupon OFZ curve;
- EIA: Europe Brent Spot Price FOB;
- Rosstat through NSEDC: CPI YoY index transformed into inflation;
- MOEX: IMOEX;
- Yahoo Finance through `yfinance`: gold, VIX, and S&P 500.

Detailed source rules are documented in `omx_wiki/dataset-formation.md`.

## Look-Ahead Controls

The MVP uses several controls to avoid obvious future leakage:

- rolling z-scores shift their rolling mean and standard deviation by one day;
- lagged returns and deltas use only prior values;
- monthly inflation is shifted to the first day of the next month before
  forward-fill;
- future labels are masked at the dataset tail when the full future horizon is
  unavailable;
- validation is time-aware through walk-forward splits.

These controls make the MVP suitable as a product demonstration and methodology
baseline. They do not yet make it a full point-in-time research dataset, because
some sources still use currently available historical series rather than exact
historical release vintages.

## Stress Target

The model first builds a transparent composite stress score from trailing
z-scores of five components:

- VIX;
- USD/RUB volatility;
- IMOEX volatility;
- absolute IMOEX drawdown;
- OFZ curve inversion, represented as the negative 10Y-2Y OFZ spread.

A current-day stress event is marked when:

```text
stress_score >= 1.0
```

For each horizon, the target is whether such a stress event occurs within the
next `h` calendar days:

- `target_7d`;
- `target_30d`;
- `target_90d`.

This target is a product stress proxy, not an official systemic crisis label.
It is designed to make the MVP measurable before the larger research program
introduces international crisis labels.

## Feature Engineering

The model uses 19 input series. For each series it creates:

- trailing level z-score;
- 7, 30, and 90 day returns for price-like series;
- 7, 30, and 90 day deltas for rate-like and stress-like series;
- missing-value flag.

This produces 95 features.

Price-like series use relative returns. Rate-like and stress-like series use
absolute deltas. Missing values are handled explicitly through missing flags and
median imputation inside the model pipeline.

## Model

The MVP model is a balanced logistic regression pipeline:

```text
SimpleImputer(strategy="median")
  -> StandardScaler()
  -> LogisticRegression(class_weight="balanced", C=0.01)
```

There is one trained model per horizon:

- `models/artifacts/crisis_logreg_7d.joblib`;
- `models/artifacts/crisis_logreg_30d.joblib`;
- `models/artifacts/crisis_logreg_90d.joblib`.

The model is deliberately simple. Its role is to create an auditable baseline,
not to maximize leaderboard performance.

## Risk Regimes

Predicted probabilities are mapped to product regimes:

| Probability | Regime |
| ---: | --- |
| `< 0.20` | `Normal` |
| `0.20 - 0.40` | `Watch` |
| `0.40 - 0.60` | `Elevated` |
| `0.60 - 0.80` | `Stress` |
| `>= 0.80` | `Crisis` |

The current thresholds are product display thresholds. They should be calibrated
more carefully before any production risk-management use.

## Explainability

For each forecast, the system computes top drivers by multiplying standardized
feature values by logistic-regression coefficients. This gives a local linear
contribution score for the latest observation.

The driver output should be read as directional product interpretation:

- positive contribution increases the stress probability;
- negative contribution decreases the stress probability;
- large absolute contribution means the factor is influential for the current
  forecast.

This is not yet a full SHAP-based or causal explanation layer.

## Validation

Validation uses walk-forward splits:

- train before `2018-01-01`, test `2018-2019`;
- train before `2020-01-01`, test `2020-2021`;
- train before `2022-01-01`, test `2022-2023`;
- train before `2024-01-01`, test `2024-2026-06-07`.

Reported metrics:

- ROC-AUC;
- PR-AUC;
- Brier score;
- positive rate;
- latest probability and regime.

The detailed results are in `docs/validation_report.md`.

## Product Interpretation

Current MVP interpretation:

- 7 day horizon is the strongest demonstration surface;
- 30 day horizon is useful but less stable;
- 90 day horizon is informative for product shape but still weaker and should be
  treated as exploratory;
- the model is a transparent baseline for early-warning logic, not a production
  crisis model.

## Boundary With Large Research

The product methodology is the mini-research layer. Its goal is to show that the
current MVP uses a fair and reproducible method.

The larger ArcShift research program should remain separate until specific
results are ready for product handoff. Future research may introduce:

- official systemic crisis labels;
- international panel datasets;
- point-in-time data vintages;
- classical crisis indicators such as credit-to-GDP gaps;
- stronger ML baselines;
- usefulness functions for false alarms and missed crises;
- richer explainability methods.

Only validated research outputs should be integrated back into this product.
