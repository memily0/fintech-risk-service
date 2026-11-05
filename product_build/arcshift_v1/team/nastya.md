# Настя: Источники И Автоматическое Получение Данных

Задачи: D01-D06. Ведущий предложен; подтвердить доступность и границы с командой.
Код развивается в текущем продукте, не в новом независимом research pipeline.

## Прочитать

current_state.md, integration_contract.md, research/08_product_handoff/
v1_source_audit/{README.md,series_catalog.csv,rights_matrix.csv,findings.csv},
v1_data_contract/{README.md,candidate_contract.json,rights_questions.md}.
Затем scripts/build_final_dataset.py в корне репозитория и contract tests.

## Последовательность

1. D01: завершить source binding. Россия: official FX, genuine key rate,
   zero-coupon curve и exact national all-items CPI YoY. Не выбирать CPI по
   порядку строк. Global факторы не подменять другими инструментами.
2. D02: adapters как чистые парсеры synthetic raw responses. Для FX units/
   nominal, CPI dimensions, curve tenor headers, dates и broken schema есть tests.
3. D03: ingestion boundary, revision history, atomic publish, one scheduler,
   timeout/429/retry и fresh/stale/calendar states на fixtures.
4. D04: только после отдельного source/probe решения выполнить конечное
   число реальных requests. Не запускать прежний full-history builder.
5. D05: обновления и snapshots для admitted sources, отдельный backfill,
   availability/freshness и parent lineage у производных.
6. D06: совместный прогон с backend/UI/model. Observation date, publication,
   receipt, signal origin и refresh time не смешиваются.

## Что Вернуть

Source registry с exact IDs/definitions/units/calendar, права по каждому purpose,
request budget; adapters + tests; schema/version decisions; receipts и hashes
для разрешённых probes; DQ/freshness cases; instructions и unresolved list.
Первичные ответы/контракты с личными данными или ограничениями не публиковать
в этом GitHub, передавать отдельным разрешённым способом. В PR достаточно
ссылки на внутреннее decision ID и безопасного summary.

## Граница С Другими

Согласовать storage/write contract с Ярославом, feature availability с Милой,
UI freshness vocabulary с Никитой. Не менять target и train loop ради отсутствия
источника. Ни публичный endpoint, ни derived feature не являются license grant.
Reviewer: Ярослав, модельную availability дополнительно смотрит Мила.

## Стартовое Сообщение Агенту

Ты работаешь над D01-D03 ArcShift V1. Прочитай README, AGENTS, parallel_plan
и team/nastya.md в product_build/arcshift_v1. Проверь текущий checkout и
candidate contracts. Начни с exact binding gaps и synthetic parser tests.
Не скачивай bulk историю, не отправляй письма, не обучай модели и не добавляй
restricted данные. Верни код, tests, source/rights decisions и открытые вопросы.
