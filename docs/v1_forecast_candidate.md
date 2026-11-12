# V1 Forecast Candidate And Evaluation Handoff

Updated: 2026-11-12. Two working limits agreed for the first historical
comparison; the full evaluation manifest is still proposed. No real fit,
accepted artifact, or serving.

The V1 task is a **new Russian market-stress episode in the next 30 calendar
days**, not the probability of a systemic banking crisis and not classification
of a month already in stress. See [task definition](v1_task_definition.md) and
[measurement](v1_stress_measurement.md). No target or measurement change here.

## What To Transfer

- Transfer the evaluation design and an interpretable first candidate, not
  historical research weights. The long-horizon credit-only comparison did
  not establish that more complex models improve the simple credit reference.
  The multi-source research comparison motivates testing incremental inputs,
  but does not establish an advantage for the daily Russian task.
- Initial candidate: one L2-regularized logistic regression trained anew on
  admitted point-in-time features. Compare it to the positive-label frequency
  estimated on mature training rows. Evaluate both on the same dates. Training
  folds, missing-feature rules, calibration eligibility, warning policy and
  acceptance limits must be frozen in the evaluation manifest before any fit.
- Compare ranking and calibration as well as episode detection, lead time and
  warning burden. Choose a warning policy using development predictions only.
  If the candidate does not meet the predefined criteria, keep the current
  forecast unavailable. Do not substitute the legacy 30-day artifact.

## Draft Acceptance Criteria

The product owner agreed on 2026-11-12 to a 10% false-alarm-day limit and
5 calendar days of useful lead for the first historical comparison. The
remaining rows describe proposed procedure, not an approved manifest.
Neither limit establishes quality on Russian outcomes or authorizes M04.

| Decision | Status and rule for the first historical comparison |
| --- | --- |
| Comparators | Use the mature training prevalence for probability scoring. Also compare to a rule that warns on high point-in-time stress intensity while stress is known to be absent. Add this second reference to the manifest only after review. |
| False alarms | Agreed: at most 10% of comparable negative origin-days in warning. Count days, not notifications, and report the numerator, denominator and time in warning. Apply the same budget to the candidate and the intensity rule. |
| Useful lead | Agreed: at least 5 calendar days before onset. Report detections at any lead and at useful lead separately. An episode with a late warning is not a timely detection; report misses and non-comparable episodes separately. |
| Threshold selection | Use development predictions only. Within the budget, prefer more timely detections; break ties by fewer warning days, then the higher threshold. If no nonempty policy fits, record no warning policy rather than relaxing the limit. Freeze each threshold before the corresponding outer test. |
| Acceptance | On untouched comparable dates, check the actual false-alarm budget, improvement in timely episode detection against the intensity rule, and Brier improvement against the prevalence reference. Report differences with uncertainty and calendar-fold breakdowns. A point improvement without adequate coverage and precision is not a pass. |

Our own banking-crisis experiments motivate using a fixed false-alarm budget
and measuring episode misses separately: a method can stay within budget and
still miss many episodes. We reuse the budget as a starting point, not the
banking-crisis performance as evidence for daily Russian market stress. The
five-day limit is an analyst workflow hypothesis, not a finding from those
longer-horizon experiments. Validate its usefulness with analysts separately.

Before execution, approve exact fold cutoffs, minimum counts and coverage,
calibration requirements, and uncertainty/acceptance bounds in the manifest.
Undefined metrics (for example, no negative origins) do not count as a pass.
Grouping consecutive alerts and choosing a notification budget are separate
policy decisions. The current scorecard records lead times but does not apply
the five-day cutoff or select operating thresholds.

## Implemented Offline

`models/validation/warning_scorecard.py` ports the research practice of
comparing operating decisions on common origins and grouping hits by event.
It accepts only explicitly synthetic data and does not import a trainer, fit
an estimator, choose a threshold, read external data or change the API.

- Inputs are already matched at-risk dates with mature known labels and two
  frozen warning decisions. The caller supplies confirmed episode onsets
  through the 30-day outcome tail. The scorecard checks each label against
  the supplied next onset; it cannot prove the completeness of that inventory
  or the historical availability of input features.
- A positive origin links only to the next onset in `(t, t+30]`. A covered
  episode counts once per policy; lead time uses the first linked warning.
  Windows spanning a fold boundary and episodes without a matched origin are
  shown separately, not counted as misses or treated as proof of coverage.
- A false-alarm day is a matched negative origin with a warning. The output
  exposes the negative-origin denominator and total warning days. It does not
  yet group consecutive false alarms into notification episodes.

Verification: `.venv-validation/bin/python -m unittest discover -s
tests/model_validation -q` passed 65 tests, including five scorecard tests.
These tests prove accounting rules on invented examples, not model quality.

Next: join this scorecard to the reviewed evaluation manifest, verify the
episode inventory and origin-level feature availability on admitted sources,
and run the first bounded historical comparison after approval.
