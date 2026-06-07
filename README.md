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

Полная пересборка данных и модели:

```bash
python scripts/build_final_dataset.py --start-date 2003-01-01
python scripts/train_crisis_model.py
```

Ограничения текущего покрытия:

- Brent начинается с `2007-07-30`;
- ОФЗ-ряды в локальных файлах начинаются с `2014-01-06`;
- инфляция в локальном файле начинается с `2014-02-01`;
- для ОФЗ и инфляции ранние значения не проксируются.
