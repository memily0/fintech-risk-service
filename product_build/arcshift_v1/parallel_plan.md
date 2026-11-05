# Параллельный План До ArcShift V1

Основа: research/08_product_handoff/arcshift_v1_end_to_end_plan.md.
Ниже те же инженерные этапы 0-11, разделённые по модулям и точкам интеграции.
Не требуется сначала закончить ВСЮ науку, чтобы начать интерфейс и аккаунты.
Но fixtures не превращают незавершённые данные/модель в готовый продукт.

## 1. Четыре Направления

| Линия | Предлагаемый ведущий | Зона владения | Можно начать сейчас |
| --- | --- | --- | --- |
| I: интеграция/backend/ops | Ярослав | Общие контракты, storage/API, аккаунты, release integration | Контракты, startup skeleton и auth/storage на fixtures |
| D: данные | Настя | Source contracts, adapters, scheduler, quality/freshness | Metadata/rights, parsers и failure tests на synthetic responses |
| M: модель/валидация | Мила | Labels, temporal splits, model evaluation/registry | Invariants, maturity/warm-up/calendar tests, finite evaluation design |
| U: интерфейс | Никита | Screens, workflow, UI states, report presentation | UX на fixtures, loading/empty/stale/unsupported, связь с contract |

Ops и QA не исчезают: I ведёт эксплуатационную сборку, M координирует
приёмочные evidence, но автор функции не является её единственным reviewer.
Нагрузка и назначения требуют подтверждения участниками. Если backend
перегружает интегратора, отдельные I-задачи передаются явно, не дублируются.

## 2. Разбор Всех Этапов

| Этап общего плана | Что параллелится | Что является зависимостью | Выход |
| --- | --- | --- | --- |
| 0 Scope | I фиксирует contracts; D уточняет series; M формализует задачу; U уточняет пользовательский путь | Перед реальными fits и выпуском нужны утверждённые границы | Версионный scope и решения, не только список пожеланий |
| 1 Знания/данные | D source work; M использует обезличенные методические выводы; U evidence UX | Реальные источники требуют точного binding и права по purpose | Series/rights/freshness matrix, unresolved gaps |
| 2 Основа | I startup/config/tests/contracts; D/M/U тестируют одинаковые fixtures | Один владелец shared schema и зависимостей | Повторяемый локальный запуск без download/fit |
| 3 Ingest | D adapters/worker; I storage/jobs; U quality states; M availability checks | Production fetch после source gates и конечного request plan | New observations, revisions, atomic snapshots и отказные tests |
| 4 Модель | M synthetic correctness и протокол уже сейчас; D готовит admitted inputs; I artifact contract; U unavailable/model-status | Fit требует approved task/horizons/inputs/splits/budget; serving требует accepted artifact | Полный validation record и решение по candidate |
| 5 Сервис | I auth/API/reviews/watchlists/reports; D пишет через ingestion boundary; U вызывает API | Реальные сигналы позже fixtures, по той же схеме | Авторизованный versioned API и личное состояние |
| 6 UI | U основной workflow; I endpoints; M проверяет трактовку score/drivers; D freshness | Реальные данные/score подключаются только после допуска | Обзор -> warning -> разбор -> review -> отчёт |
| 7 Доступ/ops | I auth/secrets/monitoring/backups; D source heartbeat; M независимые negative tests; U access UX | Policies/owner/retention должны быть выбраны до public launch | Проверенные безопасность, изоляция и runbooks |
| 8 Staging | I deployment; D provider connectivity; M acceptance; U browser tests | Интегрированный RC, budget/provider/secrets и разрешение deploy | Отдельное окружение без production данных и двойного poller |
| 9 Приёмка | Все линии закрывают свои findings; M собирает evidence, I собирает RC | Нельзя закрыть только скриншотами или unit tests | Одна версия проходит E2E/load/failure/restore/rollback |
| 10 Домен/prod | I выполняет отдельное согласованное размещение; остальные smoke/monitoring | Release gates, домен/регион/доступы и явное разрешение запуска | HTTPS сайт, один scheduler, защищённые служебные пути |
| 11 Сопровождение | D freshness, M зрелые outcomes/calibration, U ошибки UX, I incidents/backups | Назначенные owners, расписание и budget | Поддержка, renewal, restore drills и versioned changes |

## 3. Волны Работы

### W0: Общая Граница

I01 + D01 + M01 + U01 идут одновременно: согласовать contract candidate,
точку старта, статус данных и одинаковые сценарии. I02 создаёт тестовую
кодовую основу и fixture interface. В репозитории уже есть candidate
observation schema; его надо оценить, а не молча заменить другим.

**Контрольная точка K0:** общий task/data/signal/user-state contract имеет
версию и review всех четырёх направлений. Placeholder source IDs и часовые
пояса не объявлены подтверждёнными. Возможна разработка на fixtures.

### W1: Независимая Реализация

- D02/D03: parsers и ingest/DQ на fixtures; D04 отделён как реальный probe.
- M02/M03: исправленная target/split логика на synthetic data и evaluation plan.
- I03/I04: аккаунты, isolation, API и личное состояние с mock signal store.
- U02/U03: экраны и полный review workflow через fake API/fixtures.
- O01/Q01: эксплуатационные skeleton и перенос acceptance cases в tests.

**K1:** offline demo запускается без сети и обучения; synthetic происхождение
видно в UI/exports; контракты и negative tests согласованы. Это не production V1.

### W2: Реальные Данные И Оценка

D04/D05 зависят от source admission, request budget и выбора источников.
M04 зависит от admitted snapshots и утверждённого finite run plan.
I/U в это время заканчивают auth, reports, loading/error/stale states,
мониторинг и интеграционные tests, не ждут окончания fit.

**K2:** provenance и реальные обновления подтверждены, конкретный model
candidate либо принят, либо отклонён с причинами. Не удаляем компоненту
таргета ради отсутствующего источника и не выдаём legacy weights за новые.

### W3: Сборка

I05 объединяет код в RC; D06 проверяет фактическое data flow,
M05 оценивает совместимость артефакта, U04 подключает настоящие ответы API.
O02/Q02 проверяют безопасность, ошибки, нагрузку и восстановление.

**K3:** один RC проходит полный workflow. Источники, значения, версии и
права совпадают в UI/PDF/CSV/API, private state не утекает между users.

### W4: Сервер И Приёмка

O03 -> Q03 -> R01 -> R02: staging, независимая приёмка, затем отдельно
согласованный production deploy и сопровождение. Доменные DNS не являются
заменой staging/restore/rollback. До разрешения допустимы scripts/runbooks
и локальные проверки, но не реальные покупки или публичное развёртывание.

## 4. Критический Путь

```text
scope + общий контракт
  -> exact sources + rights + timestamps
  -> versioned admitted snapshot
  -> approved target/evaluation -> accepted model
  -> integrated authenticated workflow
  -> staging + full acceptance + restore/rollback
  -> production authorization -> domain release
```

Независимые линии auth/UI/test infrastructure сокращают ожидание в середине,
но не устраняют права на данные, корректность задачи и конечную приёмку.

## 5. Владение Файлами И Ветки

База: research-to-product/v1-parallel-2026-11-05. Предлагаемые рабочие ветки:
v1/data-nastya, v1/model-mila, v1/ui-nikita, v1/integration-yaroslav.
Эти ветки не создаются автоматически этим пакетом.

После K0 рекомендуемые module boundaries в текущем продукте:
data adapters/storage/jobs, model labels/validation/inference,
application auth/API/user-state, frontend/workflow, tests и ops.
Конкретные новые directory names фиксирует I02 после чтения кода.
Не создаём сразу четыре независимых проекта/БД или четыре scheduler.

Shared contracts/migrations/dependency lock меняет назначенный владелец
после короткого review. D и M не редактируют одновременно одну legacy
training функцию в одной ветке: выделить boundary или согласовать порядок.
Не складывать новые веса в существующие имена legacy artifacts.

## 6. Как Принимать Результаты

Каждый PR/возврат содержит task IDs, base SHA, точные команды tests,
actual output, изменённые contracts, limitations и remaining blockers.
Один PDF, устное «готово» или красивый screenshot не заменяют код/tests.

Проверка парой: D -> I/M; M -> I/D; U -> I/M; I/security -> M и ещё один
участник. Автор fixes найденные issues, reviewer проверяет новую версию.
Слияние координирует интегратор; автоматического merge main нет.

Прогнозные улучшения принимаются только на matching task/population/splits.
UI review не является научной валидацией, а scientific review не является
одобрением production модели или лицензии. Не закрывать gates по факту
появления Markdown. Числовые SLA, бюджет и deployment owner ещё согласуются.
