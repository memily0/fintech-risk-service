# I05.3: Отчётная Часть Никиты Через Общий Backend

Дата: 2026-11-05. Ветка: `v1/integration-yaroslav`.
Источник подхода и ReportLab/LongTable renderer:
`v1/ui-nikita`, `7f0a403a235385ff802c1780ad59f7fdeb88eab3`,
`app/workspace_reports.py`. Код адаптирован к текущим typed schemas и API,
не является побайтовой копией или полным переносом Streamlit workbench.

## Сделано

- Общая SQLite migration 005: owner-scoped immutable saved reports.
- Capture фиксирует review revision/events и ожидаемый market snapshot.
- Отдельный раздел «Отчёты», сохранение из разбора и PDF/CSV/JSON скачивание.
- Каждое чтение/скачивание проверяет текущую серверную сессию и owner.
- Payload hash, metadata consistency, revision/snapshot conflicts и bounded lists.
- Отдельный persisted rate limit export; максимум 2000 наблюдений/ревизий.
- PDF с кириллицей, escaped notes, nullable signal и unknown publication.
- Пустой набор наблюдений поддержан; CSV сохраняет числовые отрицательные
  значения и нейтрализует formula-like текстовые значения.
- Шрифт Liberation Sans с SIL OFL 1.1 включён без изменений и лицензия сохранена;
  proprietary/system Arial и внешние fonts не требуются.
- Logout очищает private report state, включая вторую same-origin вкладку.

Никакой второй auth/private DB или demo actor из Streamlit не подключён.
Старые draft exports разбора сохранены для совместимости и не объявлены
immutable reports. Выгруженную пользователем копию logout не удаляет.

## Проверено

168 core tests (19 новых), 18 temporal checks и 60 прежних research checks.
Проверены чужие ID, guest/logout, CSRF, stale revision/snapshot, неизменность
после правки, выбранные/пустые series, повреждённый payload, rate limits,
renderer failure и параллельный PDF. Кириллица извлечена из PDF; полный
русский алфавит присутствует в embedded font. Test report занимает 2 страницы.
Browser E2E на 1440/390/320 px: сохранение, три downloads, чужой аккаунт,
редактирование исходной заметки и очистка private state; 0 errors/external
requests и нет document overflow. Wheel содержит font/license/migration и
загружает кириллицу вне checkout без private datasets/weights/runtime DB.
Сохраняется известный Starlette/HTTPX TestClient warning; baseline frozen
handoff manifest mismatch не исправлялся этим шагом.

## Остаётся

Это отчётная часть UI integration, не все U01-U04: расширенный overview/chart,
отдельная warning queue/dedup, indicator watchlist вместо fixture-state list
и methodology screen ещё требуют согласования/подключения. Real sources,
accepted model, real email/recovery, retention/deletion, public abuse controls,
deployment/security/load/restore и все release gates остаются открыты.
Не было provider downloads, model fits, внешней почты или production deploy.
