# ArcShift V1 — Finite Model Evaluation Protocol

Protocol ID: `arcshift_model_eval_candidate.1`. Status: proposed for M03 review;
not frozen and not authorization to download data, fit models, or publish scores.

## Entry Gates

M04 may start only when a signed-off run manifest records the approved task,
horizon(s), forecast time/calendar, target definition, admitted source-purpose
decisions, immutable data and feature snapshot hashes, availability policy,
outer folds, warning policy, software lock, random seeds and run budget. An
input change invalidates the manifest rather than being repaired mid-run.

## Finite Candidate Design To Freeze

For each approved horizon, compare on exactly matching forecast origins:

1. training-prevalence constant baseline;
2. uncalibrated regularized logistic regression as the simple comparator;
3. the single predeclared candidate, if one is separately approved.

No MFS, multi-task family, broad hyperparameter search, or additional model is
in scope. The inherited 7/30/90 horizons are not three chances to select a
winner: approved horizons are separate tasks and all results are retained.

Use four expanding chronological outer folds after target warm-up, with
non-overlapping test periods and the strict `label_end < train_cutoff` rule.
Exact cutoffs are frozen from the admitted snapshot before outcomes are opened.
Every comparator uses the same origins and fold boundaries. Within each outer
training partition, use expanding time splits for all preprocessing and model
choices.

The finite logistic grid is `C in {0.01, 0.1, 1.0}`. Selection uses mean inner
Brier score, with the strongest regularization winning a tie. Compare three
predeclared score interpretations inside the development loop only:
uncalibrated, sigmoid calibration, and isotonic calibration. Isotonic is
ineligible when the frozen minimum sample/event rule is not met. The selection
rule and minimum must be added to the manifest before M04. Balanced class
weights do not establish probability calibration.

The outer test set is evaluation-only. It cannot choose `C`, calibrator,
threshold, horizon, feature set, model family, or artifact. If results motivate
a redesign, record rejection and create a new version with a new untouched
outer evaluation; do not relabel the viewed test as development data.

## Threshold And Warning Policy

An actionable threshold requires a product-approved false-alarm cost or annual
warning-burden constraint before M04. FAR 0.10 and display bands from legacy P1
are not imported. If no policy is approved, report threshold curves and retain
`warning_policy_status=unapproved`; do not emit actionable warnings.

Threshold selection uses development predictions only. Warning identity,
deduplication, cooldown and event matching are frozen with the policy. A policy
version never rewrites old warnings. Repeated browser reads do not create new
warnings, and personal review status is not ground truth.

## Required Metrics And Records

Report every fold, aggregate and failed run, not only the selected candidate:

- ROC AUC and average precision with training prevalence beside them;
- Brier score, log loss, calibration intercept/slope and reliability table;
- origin coverage, unavailable rate and reasons;
- at each predeclared threshold: false alarms, false alarms/year, warning days,
  precision, event recall, missed events, burden and lead-time distribution;
- event-level results under the frozen event matching/deduplication rule;
- block-bootstrap uncertainty intervals using a predeclared block length;
- paired candidate-minus-baseline differences on matching origins;
- hashes/versions for code, config, schema, data, features and environment.

If multiple candidate comparisons are approved, freeze the primary metric and
apply Holm correction to that finite family. All secondary metrics remain
descriptive. There is no empirical economic-impact claim without separate
decision/outcome data.

## Candidate Success And Failure Rules

Before M04, the manifest must give numeric acceptance bounds for calibration,
coverage, warning burden, event recall/misses and the primary paired comparison.
No bound may be invented after seeing outer results. A candidate fails when any
mandatory input is unsupported, outer evidence violates a bound, calibration
is not established for a probability claim, or the run cannot be reproduced.
A failed candidate is retained in the record with reasons.

Passing statistical bounds permits artifact review, not automatic production
admission. M05 separately verifies exact input schema, task/horizon, hashes,
cutoff, dependency compatibility, unavailable behavior, registry identity and
rollback. Independent review by Yaroslav plus Nastya for time/source semantics
is required; the author cannot be the sole reviewer.

## Run Budget

The maximum planned fit count per approved horizon is finite and must be
materialized in the manifest:

- 1 prevalence baseline (no fit);
- 3 logistic `C` values × inner folds;
- at most 2 fitted calibrators for the selected logistic candidate × inner
  folds, subject to the frozen eligibility rule;
- one refit per outer fold for each retained comparator/calibration path;
- no final full-data artifact until outer evaluation is recorded and a separate
  artifact decision is approved.

Any added run consumes a numbered amendment approved before execution. Failed
runs count toward the budget and remain in the warning record.
