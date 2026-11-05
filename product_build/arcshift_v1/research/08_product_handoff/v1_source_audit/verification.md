# Проверка Пакета Аудита

Дата: 05.11.2026. Проверяются локальные файлы и их согласованность.
Это не юридическая приёмка источников, не live feed и не новая model validation.

Инвентарь создан без импорта runtime приложения:

```sh
env PYTHONDONTWRITEBYTECODE=1 python3 research/tools/release/build_v1_source_audit_inventory.py
```

Фактически обработано 19 колонок в 8559 строках существующего CSV.
Источник дат и значений: локальный merged snapshot, включая старые fills
и transformations. Он не позволяет определить реальный возраст каждого release.
Хеши builder, trainer и dataset сохранены в local_input_manifest.csv.
Внешние web-документы полностью не архивировались и не хешировались.

Проверки:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/tools/release python3 -m unittest -v test_v1_source_audit test_v1_product_specification test_local_cycle_closeout_v1
```

Фактически выполнено: **33 теста, OK**. Из них 12 проверяют этот аудит,
12 спецификацию V1, 9 прежний local cycle closeout. Проверка хешей подтвердила
сохранность исходного кода, старого датасета и перечисленных в closeout
модельных артефактов. Это не replay прогнозов и не проверка predictive quality.

Проверки охватывают полноту относительно AST constants старого кода,
raw/derived dependencies, rights mapping, ссылки, локальный replay инвентаря,
хеши и сохранение незакрытых статусов. Успешный тест структуры не подтверждает
license interpretation, source completeness, publication chronology или SLA.
Открытия с timeout и evidence из поискового индекса помечены отдельно.

Не запускались numeric API probes, bulk source downloads, batch dataset build,
training, inference replay, live worker, покупки, DNS, deployment и Git upload.
Старые research/product inputs оставлены без изменений.
