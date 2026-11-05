# Архитектура Переноса В Продукт

Сохраняем существующий `fintech-risk-service`: сборка данных в `scripts/`,
данные в `data/`, веса в `models/artifacts/`, Streamlit в `app/dashboard.py`,
методология в `docs/`. Для первого шага не нужен новый сервис или framework.

## Разделение Задач

| Слой | Что делает | Чего не обещает |
| --- | --- | --- |
| Daily stress proxy | Нынешняя задача: пересечение собственного composite-stress порога в следующие 7/30/90 календарных дней | Не вероятность системного банковского кризиса или borrower PD |
| Macro vulnerability research | P1 quarterly и P2-A annual с отдельными разметками и популяциями | Не ежедневный торговый сигнал и не drop-in замена MVP |
| B2B context adapter | Передаёт контекст и признаки в согласованный workflow клиента | Не измеренный эффект на PD/LCR/капитал без отдельной модели и данных |
| Decision/impact evaluation | Будущий пилот одной метрики и одного решения | Не существующая доказанная экономическая ценность |

Выходы разных задач храним с разными `task_id`, target definition, horizon,
frequency, coverage и model version. Не усредняем их вероятности и не переносим
annual/quarterly score на daily grid как будто это тот же прогноз.

## Поток

```text
Разрешённые первичные источники
  -> сохранённые snapshot и metadata
  -> quality / availability / freshness checks
  -> task-specific features and mature targets
  -> train / validation / calibration / outer evaluation
  -> versioned candidate model and threshold policy
  -> acceptance decision
  -> structured signal + validity status + evidence
  -> dashboard / export / approved B2B adapter
  -> monitoring and rollback
```

Оригинальные research inputs остаются read-only вне production-data pipeline.
Внутренние интервью, контактные данные, письма и ответы экспертов не становятся
входными признаками и не копируются в публичный продукт. Переносим требования
и обезличенные выводы, не документы с личными сведениями.

## Минимальный Контракт Сигнала

- `task_id`, `target_definition_id`, `model_version`, `data_snapshot_id`.
- `forecast_origin`, `information_as_of`, `generated_at`, `latest_source_dates`.
- `geography`, `frequency`, `horizon_value`, `horizon_unit`.
- `score`, `score_kind`, `calibration_status`, `threshold_policy_id`.
- `validity_status`: valid / stale / missing / unsupported / historical_demo.
- `coverage`, `missing_features`, `source_rights_status`, `validation_version`.
- `drivers` с единицами вклада и явным отсутствием causal interpretation.
- `review_action` как предложение проверки аналитиком, не исполняемая команда.

Не добавлять фиктивный confidence percentage. Выход weighted/balanced logistic
regression не следует автоматически называть откалиброванной вероятностью.
Для численного uncertainty нужны подходящая методика и её проверенные inputs;
пока такого результата нет, использовать явный unavailable/not_estimated.

При stale/unsupported состоянии не выдавать зелёный сигнал как доказательство
низкого риска и не подменять отсутствующий прогноз последним известным score.

## Как Использовать Исследовательские Модели

P1 даёт benchmark и требования к оценке, а не готовую global serving model.
P2-A checkpoints исторические, привязаны к двум folds и JST; коммерческого
разрешения нет. Их можно сохранять локально для разрешённого исследования,
но не подключать к платному сервису или выдавать за обученную текущую модель.
Альтернативные модели команды возвращаются в очередь проверки target,
chronological split, maturity и source rights, а не автоматически принимаются.

Первый перенос из исследования — **методология оценки и прозрачность сигнала**.
Обучение нового product candidate, его допуск и deployment — следующие отдельные
шаги, с сохранением старого baseline и возможности отката.
