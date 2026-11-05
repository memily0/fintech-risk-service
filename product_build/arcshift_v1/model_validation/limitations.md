# M01–M03 Limitations And Blockers

- Only synthetic temporal helpers were executed. No provider request, dataset
  rebuild, model fit, artifact write, prediction generation or metric refresh
  was performed.
- Target threshold, component set and horizons remain candidates. The code makes
  inherited semantics explicit but does not approve them for V1.
- The strict calendar-day helper requires a row for every calendar date. A
  future approved session-calendar task needs a separately versioned calendar
  implementation and tests; it must not reuse these labels by changing wording.
- The legacy dataset lacks sufficient point-in-time publication/receipt lineage
  for a production claim. DS01–DS12 and all model-use rights remain open.
- The legacy training script is corrected for warm-up, unknown outcomes and
  fold maturity, but running it is still prohibited until an M04 manifest is
  approved. Its existing outputs and binary artifacts have not been renewed.
- Exact outer cutoffs, calibration eligibility, block-bootstrap length,
  threshold burden/cost and numeric acceptance bounds cannot be honestly frozen
  before task, source and product decisions. They are explicit M03 gates.
- Synthetic unit tests establish boundary behavior, not predictive quality,
  calibration, business impact, production fitness or source permission.
- M05 inference schema/hash/dependency/rollback validation cannot begin before
  an M04 candidate exists and I04 defines the serving boundary.
- Overall Q01 for A01–A40 is shared work. This delivery maps only the
  model-relevant A17–A24/A30 scenarios and does not close any release gate.
- Independent review by Yaroslav and Nastya is still required. The author has
  not self-approved the model validation.
