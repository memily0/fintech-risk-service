# Crisis Prediction Service Dashboard

Этот репозиторий содержит локально запускаемый MVP-дашборд для исследования макроэкономических и рыночных индикаторов, связанных с кризисными периодами.

## Что внутри

- `app/dashboard.py` - Streamlit-дашборд
- `data/processed/` - подготовленные CSV-файлы для дашборда
- `reports/research_summary.md` - краткое резюме исследования

## Быстрый старт

Требования:

- Python 3.11+ рекомендуется

Установка и запуск:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/dashboard.py
```

После запуска Streamlit откроет локальный адрес в терминале, обычно `http://localhost:8501`.

## Данные

Для запуска дашборда уже включены готовые файлы:

- `data/processed/macro_daily_merged.csv`
- `data/processed/macro_features_with_lags.csv`

Поэтому команде не нужно сначала пересобирать датасет.

## Основные зависимости

- `streamlit`
- `pandas`
- `plotly`
- `numpy`
