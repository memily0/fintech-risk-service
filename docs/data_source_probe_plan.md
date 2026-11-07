# План конечной проверки источников

Статус: подготовлен, не запущен. В registry лимиты остаются равны нулю до
отдельного решения по правам и техническому допуску. Bulk history запрещён.

## Зафиксированные определения

| Ряд | Точное наблюдение | Календарь и доступность | Конечный probe после допуска |
| --- | --- | --- | --- |
| USD/RUB, EUR/RUB | CBR R01235/R01239, официальный курс RUB за единицу после Nominal | effective date ЦБ; знание не раньше receipt | 2 запроса: по одному на валюту, один день |
| Ключевая ставка | CBR DailyInfo `KeyRate`, `% p.a.`, только с 17.09.2013, без refinancing fallback | действует каждый календарный день; announcement отдельно; знание по receipt/подтверждённому publication | 1 запрос на одну дату изменения |
| Кривая | CBR zero-coupon 1/2/5/10Y, выбор по заголовкам | дата оценки кривой; publication не угадывается | 1 ответ за одну дату |
| CPI | Россия, все товары и услуги, месяц к тому же месяцу прошлого года, `index_percent - 100`; витрина 11521100300010200001 | reference — конец месяца; ожидаемое окно 6–10-й рабочий день не заменяет фактический receipt/publication | 2 запроса: metadata/selector и один месяц |
| IMOEX | MOEX ISS `SECID=IMOEX`, `TRADEDATE`, `CLOSE`; не IMOEX2/ETF/total return | main-session close 18:50 Europe/Moscow; далее фактический receipt | 1 ответ за одну торговую дату |
| VIX | Cboe `VIX_History.csv`, `DATE`, `CLOSE`; не future/ETF | US session date, America/New_York; historical DATE не считается publication timestamp | 1 ответ с последней строкой |

Предлагаемый максимум первой проверки: 8 HTTP-ответов. Retry не увеличивает
бюджет молча: повтор после timeout/429 считается отдельным запросом и должен
помещаться в утверждённый лимит. S&P 500, Brent и gold проверяются отдельным
решением, потому что они не нужны для текущих пяти компонент target.

## Порядок запуска

1. Для каждого ряда записать decision ID по display/model/export/API и лимит.
2. Зафиксировать URL, параметры, календарь, timezone и ожидаемый content type.
3. Получить только указанный короткий ответ; сохранить время, status, headers,
   SHA-256 и безопасный receipt. Raw payload не коммитить автоматически.
4. Прогнать parser без исправления ответа вручную. Ошибка schema завершает run.
5. Проверить путь: raw hash -> observation -> revision -> общий SQLite snapshot.
6. Перезапустить API и сверить тот же active snapshot, history и model coverage.
7. Только после review решать incremental schedule и отдельный backfill budget.

Worker использует `MarketStore` и `ARCSHIFT_DB_PATH`; второй production storage
или отдельная БД для ingest не создаются. Публикация snapshot и active pointer
остаются одной SQLite-транзакцией. При падении до publish старый snapshot активен,
а повторный run идемпотентно добавляет одну revision.

## Критерий завершения

Для каждого допущенного ряда есть один воспроизводимый receipt, нормализованная
запись с reference/effective/publication/received time, revision number и один
опубликованный content-hashed snapshot. Любой pending rights, неизвестный
publication time, закрытый рынок или broken schema остаётся явным статусом,
а не нулём и не «низким риском».
