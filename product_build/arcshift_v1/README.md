# ArcShift V1: Пакет Параллельной Разработки

Дата снимка: 05.11.2026. Россия является основным рынком, международные
показатели дают внешний контекст. Отдельного направления Казахстана нет.
Цель: полноценный публичный сервис с регистрацией, не ещё один demo MVP.

## С Чего Начать

1. Прочитать [параллельный план](parallel_plan.md), затем своё задание в team/.
2. Проверить [состояние проекта](current_state.md) и [границы публикации](publication_boundary.md).
3. Использовать [общие контракты](integration_contract.md), не придумывать
   несовместимые units, timestamps, task IDs и warning states в своей ветке.
4. Создать собственную рабочую ветку от этой handoff-ветки. Не работать
   одновременно в одной ветке и не выполнять автоматическое слияние в main.
5. Вернуть код, tests, ограничения и [отчёт по шаблону](team/return_template.md).

| Участник | Предлагаемое направление | Задание |
| --- | --- | --- |
| Ярослав | Контракты, backend, интеграция и инфраструктурная сборка | [Задание](team/yaroslav.md) |
| Настя | Источники, source admission и ingest | [Задание](team/nastya.md) |
| Мила | Корректность target, temporal validation и модельная приёмка | [Задание](team/mila.md) |
| Никита | Интерфейс, workflow и представление отчётов | [Задание](team/nikita.md) |

Распределение предложено для согласования загрузки команды, не является
подтверждением выполненной работы или назначением production on-call.

## Что Уже Доступно

Кодовая основа находится в корне ЭТОГО репозитория, а не в копии внутри
пакета: app/dashboard.py, scripts/build_final_dataset.py,
scripts/train_crisis_model.py, requirements.txt. Базовый commit записан
в publication_manifest.json. Не создавайте вторую независимую кодовую базу.

Дополнительные материалы собраны в одной папке:

- research/08_product_handoff/: полный план, specification, 40 acceptance
  scenarios, 22 release gates, source audit и текущий candidate data contract.
- research/tools/release/: переносимый offline contract checker и synthetic tests.
- evidence/: обезличенные выводы исследований/интервью и связь с требованиями.
- legacy_reference/: прежние model card, methodology и validation report
  с предупреждением о найденных после их написания проблемах.
- fixtures/: явно синтетические примеры для UI, API и контрактов.
- work_packages.csv: задачи, зависимости, владельцы модулей и критерии готовности.

Первоначальные документы сохраняют свои датированные статусы. В частности,
раннее Git_transfer_authorized=false относится к отменённому переносу
полного research archive. НОВЫЙ запрос пользователя разрешает публикацию
именно этого отобранного пакета, а не закрытых интервью и ограниченных данных.

## Проверки После Клонирования

Из корня product_build/arcshift_v1:

```sh
python3 tools/check_bundle.py
```

Offline контрактные tests требуют jsonschema с format checker и системную
базу часовых поясов. Установка выполняется в отдельное окружение, не в
research runtime другого участника:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements.test.txt
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/tools/release .venv/bin/python -m unittest -v test_v1_data_contract
```

Структурные проверки и synthetic tests не доказывают качество модели,
работоспособность реального API или разрешение использовать данные.
Старые команды rebuild/train из legacy docs не являются командой старта:
они могут скачивать историю и перезаписывать artifacts. Сначала читать задание.

Внутри пакета нет полноценного production-сервиса. Запуск сайта, данные,
модели, безопасность, staging и приёмка остаются работой соответствующих этапов.
