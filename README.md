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
