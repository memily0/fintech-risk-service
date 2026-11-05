# Возврат Работы — Мила

- Участник / task IDs: Мила; M01, M02, M03; model subset of Q01 (A17–A24/A30).
- Ветка / base commit / итоговый commit: `v1/model-mila` / `4ae0778` / no commit yet.
- Что реализовано и что только спроектировано: executable nullable temporal
  helpers and synthetic regressions implemented; target/split and claims
  specified; finite evaluation protocol designed but not frozen or run.
- Изменённые модули и shared contracts: `models/validation/temporal.py`, legacy
  trainer consumes helpers, model-validation evidence added; shared candidate
  data/API schemas were not changed.
- Новые зависимости и причина: none; uses existing pandas.
- Запуск из чистого checkout: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests/test_temporal_validation.py`.
- Выполненные tests, точные команды и фактический результат:
  `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests/test_temporal_validation.py`
  — 9 tests, OK; `PYTHONDONTWRITEBYTECODE=1 python3 product_build/arcshift_v1/tools/check_bundle.py`
  — 8 tests, OK; `PYTHONDONTWRITEBYTECODE=1 python3 scripts/train_crisis_model.py --help`
  — exit 0 without fit or writes; `git diff --check` — exit 0.
- Не выполненные tests и причины: M04 model evaluation and M05 inference tests
  are gated by approved task/sources/manifest/artifact and I04 serving contract.
- Данные: synthetic only; no real snapshot/source/definition admission claimed.
- Права: no source-purpose decision changed; all candidate-contract modes remain denied pending admission.
- Модель: candidate calendar-day future composite event; inherited 7/30/90 and
  threshold 1.0 remain unapproved; expanding temporal design; no fit/artifact/version.
- Таблицы/метрики/ошибки/limitations; failed runs тоже перечислить: no model
  metrics or runs; `model_validation/claims_matrix.csv`, `limitations.md`.
- Screenshots/E2E/restore/rollback evidence где применимо: not applicable to M01–M03.
- Security/privacy: no network, secrets, personal records, provider data or restricted artifacts used.
- Обратная совместимость и migrations/rollback: no schema migration; revert the
  trainer import/use plus remove the new module to restore legacy behavior.
- Незакрытые проблемы и release blockers: task/horizons/calendar, source rights
  and point-in-time availability, immutable snapshot, numeric success bounds,
  warning policy, independent review, M04/M05/I04.
- Что нужно от другого направления: D01 decisions and admitted snapshot; I01/I04
  shared signal/inference contract; product-approved warning burden/cost;
  independent Yaroslav/Nastya review.
- Reviewer и итерация проверки: proposed Yaroslav + Nastya; iteration 0 pending.
