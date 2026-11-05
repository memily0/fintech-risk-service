# Возврат работы Насти: D01-D03

- Участник / task IDs: Настя / D01, D02, D03.
- Ветка / base commit / итоговый commit: `v1/data-nastya` / `4ae0778` / HEAD этой ветки.
- Реализовано: candidate source registry; чистые FX, curve и CPI parsers;
  file-based revision store; atomic publish; idempotency; one-scheduler lock;
  bounded retry для timeout/429; явные fixture freshness/calendar states.
- Только спроектировано: реальные provider probes, live scheduler, admitted
  production storage и provider-specific calendars. Они требуют решений D04+.
- Изменённые модули и shared contracts: добавлены `src/arcshift_data`,
  `config/arcshift_source_registry.json`, `tests/test_data_lane.py`; frozen
  candidate contracts из handoff не менялись.
- Новые зависимости: нет; используется только Python standard library.
- Запуск из чистого checkout:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v`.
- Выполненные tests: 20 новых data-lane tests, `OK`; 27 исходных contract
  tests через handoff `.venv`, `OK`; `git diff --check`, без ошибок.
- Исходный `tools/check_bundle.py`: 7 из 8 tests прошли, 1 упал на уже
  существовавшем в base расхождении SHA-256 для `evidence/evidence_to_product.csv`:
  manifest `076a7122...`, фактический base/checkout `f4f70d8c...`. Frozen handoff
  не менялся в этой ветке, поэтому manifest автоматически не переписывался.
- Не выполнены: real provider connectivity, D04 probes, E2E UI/model, load,
  restore и rollback tests — для них нет admission/интегрированного RC.
- Данные: только synthetic provider-shaped payloads внутри tests. Новые реальные
  snapshots, raw provider responses и model artifacts не создавались.
- Права: `D01-RIGHTS-PENDING-PER-PURPOSE`; display/model/export/API остаются
  pending для каждого источника. Technical probe/backfill/incremental budget = 0.
- Модель: fit не запускался; target, horizons, features и artifacts не менялись.
- Security/privacy: сеть не используется; secrets и персональные данные не
  читаются; real observations блокируются до source admission.
- Обратная совместимость: legacy builder/data/weights не изменены. Rollback —
  удалить новые `src/arcshift_data`, config, tests и этот документ.
- Незакрытые blockers: exact Rosstat resource/dimension codes; права по purpose;
  CBR/MOEX curve origin; providers для S&P 500 и gold; provider calendars;
  finite D04 probe decision; storage contract review с integration owner.
- Нужно от других направлений: Ярослав — review storage/write boundary; Мила —
  review feature availability; Никита — review freshness vocabulary.
- Reviewer и итерация: требуется Ярослав; availability дополнительно Мила.

## Ограничения

`receipt_freshness_state` проверяет возраст fixture receipt и явное состояние
календаря. Это не production SLA и не доказательство свежести наблюдения.
Парсер CPI требует передать полный набор заранее проверенных dimension codes;
встроенных реальных codes нет, потому что официальный binding ещё не подтверждён.
Структурные tests не дают права использовать источник и не закрывают release gate.
