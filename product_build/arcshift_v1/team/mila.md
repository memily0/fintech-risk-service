# Мила: Корректность Модели И Валидации

Задачи M01-M05; координация Q01-Q03 с независимым review своей работы.
Это не задача попробовать максимальное число моделей или улучшить старую AUC
любой ценой. Ведущий предложен; production/support роли отдельно не назначены.

## Прочитать

current_state.md, evidence/research_to_product.md, source findings,
candidate_contract.json, specification acceptance A17-A24/A30.
В корне репозитория: scripts/train_crisis_model.py и build_final_dataset.py.
Прежние model cards в legacy_reference читать вместе с warning banner.

## Последовательность

1. M01: зафиксировать свойства target, horizon/calendar, unknown/warm-up,
   maturity, transform availability, fitted/OOS/live и calibration semantics.
2. M02: на synthetic sequences показать boundary bugs и исправленные helpers.
   Label window с концом на cutoff или после него не зрелое training evidence.
   Неполные исходы не превращать в negative; dates уникальны и упорядочены.
3. M03: предложить конечный evaluation plan после source/task решений:
   baseline/comparator, matching origins, splits, preprocessing, calibration,
   threshold policy, multiplicity, warning/event metrics и run budget.
4. M04: новый fit только по явно утверждённому конечному плану и permitted
   inputs. Не перезаписывать existing outputs. Учитывать все результаты,
   не выбирать deployment candidate по уже просмотренному outer test.
5. M05: task-specific inference contract и artifact registry. Проверить exact
   schema, hash, cutoff, dependency compatibility, unavailable и rollback.

## Оценка

AUC/AP не заменяют calibration/Brier, false alarms, burden, event recall,
missed events и lead. Порог FAR из P1 не является готовой бизнес-ценой ошибки.
Если нет эмпирических данных для economic/decision impact, так и написать.
Balanced logistic regression не называть откалиброванной без проверки.
MFS/multi-task и сложные модели не включать без отдельного finite design.

JST annual checkpoints и P1 quarterly predictions не являются daily Russia
serving model. Не переносить их numerical scores/weights в production и этот
публичный пакет. Не выдавать source failure за отсутствие predictive signal.

## Что Вернуть

Helpers и regression tests, target/feature/split specification, finite protocol,
таблицу разрешённых/неразрешённых claims, оценочный код и limitations.
Если M04 разрешён: точные inputs/version receipts, все metrics и warning record,
model card, artifact admission/rejection с причинами. Binary model/data transfer
требует отдельной проверки публичных прав, не автоматически в PR.

Reviewer M-задач: Ярослав и Настя по time/source semantics. Приёмку чужих
модулей координирует Мила; её собственную model validation проверяет другой человек.

## Стартовое Сообщение Агенту

Ты работаешь над M01-M03 ArcShift V1. Прочитай AGENTS, current_state,
integration_contract и team/mila.md. Изучи существующий train script,
но сначала используй synthetic regression tests. Исправь/предложи temporal
invariants без новых fits и перезаписи весов. Верни tests, helpers и конечный
validation plan; не объявляй качество будущей модели подтверждённым.
