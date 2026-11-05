# Никита: Интерфейс И Рабочий Процесс

Задачи U01-U04. Цель: полноценное рабочее место, не landing и не один график.
Ведущий предложен; подтвердить загрузку и совместную границу с backend.

## Прочитать

README, current_state, integration_contract, specification/README.md,
feature_catalog.csv, acceptance_scenarios.csv и fixtures/ui_scenarios.json.
Текущий UI: app/dashboard.py в корне репозитория. Не менять framework
ради изменения стека; сначала оценить требования вместе с интегратором.

## Последовательность

1. U01: screen map обзора России, series history, signal/warning,
   investigation, personal review, watchlist, report, account и methodology.
2. U02: реализовать основной UI через общий fake API/client boundary.
   Тестовые числа явно synthetic; время данных отдельно от времени refresh.
   Разные loading/empty/error/stale/unsupported/missing states.
3. U03: личные заметки, статус проверки, фильтры, watchlists и PDF presentation
   с backend I04. Не хранить реальные private notes только в глобальном UI cache.
4. U04: настоящие API responses подключать после допуска inputs/модели;
   данные/версии/права в UI и export совпадают. Иначе честный unavailable.

## Важные UX Правила

- Главный экран рабочий. Россия основная; global factors не означают
  поддержку прогнозов кризисов всех стран. Отдельного Казахстана нет.
- Не показывать fitted history как OOS, старую оценку как свежую, unknown
  как низкий риск. Не выдумывать confidence или causal meaning драйверов.
- Регистрация публичная, не invitation-only. Team/SSO/billing отложены.
- Открытие экрана не запускает fit или provider download.
- Предупреждения не дублируются на refresh; review одного пользователя
  не закрывает warning у другого. Приватные exports не имеют публичных URLs.
- Проверить 375/768/1440 px, zoom текста 200%, клавиатуру, графики, пустые
  таблицы, длинные названия, date/time и отсутствие перекрытий.
- Записать Playwright screenshots/tests для actual UI, а не объявлять
  дизайн проверенным по Markdown или synthetic JSON.

## Что Вернуть

Рабочий frontend, API client boundary, screenshots и e2e tests, описанные
states, report examples с synthetic маркировкой, accessibility/responsive
findings и ограничения. Согласовать auth routes/report API с Ярославом,
трактовку модели с Милой, freshness semantics с Настей.
Reviewer: Ярослав и Мила, пользовательский feedback отдельно.

## Стартовое Сообщение Агенту

Ты работаешь над U01-U03 ArcShift V1. Прочитай AGENTS, current_state,
integration_contract и team/nikita.md. Используй synthetic fixtures и общий
API contract. Собери полный analyst workflow с error/freshness states,
не меняя target/метрики/права ради интерфейса. Верни код, browser tests,
screenshots, точный запуск и remaining blockers. Production deploy не делай.
