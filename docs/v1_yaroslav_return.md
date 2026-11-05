# Возврат Работы Ярослава: I02-I04.1

Дата: 2026-11-05. Ветка: `v1/integration-yaroslav`.
База: `4ae077836d286b5b3bc166609dc86ff7ca601be7`.
Пакет содержит только локальную synthetic-реализацию, не публичный релиз V1.

## Реализовано

- FastAPI и отдельный environment lock, loopback-only запуск без download/fit.
- Версионные SQLite-миграции, ledger/checksums и immutable fixture snapshots.
- `.test` регистрация, Argon2id, локальное подтверждение, сессии и logout.
- Same-Origin/CSRF проверки, rate limits, owner-scoped watchlists/reviews.
- Revision conflicts, фиксированные scenario/snapshot и status-event history.
- Browser workbench, JSON/CSV и печатный отчёт с кириллицей.
- Очистка личного состояния при logout, включая вторую same-origin вкладку.

Инструкции: [запуск и API](../arcshift_v1/README.md),
[тестовые аккаунты](../arcshift_v1/LOCAL_AUTH.md).
Текущие версии кандидатов: `v1-fixture.1`, `v1-local-auth.1`,
`v1-local-workspace.1`. Это не согласование общего live signal contract.

## Проверки На Этом Checkpoint

```sh
.venv-v1/bin/python -m unittest discover -s tests -q
.venv-v1/bin/python tools/smoke_v1_backend.py
.venv-v1/bin/python tools/smoke_v1_auth.py
.venv-v1/bin/python -m pip check
```

98 тестов приложения прошли. HTTP checks проверили два запуска на временной
БД, неизменность snapshot, сохранение сессии и её отзыв. Browser check
`node tools/smoke_v1_workbench.cjs` с Playwright прошёл на 1440/390/320 px:
регистрация, local verification, вход, наблюдение, разбор, reload, JSON/CSV,
печать, чужие UUID, HTML-like note и logout во второй вкладке. Ноль внешних
запросов и browser errors. Все тестовые серверы/БД очищены. Зависимости:
`pip check` OK; известное Starlette/HTTPX TestClient warning не скрыто.

Для установленного Chrome: `ARCSHIFT_PLAYWRIGHT_CHANNEL=chrome`.
Отдельные screenshots/test DB/tokens в этот публичный пакет не входят.
Новая локальная preview-сессия не является production deployment.

## Открыто Перед Интеграцией

- D: real sources/rights, exact CPI binding, worker и observation storage boundary.
- M: approved target/calendar/horizons, temporal fixes, evaluation и artifact admission.
- U: один общий API, реальные actor/session вместо demo actor и единые report semantics.
- I: resend/recovery, real mail, public auth policy, production DB и operations.
- Полная приёмка, нагрузка, security review, backup/restore, rollback и HTTPS.

На этом checkpoint closed/dismissed ещё не требуют непустую заметку в API;
перед общей интеграцией это надо согласовать с командным contract и UI.
History export и source-backed warnings пока не реализованы этим API.
Изменение отбрасываемого target/источника не является допустимым способом
снять integration blocker. JST остаётся research-only и здесь не используется.

Старые ML/Streamlit файлы не заменены; модели не обучались. Секреты, почтовые
токены, личные runtime DB, исходные интервью и private research не включены.
Переключение на production/public bind запрещено текущими settings.
