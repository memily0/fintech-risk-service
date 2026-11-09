# Возврат Работы Милы: Temporal Follow-up И M03

Дата: 09.11.2026.

- Участник / task IDs: Мила; M01–M03; model-часть Q01 (A17–A24/A30).
- Ветка / base commit / implementation commit:
  `v1/model-mila-followup-2026-11-09` /
  `3c35411faeff6b1ee2a77edf03b582e58901263c` /
  `acd6eb1797426470f6865e8202b6e092ef077017`.
  Финальный commit отчёта указывается при возврате, потому что файл не может
  содержать собственный SHA без изменения этого SHA.

## Что Реализовано И Что Только Спроектировано

- Исправлен alignment contract `dates/event/target/label_end`: индексы должны
  быть уникальны и точно совпадать; перестановка с исходными labels отклоняется.
- Non-default индекс сохраняется в target, label_end, mature и complete_window.
- Добавлены regressions на reorder, разные/неуникальные индексы и train mask.
- Product fold boundary требует отдельные data/calendar/feature snapshot IDs,
  measurement hash и точный as-of, равный fold cutoff 09:00 МСК.
- Более поздний snapshot запрещён. Late receipt/revision не меняет train rows
  прошлого fold; это проверено recording estimator stub без настоящего fit.
- M03 перепривязан к `ru-domestic-market-stress.1`, target
  `ru_domestic_stress_onset.1` и единственному горизонту 30 календарных дней.
- Подготовлен конечный manifest-кандидат: prevalence baseline, одна L2-logistic
  `C=1.0`, четыре outer/три inner folds, максимум 20 estimator fits, порядок
  preprocessing/calibration/threshold, coverage и обязательные метрики.
- Протокол остаётся `proposed_not_authorized`. M04 не запускался.

Реализован код boundary и synthetic checks. Exact outer dates, admitted feature
schema, warning threshold, business constraints, numeric acceptance bounds и
bootstrap block length только перечислены как обязательные решения до M04.

## Изменённые Модули И Shared Contracts

- `models/validation/temporal.py`: строгий индексный контракт.
- `models/validation/product.py`, `measurement.py`: перенос точного as-of в
  prepared target snapshot.
- `models/validation/evaluation.py`: manifest candidate и synthetic fold batch.
- `tests/model_validation/`: alignment, manifest и late-revision/stub tests.
- `docs/v1_model_evaluation_protocol.md`: M03 и model-Q01 evidence map.
- `docs/v1_model_integration.md`: ссылка на follow-up.

Канонические `stress_definition.py` и `task_definition.py` не дублировались и
не менялись. Формула и `MEASUREMENT_SHA256` импортируются. Frozen handoff
`PACKAGE_CONTENTS.csv` не переписывался, как требовалось в review.

## Зависимости И Окружение

Новых зависимостей нет. Проверено на macOS arm64, Python 3.13.7:

- validation: NumPy 2.3.4, pandas 2.3.3, точный `requirements-validation.lock`;
- application: точный `requirements-v1.lock`, editable package без новых deps;
- `pip check`: OK в обоих окружениях.

Репозиторные locks ранее проверялись интеграцией на Python 3.14. Этот follow-up
дополнительно воспроизведён на доступном Python 3.13.7; production compatibility
или новый lock этим не объявляются.

## Запуск Из Чистого Checkout

```sh
python3 -m venv .venv-validation
.venv-validation/bin/python -m pip install -r requirements-validation.lock
PYTHONDONTWRITEBYTECODE=1 .venv-validation/bin/python -m unittest discover -s tests/model_validation -v
.venv-validation/bin/python -m pip check

python3 -m venv .venv-v1
.venv-v1/bin/python -m pip install -r requirements-v1.lock
.venv-v1/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv-v1/bin/python -m unittest discover -s tests -q
.venv-v1/bin/python -m pip check
```

В приложенном handoff была старая команда `-s tests -p
test_temporal_validation.py`. После интеграции validation tests находятся в
`tests/model_validation/`; использована актуальная эквивалентная команда выше,
чтобы не добавлять pandas в runtime environment.

## Фактические Результаты Tests

- Validation suite: 68 tests, OK.
- Application suite: 171 tests, OK.
- `pip check`: OK в двух окружениях.
- `git diff --check`: exit 0.
- `git diff --exit-code 3c35411 -- models/artifacts data/model_metrics.json
  data/model_predictions.csv`: exit 0; старые weights/metrics/predictions не
  изменены.
- Известное `StarletteDeprecationWarning` для FastAPI TestClient/HTTPX сохранено;
  оно существовало до follow-up и не влияет на результаты.

Regression evidence: на исходном `3c35411` новый alignment-набор дал 3 failure
из 22 (`event` reorder, different index, reordered target). После исправления
все 22 прошли. Первый application запуск системным Python дал 9 import errors
из-за отсутствия FastAPI/installed `arcshift_data`; после создания lock-based
`.venv-v1` все 171 tests прошли. Model/evaluation failed runs отсутствуют.

## Данные, Права И Модель

- Данные: только invented synthetic observations/calendars/features.
- Snapshot IDs в тестах явно synthetic; provider network не использовался.
- Права: source admission/model-use/export/API decisions остаются pending.
- Задача: `ru_market_stress_onset_v1`, target
  `ru_domestic_stress_onset.1`, measurement `ru-domestic-market-stress.1`,
  горизонт 30 calendar days, cutoff 09:00 Europe/Moscow.
- Artifact/version: no fit, no new weights, no candidate artifact.
- Model quality, calibration, economic impact и empirical measurement validity
  не установлены.

## Security, Совместимость И Rollback

Сетевых запросов, credentials, personal data, customer portfolios, downloads,
DB migrations и production side effects нет. Feature/target snapshots обязаны
иметь точные version IDs; более поздний as-of не допускается в старый fold.

Изменений публичного API и storage schema нет. Rollback: revert implementation
commit `acd6eb1797426470f6865e8202b6e092ef077017`; existing artifacts/data не
требуют восстановления, потому что не изменялись.

## Открытые Ограничения И Следующие Шаги

M04 блокируют:

1. admitted source/data/feature snapshots и права model use;
2. проверенные provider calendars/availability на 09:00 МСК;
3. exact feature schema и missingness policy;
4. утверждённые exact outer/inner cutoffs;
5. решение Ярослава/product owner о warning burden или стоимости ошибок,
   threshold rule, numeric acceptance bounds, bootstrap block length и policy ID;
6. независимый review Ярослава и Насти и явное разрешение finite fit.

После разрешения M04 выполняется только утверждённый максимум 20 fits, все
failed/negative results сохраняются, outer test не используется для выбора.
M05 затем отдельно проверяет exact schema/hash, task/target/horizon/cutoff,
dependency lock, registry, unavailable behavior, serving compatibility и rollback.

- Screenshots/E2E/restore: неприменимо к этому model follow-up.
- Что нужно от другого направления: D — admitted snapshots/rights/coverage;
  I/Ярослав — threshold/business constraints и shared artifact contract.
- Reviewer: Ярослав и Настя по time/source semantics; independent re-review pending.
- `main` не изменялся и не сливался.
