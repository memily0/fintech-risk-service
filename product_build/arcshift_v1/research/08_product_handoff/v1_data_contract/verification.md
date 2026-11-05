# Проверка Кандидата Контракта

Дата: 05.11.2026. Все числовые примеры новых normalizer tests синтетические,
snapshot помечен synthetic-contract-test-not-market-data. Значения не являются
данными рынка и не включены в product/research training datasets.

Использован уже установленный jsonschema 4.26.0. Новые зависимости не
устанавливались; production requirements и lock этим шагом не изменены.
Draft 2020-12 schema проверяется локально, внешних $ref у неё нет.

Команда из корня ArcShift:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/tools/release python3 -m unittest -q test_v1_data_contract test_v1_source_audit test_v1_product_specification test_local_cycle_closeout_v1
```

Фактически выполнено **60 тестов, OK**: 27 новых contract/normalization tests,
12 source-audit tests, 12 specification tests и 9 local-closeout tests.
Hash checks подтвердили сохранность ранее перечисленных product/research
inputs. Это не проверка predictive quality и не исполнение 40 сценариев
приёмки будущего приложения.

Новые tests проверяют:

- Schema, versions, exact units/resource IDs и canonical dimensions.
- Bool/NaN/Inf, missing=null, reversed/invalid periods и naive timestamps.
- Receipt boundary, неизвестное publication time, timezone и effective date.
- Неиспользование позднего US close в московское утро.
- CPI index -> inflation, запрет MoM/weekly/regional/row-position подмены.
- Genuine key rate без refinancing substitution и до-definition history.
- Curve header selection при перестановке колонок и отказ при неоднозначности.
- Запрет подставлять permissions в observation; весь candidate use остаётся blocked.
- Открытые source findings и незакрытый exact CPI binding не скрыты.

Не проверены реальные provider codes, payloads, HTML multirow extraction,
vintages/revisions, rate limits, calendar/freshness, сервер и публичный доступ.
Нормализаторы ожидают уже распознанные canonical dimensions/headers;
источниковые adapters в продукт не интегрированы. Receipt hash проверяется
по форме; проверка совпадения с реальными сохранёнными bytes будет частью ingest.

Документационные запросы: DailyInfo и curve страницы ЦБ открыты; основной
Росстат price/FAQ/print вернул timeout. Candidate CPI IDs уточнены по поисковому
индексу официальных страниц, не по числовому API. Браузерная проверка не является
server reachability или законченным source admission.

Новые fits, provider numeric probes, bulk downloads, outreach, покупки,
deployment и Git upload не выполнялись. Прежние product/research inputs
сверяются существующими hash tests, а не перезаписываются.
