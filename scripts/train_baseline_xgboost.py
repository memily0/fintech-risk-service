"""Train baseline XGBoost on data/processed/dataset_monthly.csv.

Time-based split (no random shuffle):
  train: 2003-01-01 .. 2018-12-01
  test:  2019-01-01 .. end

Outputs:
  model/baseline_xgboost.pkl
  model/baseline_metrics.md
"""
from __future__ import annotations

import pickle
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "dataset_monthly.csv"
MODEL_DIR = ROOT / "model"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

FEATURES = [
    "vix_mean", "vix_zscore", "vix_delta",
    "fed_rate", "fed_rate_delta", "fed_rate_delta3",
    "cbr_rate", "cbr_rate_delta", "cbr_rate_delta3",
    "cpi_russia",
    "usdrub_vol", "usdrub_zscore", "usdrub_accel",
    "imoex_return", "imoex_vol", "imoex_drawdown",
    "ofz_spread_filled",
]
TARGET = "label"
SPLIT_DATE = pd.Timestamp("2019-01-01")


# ---------------------------------------------------------------- load
df = pd.read_csv(DATA, parse_dates=["date"])
print(f"Loaded {DATA}  shape={df.shape}")

# drop rows without label
n_before = len(df)
df = df[df[TARGET].notna()].copy()
df[TARGET] = df[TARGET].astype(int)
print(f"Dropped {n_before - len(df)} rows with NaN label  →  {len(df)} rows remain")


# ---------------------------------------------------------------- split by date
train = df[df["date"] < SPLIT_DATE]
test  = df[df["date"] >= SPLIT_DATE]

X_train, y_train = train[FEATURES], train[TARGET]
X_test,  y_test  = test[FEATURES],  test[TARGET]

print(f"\nTrain: {len(train)} rows  ({train['date'].min().date()} .. {train['date'].max().date()})")
print(f"Test:  {len(test)} rows  ({test['date'].min().date()} .. {test['date'].max().date()})")

def dist(s: pd.Series) -> str:
    vc = s.value_counts().sort_index()
    return ", ".join(f"{int(k)}={int(v)} ({v/len(s)*100:.1f}%)" for k, v in vc.items())

print(f"  train class dist: {dist(y_train)}")
print(f"  test  class dist: {dist(y_test)}")


# ---------------------------------------------------------------- class weights
# scale_pos_weight is a binary param; for multiclass we pass per-sample weights
# derived from balanced class weights (inverse frequency).
classes = np.array(sorted(y_train.unique()))
cw = compute_class_weight(class_weight="balanced", classes=classes, y=y_train)
class_weight = dict(zip(classes, cw))
sample_weight = y_train.map(class_weight).values
print(f"\nBalanced class weights (used as sample_weight): {{ {', '.join(f'{int(k)}: {v:.3f}' for k,v in class_weight.items())} }}")


# ---------------------------------------------------------------- train
model = xgb.XGBClassifier(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    objective="multi:softprob",
    num_class=3,
    eval_metric="mlogloss",
    use_label_encoder=False,
    tree_method="hist",
    random_state=42,
)
model.fit(X_train, y_train, sample_weight=sample_weight, verbose=False)
print("\nModel trained.")


# ---------------------------------------------------------------- evaluate
y_pred = model.predict(X_test)

report_dict = classification_report(y_test, y_pred, labels=[0, 1, 2],
                                    target_names=["0 (норма)", "1 (стресс)", "2 (кризис)"],
                                    output_dict=True, zero_division=0)
report_txt = classification_report(y_test, y_pred, labels=[0, 1, 2],
                                   target_names=["0 (норма)", "1 (стресс)", "2 (кризис)"],
                                   zero_division=0)
cm = confusion_matrix(y_test, y_pred, labels=[0, 1, 2])

print("\nClassification report (test):")
print(report_txt)
print("Confusion matrix (rows=true, cols=pred; labels 0,1,2):")
print(cm)


# ---------------------------------------------------------------- feature importance
importance = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False)
print("\nFeature importance (gain-based, top 10):")
for k, v in importance.items():
    print(f"  {k:22s} {v:.4f}")


# ---------------------------------------------------------------- save model
pkl_path = MODEL_DIR / "baseline_xgboost.pkl"
with open(pkl_path, "wb") as fh:
    pickle.dump(model, fh)
print(f"\nSaved model → {pkl_path}")


# ---------------------------------------------------------------- save metrics.md
def cm_md(cm: np.ndarray) -> str:
    head = "| true \\ pred | 0 | 1 | 2 |\n|---|---:|---:|---:|"
    rows = [f"| {i} | {cm[i,0]} | {cm[i,1]} | {cm[i,2]} |" for i in range(3)]
    return head + "\n" + "\n".join(rows)

def imp_md(s: pd.Series) -> str:
    head = "| feature | importance |\n|---|---:|"
    rows = [f"| {k} | {v:.4f} |" for k, v in s.items()]
    return head + "\n" + "\n".join(rows)

def report_md(d: dict) -> str:
    head = "| class | precision | recall | f1 | support |\n|---|---:|---:|---:|---:|"
    rows = []
    for k in ["0 (норма)", "1 (стресс)", "2 (кризис)", "macro avg", "weighted avg"]:
        if k in d:
            r = d[k]
            rows.append(f"| {k} | {r['precision']:.3f} | {r['recall']:.3f} | {r['f1-score']:.3f} | {int(r['support'])} |")
    acc = d.get("accuracy", float("nan"))
    rows.append(f"| **accuracy** | | | **{acc:.3f}** | {int(d.get('macro avg', {}).get('support', 0))} |")
    return head + "\n" + "\n".join(rows)

md = f"""# Baseline XGBoost — результаты

Сгенерировано: {date.today().isoformat()}  ·  скрипт: `scripts/train_baseline_xgboost.py`

## Конфигурация

- **Признаки** ({len(FEATURES)}): {", ".join(f"`{c}`" for c in FEATURES)}
- **Целевая переменная:** `label` (0/1/2)
- **Split по времени:**
  - train: 2003-01-01 .. 2018-12-01 ({len(train)} строк, {train['date'].min().date()}..{train['date'].max().date()})
  - test:  2019-01-01 .. {test['date'].max().date()} ({len(test)} строк)

### Распределение классов
- train: {dist(y_train)}
- test:  {dist(y_test)}

### Балансировка
`scale_pos_weight` — биномиальный параметр, для multiclass использованы **sample_weight** из `sklearn.utils.class_weight.compute_class_weight(class_weight='balanced')`:

| class | weight |
|---|---:|
{chr(10).join(f"| {int(k)} | {v:.3f} |" for k, v in class_weight.items())}

### Параметры модели
- n_estimators = 200
- max_depth = 4
- learning_rate = 0.05
- objective = `multi:softprob`, num_class = 3
- eval_metric = `mlogloss`
- tree_method = `hist`, random_state = 42

## Classification report (test)

{report_md(report_dict)}

## Confusion matrix (test)

{cm_md(cm)}

## Feature importance (gain, top 10)

{imp_md(importance)}

## Замечания

- В `test` всего {len(test)} строк, из них минорные классы — крайне малая выборка → метрики имеют большой доверительный интервал.
- Период обучения (2003–2018) включает 3 из 4 размеченных кризисов (GFC 2008-09, Крым 2014-12, исключая COVID 2020 и 2022). Тест видит COVID и санкционный шок 2022 — это честная проверка обобщения.
- XGBoost нативно обрабатывает NaN в признаках — `dropna` не делался.
"""

md_path = MODEL_DIR / "baseline_metrics.md"
md_path.write_text(md, encoding="utf-8")
print(f"Saved metrics → {md_path}")
