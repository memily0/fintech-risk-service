# I05.2: Временное Ядро Милы И Статус Модели

Дата: 2026-11-05. Ветка: `v1/integration-yaroslav`.
Источник: `v1/model-mila`, `eb54d6ed10e8337afc6c0221419936be07f6dadc`.

**Дополнение 09.11.2026:** новый proposed evaluation manifest и model-часть
Q01 описаны в [протоколе оценки](v1_model_evaluation_protocol.md). Он относится
к `ru-domestic-market-stress.1` / `ru_domestic_stress_onset.1`, требует
отдельный as-of snapshot на каждый fold и не разрешает M04.

**Дополнение 06.11.2026:** [постановка задачи](v1_task_definition.md)
согласована: новый рыночный стресс России, 30 календарных дней. Текущее API
`v1-model-readiness.2` отличает business approval от допуска модели;
ниже описан исторический I05.2 до этого решения. Новый onset adapter не меняет
байты импортированного temporal core и прежнюю future-presence цель.

**Дополнение 08.11.2026:** [методика российского стресса](v1_stress_measurement.md)
зафиксирована отдельно от допуска источников и модели. Действует
`v1-model-readiness.3`; исторические результаты I05.2 ниже не переписаны.

## Реализовано

`models/validation/__init__.py` и `temporal.py` перенесены побайтово без изменений.
SHA-256 temporal.py: `b27a08a78aa28607c9f5fdedb7e28cc0a0a7848977e7af8eea9c9b807ed8c947`.
Это обязательные компоненты, unknown/warm-up, календарные окна, зрелость метки
и строгое `label_end < cutoff`. Модуль доступен в wheel как `arcshift_model`;
его pandas/NumPy dependencies являются optional, не частью API startup.

Новый `product.py` проверяет явный synthetic snapshot, все пять стандартизованных
компонент, конечные числа, отдельную дату доступности исходов, date-only origins
и отсутствие молчаливой нормализации intraday/timezone. Подготовленный frame
содержит score/event, nullable target, label_end, mature и complete_window.
Это не генератор причинно корректных признаков из сырых уровней и не модель.

Новые read-only endpoints:

- `/api/v1/models/status`: источник определения, кандидаты 7/30/90, пустой список
  утверждённых горизонтов, input coverage и blockers.
- `/api/v1/signals/current`: `signal=null`, state unavailable или unsupported,
  без выдуманной вероятности, score=0 или загрузки legacy weights.

`v1-model-readiness.1` пока намеренно не умеет serving принятого артефакта.
Параметр пути/имени модели не может включить загрузку файла. Данным соответствует
тот же immutable snapshot, что market API. Во вкладке «Модель» эти статусы
читаются из API. Наличие сырого ряда не означает готовность компоненты/feature.
Сейчас отдельно отсутствуют VIX и IMOEX, а все источники ещё не допущены.

## Проверки

- 149 core/data/API tests, включая 12 новых model-boundary regressions.
- 18 offline temporal tests прошли и в прежнем окружении, и в новом отдельном
  `.venv-validation` на Python 3.14; lock записан по последнему окружению.
- NumPy закреплён на 2.3.4: при пробе 2.5.4 обнаружено предупреждение pandas
  о future timedelta compatibility. Оно не подавлялось; после pin повторено
  18 tests. Starlette/HTTPX warning core test transport остаётся известным.
- HTTP restart: 10 маршрутов, два запуска; snapshots и ledger сохранены.
- Browser: модель/недоступный сигнал, история, прежний private workflow;
  1440/390/320 px, 0 errors/external requests и без document overflow.
- Wheel собирается и работает вне checkout; optional temporal core импортируется
  отдельно, API не импортирует ML stack. В wheel нет датасетов/весов/runtime DB.
- 60 прежних research/contract checks прошли; legacy trainer/CSV/weights сохранены.

Команды: [README](../arcshift_v1/README.md). Это не полная приёмка V1 или M04/M05.

## Что Не Объявлено Завершённым

Не переносился и не запускался trainer Милы: он остаётся baseline-кандидатом,
а конечный evaluation protocol ещё требует freeze. Реальные источники,
approved task/horizons, feature availability, finite evaluation, calibration,
warning policy, accepted artifact и serving остаются открыты. Статус лабораторного
review не заменяет продуктовый допуск. JST не использовался.

Следующий интеграционный блок: расширенные экраны/отчёты Никиты через единый
backend вместо demo actors и отдельного личного SQLite. Отдельно остаются real
data worker, public email/recovery и эксплуатационная приёмка.
