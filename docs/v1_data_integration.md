# I05.1: Data Lane -> API -> History

Дата: 2026-11-05. Ветка: `v1/integration-yaroslav`.
Предыдущий backend/auth/UI checkpoint: `9875c9b`.
Источник неизменённых data-модулей: Настя, `v1/data-nastya`,
`8bdb1de597eb5d567a8a19c84435ad9294a206cc`.

## Объединено

Скопированы только `src/arcshift_data`, candidate registry, data tests и return
документ. README из ветки Насти не заменяет существующие локальные правки.
Её исходные коммиты доступны в своей ветке; здесь интеграционный commit,
а не переписывание авторства или всей истории ветки.

Её FX/curve/CPI parsers и JsonObservationStore используются для воспроизводимого
synthetic примера. Затем SQLite snapshot с content hash публикуется атомарно.
HTTP обслуживает только опубликованный снимок; сетевого fetch/fit в нём нет.
Registry из fixtures побайтово сверяется с оригинальным config в тестах.

Работают каталог семи рядов и история 11 актуальных наблюдений / 12 ревизий:
USD/RUB, EUR/RUB, четыре точки кривой и CPI YoY. Все числа выдуманы, все коды
измерений CPI синтетические, publication time остаётся null. Это не свежие
котировки, не проверенный официальный CPI binding и не допуск данных в модель.

Добавлены market contract `v1-local-market.1`, миграция 004, защищённые от
перепутывания series/resource/units проверки и отказ при повреждении snapshot.
Seed не откатывает новый active snapshot при рестарте. История в браузере
имеет фильтр дат, переключение ревизий и отдельное время получения.

Попутно выполнено требование общего contract: closed/dismissed теперь требуют
непустую заметку. Старые fixture/auth/workspace API versions не переименованы.

## Проверки

- 137 tests: 98 прежних, 20 исходных data-lane и 19 новых integration/regression.
- 60 прежних локальных research/contract checks прошли без изменения ML файлов.
- HTTP: 8 маршрутов, два запуска, оба snapshot и migration ledger сохранены.
- Auth HTTP: сессия сохраняется при restart и отзывается после logout.
- Browser E2E: история/ревизии/фильтр дат и прежний полный личный workflow;
  1440/390/320 px, нет document overflow, 0 browser errors/external requests.
- Wheel собран и запущен вне checkout: API отдаёт 7 synthetic series;
  в wheel нет private datasets, runtime DB или model artifacts.
- pip check и git diff --check прошли. Starlette/HTTPX warning остаётся известным.

Запуск: [README](../arcshift_v1/README.md). Установка editable требует второго
шага после requirements lock. Он не меняет legacy `.venv`/requirements.txt.
У старого frozen handoff checker остаётся известное базовое расхождение SHA
для `evidence/evidence_to_product.csv`; evidence и frozen manifest здесь не
перезаписывались. Это не полная release acceptance.

## Следующая Интеграция

Подключить M02/M03 Милы и общий signal/inference contract, затем расширенные
экраны/отчёты Никиты через общий backend вместо его демо-аккаунтов/SQLite.
Его workbench и модельный trainer не объявлены объединёнными этим шагом.
Real source probes, worker, approved target/horizons, evaluation, real email,
recovery, production DB, security/load/restore и HTTPS остаются открыты.
Ни реальные данные, ни JST, ни обучение, ни внешние письма не использовались.
