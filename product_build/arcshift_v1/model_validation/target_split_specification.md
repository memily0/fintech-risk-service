# ArcShift V1 — Target, Feature And Temporal Split Specification

Status: `candidate.1`, M01/M02 implementation evidence, not an approved V1 task.
Date: 2026-11-05. Owner lane: model validation (Mila). Base: `4ae0778`.

## 1. Task And Target Candidate

`task_id`: `ru_composite_stress_event_candidate_v1`
`target_definition_id`: `future_composite_stress_event_candidate.1`

For a forecast origin `t` and horizon `H`, the candidate target is whether the
ArcShift composite stress event occurs on any calendar day in `(t, t + H]`.
The start is exclusive and the end is inclusive. `H` is measured in calendar
days, not rows or trading sessions. The inherited values 7/30/90 days and the
event threshold 1.0 are candidates only; `candidate_contract.json` currently
has no approved horizon.

The inherited composite has five mandatory components:

1. trailing VIX z-score;
2. trailing USD/RUB-volatility z-score;
3. trailing IMOEX-volatility z-score;
4. trailing absolute IMOEX-drawdown z-score;
5. trailing inverted OFZ 10Y–2Y-spread z-score.

The trailing mean and standard deviation exclude the current point. A composite
score and event exist only when every mandatory component exists. A component
change, threshold change, calendar change, or silent component removal creates
a new target definition and requires a new evaluation; it is not a patch to
make the current task pass.

This is a proxy for a future threshold event in a proprietary composite. It is
not an official banking-crisis probability, borrower PD, bank EL, or causal
estimate.

## 2. Unknown, Warm-up And Maturity

- Warm-up or a missing mandatory stress component produces `unknown`, not 0.
- Every calendar date in `(t, t + H]` must have a known event state. A missing
  date or unknown event makes the label unknown.
- `label_end = t + H calendar days` is stored for every origin.
- A label is outcome-mature only when the outcome snapshot covers `label_end`.
- For a historical training cutoff `c`, a row is eligible only when
  `t < c`, `label_end < c`, and the target is known. Equality is excluded
  because a date-only cutoff does not prove that the endpoint close/outcome was
  available before training began.
- A later observation of the label does not make it historically known at an
  earlier cutoff. Availability must be evaluated as of that cutoff.
- Dates must be unique and strictly increasing. Duplicates and reordered rows
  fail validation rather than being silently sorted or collapsed.

The executable implementation is `models/validation/temporal.py`. Synthetic
regressions are in `tests/test_temporal_validation.py`.

## 3. Forecast-Origin And Feature Availability

Every future feature snapshot must identify `forecast_origin`,
`information_as_of`, data/feature snapshot IDs, definitions, parent series,
missingness, and source admission. Only values known by `information_as_of` may
enter a row. Prospective availability is
`max(received_at, published_at when known)`; an unknown historical publication
time stays unknown. Same-date US closes, unfinished daily bars, forward-filled
values, and CPI assumptions are not automatically known at a Moscow origin.

Feature transformations are fitted inside each training split. Imputation,
scaling, selection, calibration, and threshold selection may not see the outer
test interval. Forward-fill does not create a new observation or reset age.

The 19 legacy columns and 95 transformations are an inventory, not an admitted
V1 schema. DS01–DS12 and all source-purpose rights remain open. A model run must
use an immutable admitted feature snapshot; source failure is not evidence of
no predictive signal.

## 4. Split Semantics

The evaluation uses expanding chronological outer folds. Each training mask
applies the strict label-end rule above. Test origins are identical for every
baseline and comparator in a task/horizon comparison. Rows unavailable to one
comparator are reported and paired analysis uses the common supported origins;
coverage loss is a result, not silently discarded.

Calibration and warning thresholds are selected only from the training-side
development loop. Outer outcomes are opened once for final evaluation and may
not be used to choose a deployment candidate, horizon, feature set, calibrator,
or threshold. Exact dates, admitted inputs and run manifest must be frozen
before M04 begins; the candidate protocol is in `evaluation_protocol.md`.

## 5. Score And History Labels

- `fitted`: score from a model that trained on the displayed observation or its
  future; exploratory only and never the default validation curve.
- `OOS`: prediction generated without the observation or its label being used
  in fit, preprocessing, calibration, or threshold selection.
- `historical_demo`: synthetic or non-admitted historical display; not current.
- `live`: score from an admitted artifact and a valid current feature snapshot.

These states are mutually explicit. Missing OOS folds remain missing. A
balanced logistic-regression output has `calibration_status=not_established`
until held-out evidence supports a calibrated interpretation.

## 6. Decisions Required Before Freeze

The product owner/integration, data and model reviewers must approve: task and
threshold meaning; one or more horizons; forecast time and calendar; exact
component availability; admitted sources and model-use rights; immutable data
snapshot; outer dates; preprocessing; calibration candidates; warning burden or
cost policy; multiplicity rule; success/failure criteria; and finite run budget.
Until then M04 and M05 remain blocked and the UI must use `unavailable` or
clearly labelled `historical_demo` states.
