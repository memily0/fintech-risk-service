# Проверка Спецификации

Дата: 05.11.2026. Проверяется локальный пакет требований, не готовность V1.

Команда из корня ArcShift:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/tools/release python3 -m unittest -v test_v1_product_specification test_local_cycle_closeout_v1
```

Фактически выполнено: **21 тест, OK**. Из них 12 относятся к спецификации,
9 к ранее подготовленному local cycle closeout.

Проверены структура CSV, уникальность ID, ссылки evidence/gates,
двусторонние связи функций и сценариев, отсутствие циклов в backlog,
согласованность coverage/access/budget, локальные ссылки и сохранение
неутверждённых статусов. Closeout tests дополнительно сверили исходные
research/product hashes, включая существующие weights и dataset, и запрет
отменённого Git install. Совпадение hashes не является повторной оценкой модели.

Содержимое пакета:

- 20 Must функций, 1 Should, 3 отложенных направления.
- 40 сценариев приёмки, все not_run.
- 12 строк эксплуатационных целей, все not_measured.
- 12 пакетов реализации с предлагаемыми ролями, named owners не назначены.
- 12 решений с раздельными confirmed/proposed/pending статусами.
- Все 22 release gates остаются pending.

Не выполнялись: 40 продуктовых сценариев, нагрузочный прогон, измерение NFR,
новая валидация/обучение/inference replay, проверка лицензии каждого будущего
production feed, числовые загрузки, purchases, DNS, deployment и Git push.
Код приложения и старые артефакты не изменены. Существующие пользовательские
изменения в product worktree оставлены без откатов.
