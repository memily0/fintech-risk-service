# Project Context

## Product Direction

IVR is a crisis early-warning product. For MVP-1.0, the product should focus on financial crisis / market stress probability rather than becoming a credit scoring system.

The main user-facing output should be:

- probability of financial crisis or stress regime;
- risk regime such as Normal, Watch, Stress, Crisis;
- horizon, initially 7 / 30 / 90 days;
- explanation of factor contributions;
- historical behavior of the signal.

## Business Evidence From Interviews

Interview synthesis points toward delayed risk visibility in banking:

- credit-risk outcomes mature slowly, often months later;
- calibration and distribution drift are hard to notice early;
- existing systems monitor local model or portfolio health more than systemic stress;
- users need explanations and operational summaries, not just charts.

## Current Backend State

The backend repository currently contains:

- `scripts/build_final_dataset.py` - builds `data/final_dataset.csv` from CBR, MOEX, yfinance, local inflation, and OFZ files.
- `data/final_dataset.csv` - daily dataset with 4517 rows and 20 columns from 2014-01-01 to 2026-05-14.
- `app/dashboard.py` - Streamlit dashboard for market indicators, stress metrics, rates / OFZ, correlations, and data quality.

The dashboard already has a heuristic composite stress index in `build_composite_stress_index`, but it is not exposed as a trained prediction model.

## First Model Implication

The first model should be conservative:

- start with an interpretable baseline before heavier ML;
- create a documented stress target using future stress windows;
- use time-aware validation to avoid look-ahead bias;
- expose model output in the dashboard as probability plus drivers;
- keep the existing data pipeline and dashboard patterns.

## MVP-1.0 Baseline Model

The first implemented model is a balanced logistic regression baseline. It is intentionally simple and explainable.

Target:

- build a composite stress score from trailing z-scores of VIX, USD/RUB volatility, IMOEX volatility, absolute IMOEX drawdown, and OFZ curve inversion;
- mark stress event when `stress_score >= 1.0`;
- train separate future-event classifiers for 7, 30, and 90 day horizons.

Features:

- trailing level z-scores;
- 7 / 30 / 90 day returns for market price series;
- 7 / 30 / 90 day deltas for rates, spreads, volatility and drawdown;
- missing-value flags.

Current model quality:

- 7 day horizon: mean walk-forward ROC-AUC about 0.740;
- 30 day horizon: mean walk-forward ROC-AUC about 0.645;
- 90 day horizon: mean walk-forward ROC-AUC about 0.447.

Interpretation:

- 7 and 30 day outputs are the best MVP demonstration surfaces.
- 90 day output is retained for product shape, but should be treated as weak until the dataset is expanded.

## Bank of England Reference Takeaways

The useful concepts are:

- define a positive class before crisis, not only during crisis;
- exclude post-crisis periods where the signal is contaminated by aftermath;
- validate with forecasting / time splits;
- compare logistic regression against tree ensembles;
- explain drivers through feature contribution / Shapley-style outputs.

The parts not suitable for direct reuse:

- annual multi-country JST data shape;
- Python 3.6 / R research workflow;
- heavyweight repeated experiments and pickle result format;
- model code coupled to paper reproduction rather than product serving.
