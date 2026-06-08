# Crisis Prediction Service Dashboard

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/train_crisis_model.py
streamlit run app/dashboard.py
```

## Модель MVP-1.0

Первая модель — интерпретируемый baseline для демонстрации early-warning логики.
Она строит trailing stress index, размечает future stress event на горизонтах 7/30/90 дней,
обучает balanced logistic regression и сохраняет артефакты:

- `data/model_predictions.csv` — вероятности, режимы риска и ключевые драйверы;
- `data/model_metrics.json` — walk-forward метрики и параметры модели;
- `models/artifacts/*.joblib` — обученные sklearn pipelines.

Пересборка:

```bash
python scripts/train_crisis_model.py
```

## Исторический датасет

`scripts/build_final_dataset.py` по умолчанию собирает дневной датасет с `2003-01-01`.
Для ключевой ставки используется официальный ряд ЦБ РФ: после появления key rate берется
`Key rate`, до этого — `Refinancing Rate` из той же таблицы ЦБ.

Для исторических рядов в MVP-1.0 используются:

- Brent: официальный EIA Europe Brent Spot Price FOB (`RBRTE`) из XLS-выгрузки EIA;
- инфляция: агрегированный CPI YoY ряд Росстата через пакет НЦСЭД `rsdocs_1031000110063`,
  где `inflation = CPI YoY index - 100`;
- ОФЗ: официальная кривая бескупонной доходности государственных облигаций ЦБ РФ
  по 1/2/5/10 годам; локальные MOEX-файлы используются только для сверки на пересечении.

Подробное описание формирования датасета: `omx_wiki/dataset-formation.md`.

Полная пересборка данных и модели:

```bash
python scripts/build_final_dataset.py --start-date 2003-01-01
python scripts/train_crisis_model.py
```

Ограничения текущего покрытия:

- Brent начинается с `2003-01-02` в текущем MVP-датасете;
- инфляция покрывает весь период с `2003-01-01` после сдвига месячного CPI YoY на следующий месяц;
- ОФЗ-ряды начинаются с `2003-01-04` через источник ЦБ РФ;
- первые дни до старта отдельных рынков остаются пустыми, а не проксируются.
