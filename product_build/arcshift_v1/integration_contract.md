# Общая Граница Интеграции

Статус: кандидат для K0. Полнота описания не означает approved scope.
Owner shared schema предлагается Ярослав; изменения review всеми линиями.

## Данные

Использовать candidate_contract.json и observation.schema.json в
research/08_product_handoff/v1_data_contract/. Неизвестные source bindings
и dimension codes оставлять незаполненными с причиной, не угадывать.
Каждая запись имеет IDs/units/reference period, publication nullable,
receipt с timezone, revision/snapshot и quality. Unknown не превращать в 0.
Отдельно нужны закрытие session, freshness/calendar и admission по purpose.

## Признаки И Модель

Feature snapshot содержит ID, task, information_as_of, parents/definitions,
feature schema/version и missingness. Temporal model labels имеют явный
label_end и только зрелые train labels. Будущая метка, известная сегодня,
не считается известной на исторический train cutoff.

Signal: task_id, target_definition_id, model_version, feature/data snapshot IDs,
forecast_origin, information_as_of, generated_at, geography/frequency/horizon,
score и score_kind, calibration status, validation/policy IDs, validity и drivers.
Для unknown/stale/unsupported нет зелёного current risk. Historical_demo,
fitted, OOS и live различаются. Нет выдуманного confidence percentage.
Drivers в logit units не называются причинными эффектами или probability points.

## Предупреждения И Личное Состояние

Системное warning связано с immutable signal и policy. Его identity/dedup
определяется событием/политикой, не refresh браузера. User review хранится
отдельно: new, acknowledged, in_review, closed, dismissed. При closed/dismissed
есть заметка и audit timestamp. Это не ground truth о правильности модели.
Watchlists, settings, notes, generated reports имеют owner ID на сервере.

## API И UI

UI не вызывает provider download или fit. API обслуживает уже опубликованные
snapshots. Все protected ресурсы проверяют actor/owner; смена ID в URL не
даёт доступ. Read API для history/signals и writes личного состояния разделены.
Для loading/empty/stale/unavailable/unsupported есть разные ответы и UI states.
Тяжёлые reports/exports ограничиваются отдельно от интерактивных запросов.

## Fixture Boundary

fixtures/ui_scenarios.json не является provider response или training data.
Каждый сценарий synthetic=true; никаких claims текущего риска на его основе.
fixtures/observation.json соответствует синтетическому candidate example.
Known-by check не является freshness check или license approval.

## Release Boundary

Immutable code/config/model/schema versions и source admission регистрируются
до serving. Изменение договора/источника может изменить разрешённый export.
Старые binary models не загружать из произвольных user uploads.
Новый fit, bulk download, sender email или infrastructure action не являются
побочным эффектом unit tests, открытия dashboard или запуска API.
