# Ярослав: Контракты, Backend И Общая Сборка

Задачи I01-I05, O01-O03, R01-R02. Не брать всю разработку молча на себя:
после подтверждения команды делегировать отдельные I/O пакеты явно.

## Последовательность

1. I01/K0: собрать короткий review contract от D/M/U. Зафиксировать объект
   прогноза, vocabulary states, units/IDs/time, личные versus общие данные,
   protocol changes и ownership shared schema. Открытые решения не прятать.
2. I02: повторяемый startup, settings и зависимости, общие interfaces,
   schema/migrations и fixture mode. Сначала прочитать существующий продукт.
3. I03: публичные аккаунты, verification/recovery/session, authorization,
   abuse/rate limits и безопасные private reports. Privacy/retention/mail
   provider до public launch, не писать реальные credentials в Git.
4. I04: observation/signal history store, warnings/reviews/watchlists,
   read API, bounded report jobs и immutable snapshot exports на fixtures.
5. O01/O02: monitoring, secrets, backup/restore, migration/rollback runbooks,
   local failure/load tests. Не ждать окончания красивого UI для ops.
6. I05/K3: объединить D/M/U результаты в один release candidate. Проверить
   actual versions, source rights, dependency compatibility и negative cases.
7. O03/Q03: отдельно согласованный staging, independent acceptance,
   реальный off-server restore и rollback. Single VPS не называть HA.
8. R01/R02: после explicit approval production/domain, smoke checks,
   incident owners, renewal, access review и maintenance schedule.

## Контроль Данных И Исследований

Не переводить JST/model research-only в product. Старые weights и текущая
daily proxy модель не прошли новую приёмку только потому, что загружены в Git.
До M04 заморозить exact task, sources, horizons, splits и finite run plan.
Source access, display, model use, derived outputs и export оцениваются отдельно.

## Review Команды

Принимать по return_template: code/tests/commands/versions/limits, не одному PDF.
D работу смотреть вместе с Милой по availability; M работу с Настей по sources;
U с Милой по трактовке warnings. Security/ops Ярослава проверяет другой
участник, не только автор. Не объединять несовместимые contract versions.

## Стартовое Сообщение Агенту

Ты работаешь над I01-I04 и локальным O01 ArcShift V1. Прочитай AGENTS,
parallel_plan, integration_contract, current_state и team/yaroslav.md.
Сохрани existing code, user changes и frozen outputs. Согласуй K0 interfaces,
реализуй воспроизводимую основу, auth и личное состояние на fixtures.
Не скачивай всю историю, не обучай и не развёртывай production автоматически.
Верни tests, migrations/contracts, operations gaps и интеграционный план.
