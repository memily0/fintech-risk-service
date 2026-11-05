> HISTORICAL REFERENCE ONLY. Later audit found train-label maturity,
> warm-up/unknown-target and fitted/OOS gaps. Old metrics, calibration
> wording and horizon interpretations are NOT renewed validation.
> Do not run old rebuild/train commands automatically. Read current_state.md.

# Validation Report: ArcShift MVP-1.0

## Scope

This report summarizes the validation evidence for the current ArcShift MVP-1.0
baseline model.

Artifacts used:

- model metrics: `data/model_metrics.json`;
- predictions: `data/model_predictions.csv`;
- training script: `scripts/train_crisis_model.py`;
- dataset documentation: `omx_wiki/dataset-formation.md`.

The model is a product demonstration baseline. The validation goal is to show
that the pipeline is time-aware, reproducible, and honest about limitations. It
is not a claim of production-grade crisis prediction.

## Dataset Snapshot

| Field | Value |
| --- | --- |
| Dataset | `data/final_dataset.csv` |
| Frequency | Daily calendar index |
| Start date | `2003-01-01` |
| End date | `2026-06-07` |
| Rows | 8559 |
| Columns | 20 |
| Feature count after engineering | 95 |

## Validation Design

The model uses walk-forward validation. Each fold trains on all valid target
rows before a cutoff date and tests on the following time period.

Fold design:

| Fold | Train end | Test start | Test end |
| ---: | --- | --- | --- |
| 1 | `2017-12-31` | `2018-01-01` | `2019-12-31` |
| 2 | `2019-12-31` | `2020-01-01` | `2021-12-31` |
| 3 | `2021-12-31` | `2022-01-01` | `2023-12-31` |
| 4 | `2023-12-31` | `2024-01-01` | `2026-06-07` |

The final model artifacts are trained on all valid rows for each horizon after
walk-forward metrics are computed.

## Metric Definitions

- ROC-AUC: ranking quality across positive and negative cases.
- PR-AUC: precision-recall quality, useful when stress events are less frequent.
- Brier score: probability calibration error, where lower is better.
- Positive rate: share of observations where the future stress target is true.

Accuracy is intentionally not used as the main metric because stress events are
imbalanced and false alarms versus missed events have different business costs.

## Summary By Horizon

| Horizon | Observations | Positive rate | Mean ROC-AUC | Mean PR-AUC | Mean Brier score | Latest probability | Latest regime |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 7d | 8552 | 13.34% | 0.842 | 0.735 | 0.101 | 0.010 | `Normal` |
| 30d | 8529 | 19.15% | 0.747 | 0.563 | 0.183 | 0.092 | `Normal` |
| 90d | 8469 | 31.10% | 0.618 | 0.528 | 0.294 | 0.251 | `Watch` |

Latest probability date: `2026-06-07`.

## 7 Day Horizon

| Train end | Test period | Observations | Positive rate | ROC-AUC | PR-AUC | Brier score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `2017-12-31` | `2018-01-01` to `2019-12-31` | 730 | 4.93% | 0.944 | 0.815 | 0.047 |
| `2019-12-31` | `2020-01-01` to `2021-12-31` | 731 | 9.99% | 0.985 | 0.942 | 0.033 |
| `2021-12-31` | `2022-01-01` to `2023-12-31` | 730 | 24.11% | 0.528 | 0.564 | 0.152 |
| `2023-12-31` | `2024-01-01` to `2026-06-07` | 882 | 12.24% | 0.910 | 0.618 | 0.173 |

Interpretation:

- Strongest horizon in the MVP.
- Performs very well in 2018-2021 and 2024-2026.
- The 2022-2023 fold is materially weaker, likely reflecting regime shift and
  stress dynamics that the current linear baseline does not fully capture.

## 30 Day Horizon

| Train end | Test period | Observations | Positive rate | ROC-AUC | PR-AUC | Brier score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `2017-12-31` | `2018-01-01` to `2019-12-31` | 730 | 8.08% | 0.820 | 0.419 | 0.152 |
| `2019-12-31` | `2020-01-01` to `2021-12-31` | 731 | 14.50% | 0.836 | 0.694 | 0.128 |
| `2021-12-31` | `2022-01-01` to `2023-12-31` | 730 | 26.58% | 0.463 | 0.480 | 0.256 |
| `2023-12-31` | `2024-01-01` to `2026-06-07` | 859 | 24.80% | 0.870 | 0.658 | 0.197 |

Interpretation:

- Useful medium-horizon signal for MVP purposes.
- Lower precision-recall quality than 7d.
- 2022-2023 remains the weak fold.
- Probability calibration is less stable than the 7d model.

## 90 Day Horizon

| Train end | Test period | Observations | Positive rate | ROC-AUC | PR-AUC | Brier score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `2017-12-31` | `2018-01-01` to `2019-12-31` | 730 | 21.10% | 0.303 | 0.146 | 0.346 |
| `2019-12-31` | `2020-01-01` to `2021-12-31` | 731 | 26.13% | 0.663 | 0.623 | 0.331 |
| `2021-12-31` | `2022-01-01` to `2023-12-31` | 730 | 26.58% | 0.580 | 0.452 | 0.334 |
| `2023-12-31` | `2024-01-01` to `2026-06-07` | 799 | 43.80% | 0.926 | 0.892 | 0.166 |

Interpretation:

- The 90d model is the weakest of the three on average.
- Early folds have poor calibration and weak ranking performance.
- The strong 2024-2026 fold should not be overinterpreted without additional
  robustness checks.
- Keep this horizon visible for product shape, but label it internally as
  exploratory until the research dataset and target definition are improved.

## Main Findings

1. The MVP successfully implements a time-aware validation pipeline.
2. The 7d model is currently the strongest and clearest demonstration surface.
3. The 30d model is directionally useful but less stable.
4. The 90d model needs more research before it can be treated as reliable.
5. The 2022-2023 period is the main stress test for the current approach.
6. Calibration should be improved before any production risk use.

## Known Validation Gaps

- No official systemic crisis labels are used yet.
- No comparison against classical crisis baselines is included yet.
- No point-in-time data vintage system is implemented yet.
- No policy-aware usefulness function is implemented yet.
- No explicit false alarm and missed-stress operating point is selected.
- No external validation on non-Russian markets is included yet.

## Recommended Next Validation Work

Near-term product validation:

- add false alarm and missed-stress counts by threshold;
- add calibration plots or calibration tables;
- report recent-window performance separately;
- document the 2022-2023 failure mode in more detail.

Research validation:

- compare against threshold-only stress indicators;
- compare against credit-gap and macrofinancial baselines;
- introduce official crisis labels;
- build a point-in-time dataset protocol;
- evaluate lead time before known stress episodes;
- test nonlinear models against the logistic baseline.
