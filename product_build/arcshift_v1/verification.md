# Проверка Публичного Пакета

Дата: 05.11.2026. Проверяется отобранный handoff, не готовность продукта.
Фактически выполнено: **35 тестов, OK**. Из них 8 проверяют публичный
пакет и 27 являются synthetic offline contract tests. Никакие provider
downloads, model fits или production tests не выполнялись.

Из корня этого пакета:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/check_bundle.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/tools/release python3 -m unittest -v test_v1_data_contract
```

Проверяются состав/хеши, obvious secret/private-path patterns, ссылки,
28 задач без циклов с покрытием всех этапов, текущие open gates и synthetic
маркировка. Offline contract tests проверяют synthetic invariants, не реальные
данные, license interpretation, train quality или production безопасность.

Автоматический scanner не является полной гарантией отсутствия чувствительной
информации. Дополнительно применён конечный allowlist исходных файлов,
просмотр содержания и обезличивание interview/research summary.

В продуктовой рабочей копии не переключается ветка и не коммитятся чужие
dirty файлы. Публикация выполняется отдельным Git-деревом от указанного base.
Старые данные/weights не перезаписываются; новые raw datasets не добавляются.
