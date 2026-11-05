# Постоянное Обновление Данных ArcShift V1

Дата проверки: 05.11.2026. Пользователь включил постоянное получение данных
и автоматически обновляемый dashboard в требования первой полноценной версии.
Это подтверждённое требование, но ниже предложены архитектура и интервалы,
а не уже работающий feed, оплаченный тариф или разрешённый acquisition run.

Уточнение scope: Россия является основой V1, международные ряды нужны
как внешние факторы. Казахстан отдельно не подключаем. Доступ к продукту
публичный с регистрацией, не invitation-only. Платные market feeds пока
не согласованы: сначала проверяем допустимые варианты в инфраструктурной
рамке бюджета. Регистрация не заменяет права на публичный display/export/API.
См. [спецификацию](v1_product_specification/README.md).

## Что Считаем Живым Дашбордом

Dashboard показывает последние допустимые наблюдения и автоматически
обновляется, сохраняя время наблюдения, публикации и получения. Для каждой
серии отдельно виден режим: real_time / delayed / end_of_day / macro_release /
market_closed / stale / unavailable. Не называем весь экран real-time, если
часть данных приходит с задержкой или имеет месячную частоту.

Обновление браузера, получение нового наблюдения, inference и переобучение
являются разными операциями. Частый refresh не устраняет задержку поставщика.

## Текущая Исходная Реализация

- `scripts/build_final_dataset.py` строит преимущественно дневной CSV batch.
  Он использует ЦБ РФ, дневной Brent EIA, CPI и yfinance для части рынков.
- `app/dashboard.py:114`, `:133`, `:149` читают локальные CSV/JSON под
  `st.cache_data` без TTL и без fingerprint входного snapshot.
- Постоянный ingest worker и live snapshot API в просмотренных файлах
  отсутствуют. Простое изменение CSV не гарантирует обновления кэшированного UI.
- Прежний датасет заканчивается 07.06.2026; он остаётся historical snapshot,
  не текущей обстановкой на 05.11.2026.

## Источники И Частоты

| Семейство | Проверенный вариант | Что нужно решить |
| --- | --- | --- |
| Российские рыночные показатели | [MOEX ISS](https://www.moex.com/a2920): market data, история, delayed-доступ и real-time subscription | Точный набор доступных инструментов, timestamps, задержка, display/non-display/redistribution entitlement и тариф |
| Официальные валютные курсы и ключевая ставка | [Сервисы ЦБ РФ](https://cbr.ru/development/dws/): датированные официальные значения и история | Регламент публикации, effective date, частота проверки, разрешённое использование; официальный курс не intraday spot quote |
| Brent для дневной истории | [EIA Europe Brent Spot FOB](https://www.eia.gov/dnav/pet/hist/RBRTED.htm): дневная серия | Сохранить именно spot definition; проверять после обновления источника; это не биржевой поток Brent futures |
| Международные индексы, VIX и gold | Для V1 нужен поставщик с подходящим instrument coverage и commercial display/use rights | Провайдер, бюджет, exchange entitlements, задержки, лимиты и история пока не выбраны |
| Инфляция, ВВП, кредит и иная макростатистика | Первичный владелец конкретной серии после source admission | Обновлять по релизам и учитывать пересмотры; monthly/quarterly observation нельзя выдавать за новый tick |

[MOEX tariffs](https://www.moex.com/s1147) отдельно различают получение данных
и дальнейшее распространение, включая delayed display. Бесплатный endpoint
или пользовательская подписка сами по себе не подтверждают право показа
котировок клиентам ArcShift. Суммы и конкретные договорные условия здесь
не выбираются; соответствие текущему способу использования ещё проверить.

[yfinance README](https://github.com/ranaroussi/yfinance) обозначает research /
educational purpose и предупреждает о правах на Yahoo data. Лицензия Python
библиотеки не заменяет согласование прав и надёжности production feed.
Не делаем Yahoo/yfinance безусловной основой коммерческого live dashboard.

Нельзя тихо заменить официальный FX rate биржевой ценой, Brent spot фьючерсом,
gold futures spot gold или индекс ETF-прокси. Новая серия получает отдельный
instrument ID, определение, units и решение о применимости в model features.
Поддержку конкретного FX-инструмента нельзя вывести из общей доступности ISS.

## Предлагаемая Архитектура

```text
Разрешённый API/feed
  -> provider adapter + ограничение запросов
  -> immutable response/snapshot и receipt
  -> schema / units / instrument / timestamp checks
  -> normalised observations + latest valid view
  -> read API/cache
  -> автоматически обновляемый dashboard

Проверенные наблюдения нужной частоты
  -> task-specific feature snapshot
  -> inference выбранной frozen serving model
  -> versioned signal с отдельным information_as_of
```

Один серверный worker получает данные для всех пользователей. Browser sessions
читают API/cache; каждый открытый экран не создаёт новый поток запросов
к бирже. Backfill истории отделён от incremental updates. Snapshot публикация
атомарна, повторная обработка идемпотентна, late/out-of-order значения и
исправления сохраняются версиями. Компонент хранения выбирается после оценки
нагрузки; наличие live updates само по себе не требует Kafka или микросервисов.

Для рыночного адаптера поддерживаются polling либо streaming, в зависимости
от контракта поставщика. В обоих случаях обязательны rate limits, bounded
retry/backoff, timeout, журнал последнего успеха и контролируемый reconnect.
Новые сетевые попытки не выполняются по старым исчерпанным research budgets.

## Предложенные Цели Обновления

- UI/read API: ориентир 15-60 секунд для активного экрана, после load/rate review.
- Market polling: ориентир 1-5 минут для выбранного delayed/intraday режима,
  либо streaming при разрешённом real-time feed. Это не SLA поставщика.
- Официальные daily/macro releases: проверка по расписанию публикации и
  ограниченный повтор, без бессмысленного постоянного запроса неизменной серии.
- Модельный сигнал: по завершённому feature snapshot и валидированной частоте.
  Нынешнюю daily модель нельзя объявить минутной, подавая в неё неполный bar.
- Переобучение: отдельный контролируемый job после data/validation/release checks,
  не на каждом tick и не при открытии страницы.

Итоговые интервалы, режимы работы рынков, timezone, доступность и допустимый
возраст каждой серии фиксируются после выбора coverage, прав и deployment.

## Контракт Свежести

У каждой записи: provider, series/instrument ID, definition version, value,
units, currency, observation/event time, effective period, publication time
(если известен), received time, timezone, revision/snapshot ID и quality flags.
Для feed также latency mode, известная задержка, market/session status и
entitlement scope. Неизвестный publication timestamp остаётся unknown.

UI отдельно показывает время последних данных и время последней проверки.
Успешный HTTP ответ с прежним значением не делает observation свежим.
Порог stale зависит от серии, торгового календаря и публикационного регламента.
При disconnect/stale остаётся последнее значение с предупреждением; оно не
выдаётся за live и не создаёт новый actionable alert из старого сигнала.

## Приёмка V1 Live Layer

1. Согласованы series IDs, определения, rights/entitlements, режим задержки
   и конечный request budget по каждому провайдеру.
2. Доказано получение и сохранение нового observation с реальными timestamps;
   изменение UI/cache не считается таким доказательством.
3. Проведены tests: duplicate, out-of-order, late revision, timeout, HTTP 429,
   недоступность, reconnect, market closed и рассинхронизация времени.
4. UI обновляется без ручного перезапуска и не показывает stale как live.
5. Данные, признаки и модельный сигнал имеют согласованные версии/as-of;
   последний сигнал может быть старше рыночного tick и это видно пользователю.
6. Проверены provider rate limits, отсутствие ключей в client/log/export,
   доставка мониторинга и восстановление после сбоя worker.

Это отдельный сквозной блок V1 01 / V1 03 / V1 04 / V1 05. Он может
разрабатываться параллельно с исправлением model validation. Сам live слой
не подтверждает predictive quality, экономическую пользу или global coverage.

В этом шаге изучены код и официальные документационные страницы. Jobs,
подписки, новые численные downloads, обучение и deployment не запускались.
