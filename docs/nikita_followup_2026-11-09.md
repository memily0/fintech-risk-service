# Возврат Никиты · обзор, наблюдение и очередь

Дата 09.11.2026. Задачи U02/U03, A23/A25/A26/A27/A31.
Ветка `v1/ui-nikita-followup-2026-11-09`.
База `3c35411faeff6b1ee2a77edf03b582e58901263c`.
База и изменения общего UI/API согласованы Никитой в чате 09.11.2026.
Итоговый SHA выдаёт `git rev-parse HEAD`.

## Реализовано

- Общий FastAPI-workbench использует каталог и истории market API. Обзор показывает ряды независимо от текущего сигнала. Поддержаны пустая история, отсутствие актуальной ревизии, отсутствующий USD/RUB, null и числовой ноль. График выбирает доступный ряд и разрывает линию на пропусках.
- Каталог и история сверяют `data_snapshot_id`. При смене A/B UI повторяет загрузку один раз. Если снимки продолжают расходиться, показывает обновление и предлагает повторить проверку. Подпись истории берётся из её ответа. Поздний ответ предыдущего запроса отбрасывается счётчиком поколения.
- Дата наблюдения, время получения и время проверки интерфейса показаны отдельно. Время публикации сохраняется nullable. Обзор показывает «Свежесть не оценена», пока API не передаёт отдельного решения.
- Отдельный watchlist показателей принимает устойчивые `series_id`. Кнопка каждого сохранённого показателя открывает его историю. Прежние `scenario_ids` сохраняются в прежней таблице и выдаче, с отдельной подписью в UI.
- Очередь содержит два исторических synthetic-примера. Системный `warning_id` определяется `signal_id` и версией политики. Примеры публикуются при старте явно, HTTP-чтение очереди их не создаёт. Повторный старт и refresh сохраняют ID. Два пользователя имеют отдельные review и заметки. Одновременное начало одного разбора идемпотентно.
- Review связывается с warning и исходным market snapshot. Создание отчёта для такого review читает сохранённый снимок, включая случай смены активного указателя. PDF/CSV/JSON используют существующие защищённые маршруты. В них сохраняются warning/signal/policy IDs. Прежние review и saved reports поддержаны через nullable поля.
- Экран модели читает точный task ID и версию из `GET /api/v1/models/task`, сверяет их с model status и measurement. Допуск модели и политика предупреждений показываются отдельно.

## Контракты и изменения

| Маршрут | Кандидат контракта |
|---|---|
| GET/PUT `/api/v1/workspace/indicator-watchlist` | `v1-local-indicators.1`, `series_ids`, максимум 13 уникальных поддерживаемых ID |
| GET `/api/v1/workspace/warnings` | `v1-local-queue.1`, общие immutable warnings и review текущего владельца, limit/offset |
| POST `/api/v1/workspace/warnings/{UUID}/review` | Идемпотентно возвращает личный review, общий CSRF и ограничения записи |
| Existing reviews и saved reports | Nullable `warning_id`, `signal_id`, `policy_id`, `data_snapshot_id` в review |

В CSV отчёта добавлены три колонки связи с предупреждением. Числовые значения и существующие колонки сохранены в прежнем порядке. При пустой истории остаются заголовки.

Изменены `arcshift_v1/static/app.js`, `app.css`, `index.html`, общий workspace, API startup, чтение сохранённого market snapshot и report renderer. Добавлены `warning_queue.py` и migration 006. Применённые migrations 001–005 сохранены. Runtime-зависимости берутся из существующего `requirements-v1.lock`. Новых runtime-пакетов нет.

## Запуск

Проверено на Windows, Python 3.14.0. Из корня checkout.

```powershell
python -m venv .venv-v1
.venv-v1/Scripts/python.exe -m pip install -r requirements-v1.lock
.venv-v1/Scripts/python.exe -m pip install --no-build-isolation --no-deps -e .
$env:ARCSHIFT_PORT='8780'
$env:ARCSHIFT_DB_PATH='.cache/nikita-preview.sqlite3'
$env:PYTHONUTF8='1'
.venv-v1/Scripts/python.exe -m arcshift_v1
```

Открыть [локальный workbench](http://127.0.0.1:8780/).
Отчёты используют включённый в интеграцию Liberation Sans. Внешний Arial и переменная шрифта Streamlit-прототипа этому runtime не требуются.

## Проверки

```powershell
$env:PYTHONUTF8='1'
.venv-v1/Scripts/python.exe -m unittest discover -s tests -q
.venv-v1/Scripts/python.exe -m unittest discover -s tests -p test_v1_warning_queue.py -v
.venv-v1/Scripts/python.exe -m pip install playwright==1.59.0
.venv-v1/Scripts/python.exe -m playwright install chromium
.venv-v1/Scripts/python.exe tools/check_nikita_workbench.py
.venv-v1/Scripts/python.exe -m pip check
node --check arcshift_v1/static/app.js
git diff --check
```

Core/API suite содержит 176 тестов. На этой Windows-машине 175 проходят. Унаследованная проверка `test_database_restricted_permissions_and_event_log_has_no_credentials` ожидает POSIX mode 0600, Windows возвращает 0666. Это открытая платформенная проверка прав хранения. При явном исключении указанного теста остальные 175 прошли. Ошибка полного первого прогона и это исключение зафиксированы раздельно. Сохраняется прежнее предупреждение Starlette TestClient об HTTPX.

Новые пять тестов очереди прошли. Повторно прошли 19 проверок saved reports и 16 workspace. Проверена конкурентная идемпотентность, старый snapshot после публикации нового, отдельность watchlists, запрет чужих review и чтение сохранённого отчёта прежнего контракта.

Браузерный инструмент запускает собственный временный loopback-сервис и удаляет свою synthetic DB после проверки. Он проверяет null/0/empty/no-current/без USD-RUB, отказ одного ряда, loading, stale/missing/market_closed/error на fake API, смену каталога A/B и постоянное расхождение снимков. Второй проход использует настоящий общий API, две независимые cookie-сессии и две вкладки одной сессии.

| Приёмка | Результат |
|---|---|
| A23 | Два разных warning ID, двойной refresh сохраняет две строки. Одновременное начало создаёт один review владельца. |
| A25 | Личный статус и заметка сохраняются через общий API, optimistic revision и терминальные переходы проверяются существующими tests. |
| A26 | Indicator watchlist отделён от старого scenario watchlist. Переход в историю использует series ID. Два owner имеют независимые списки. |
| A27 | Сохранённый отчёт и все три скачивания проверены. После смены active snapshot старый warning создаёт отчёт по исходным наблюдениям. |
| A31 | Чужие review и saved-report IDs возвращают 404, после logout отчёт возвращает 401. Вторая вкладка очищает private state. Второй аккаунт сохраняет свою сессию. |
| UI | 375/768/1440 px, клавиатура, текст 200%, длинные ID и даты, отсутствие горизонтального overflow документа и внешних запросов. |

Первые браузерные прогоны обнаружили переполнение summary при 200% на 768 px и влияние общего SVG-стиля на высоту графика. Исправлены перенос текста, tablet-grid и размер графика. Все browser assertions проходят после исправлений.

[Обзор 375](../output/playwright/nikita-followup/overview-375.png) · [768](../output/playwright/nikita-followup/overview-768.png) · [1440](../output/playwright/nikita-followup/overview-1440.png) · [Разбор 200%](../output/playwright/nikita-followup/review-768-zoom200.png)

## Данные, доступ и совместимость

Только synthetic parser fixtures из базы интеграции. Market snapshot определяется content hash. Fixture snapshot сценария, `synthetic-signal-<sha256>` и `synthetic-queue-policy.1` сохранены в warning. Два примера имеют одинаковые условные значения из исходного исторического сценария и разные иллюстративные signal IDs A/B. Политика является fixture для проверки процесса.

Данные, заметки и пароли тестов вымышлены. Сессии, CSRF, лимиты и owner checks переиспользуют общий backend. Секреты, токены и runtime SQLite в артефакты не входят. Наблюдения для реального display/model use/export/API ожидают source-specific admission. Модельные fit, provider-запросы, внешняя почта и production deploy в этом пакете отсутствуют.

Migration 006 создаёт новые таблицы, сохраняя прежние записи. До обновления рабочей DB нужна её резервная копия. Старый код со schema 005 откажется открывать schema 006. Для отката к прежнему runtime используют копию до обновления. Приведённый preview запускается с отдельной DB в `.cache`.

## Открыто для review

- Ярослав проверяет additive API/schema, migration 006, лимиты и связи warning–review–report. Общая production-политика очереди, retention и объёмы требуют отдельной приёмки.
- Настя согласует серверное поле свежести и календаря. Сейчас stale/missing/market_closed/error проверяются на явно synthetic fake responses, текущий market API не выдаёт эти статусы.
- Мила проверяет семантику исторических примеров, task/measurement IDs и допуска. Рабочий сигнал остаётся null до M04 и допуска входов.
- Дальнейшие production load/security/restore, реальная регистрация/recovery, источники и прогноз относятся к владельцам интеграции.

Reviewer — Ярослав, семантика сигналов — Мила. Пользовательский feedback собирается отдельно.
