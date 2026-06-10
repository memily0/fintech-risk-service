"""IsolationForest as crisis-anomaly detector.

Train: только зелёные (label=0) месяцы в 2003-01..2018-12
Test:  всё с 2019-01 далее, оценка как бинарной задачи (label > 0 = тревога).

NaN: IsolationForest не принимает NaN, используем median-imputer (fit на train).

Outputs:
  model/isolation_forest.pkl  — {model, imputer, features, threshold_decision}
  model/comparison_table.md   — сравнение трёх моделей
"""
from __future__ import annotations

import pickle
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "dataset_monthly.csv"
MODEL_DIR = ROOT / "model"

FEATURES = [
    "vix_mean", "vix_zscore", "vix_delta",
    "fed_rate", "fed_rate_delta", "fed_rate_delta3",
    "cbr_rate", "cbr_rate_delta", "cbr_rate_delta3",
    "cpi_russia",
    "usdrub_vol", "usdrub_zscore", "usdrub_accel",
    "imoex_return", "imoex_vol", "imoex_drawdown",
    "ofz_spread_filled",
]
SPLIT_DATE = pd.Timestamp("2019-01-01")


df = pd.read_csv(DATA, parse_dates=["date"])
df = df[df["label"].notna()].copy()
df["label"] = df["label"].astype(int)
df["label_binary"] = (df["label"] > 0).astype(int)

train_all = df[df["date"] < SPLIT_DATE]
test      = df[df["date"] >= SPLIT_DATE]
train_green = train_all[train_all["label"] == 0]

print(f"Train (зелёные only): {len(train_green)} rows  ({train_green['date'].min().date()} .. {train_green['date'].max().date()})")
print(f"Test:                  {len(test)} rows  ({test['date'].min().date()} .. {test['date'].max().date()})")
print(f"  test class dist (binary): 0={(test['label_binary']==0).sum()}, 1={(test['label_binary']==1).sum()}")


# ---------------------------------------------------------------- impute + train
imputer = SimpleImputer(strategy="median")
X_train_g = imputer.fit_transform(train_green[FEATURES])
X_test    = imputer.transform(test[FEATURES])

iso = IsolationForest(
    n_estimators=200,
    contamination=0.1,
    random_state=42,
    n_jobs=-1,
)
iso.fit(X_train_g)
print("IsolationForest trained.")


# ---------------------------------------------------------------- score
# decision_function: высокое значение → норма; низкое → аномалия
# anomaly_score = -decision_function  → высокое → аномалия (привычнее)
dec = iso.decision_function(X_test)
anomaly_score = -dec
pred_raw = iso.predict(X_test)   # 1 = normal, -1 = anomaly
pred_alarm = (pred_raw == -1).astype(int)

y_true = test["label_binary"].values


# ---------------------------------------------------------------- report
print("\n=== IsolationForest (test, alarm = anomaly) ===")
print(classification_report(y_true, pred_alarm, labels=[0, 1],
                            target_names=["0 (норма)", "1 (аномалия)"],
                            zero_division=0))
cm = confusion_matrix(y_true, pred_alarm, labels=[0, 1])
print("Confusion matrix:"); print(cm)


# ---------------------------------------------------------------- anomaly scores for red months
red_test = test[test["label"] == 2].copy().reset_index(drop=True)
red_test_scores = -iso.decision_function(imputer.transform(red_test[FEATURES]))
red_test_pred   = (iso.predict(imputer.transform(red_test[FEATURES])) == -1).astype(int)

print("\n=== Anomaly score для красных месяцев в тесте ===")
print("(higher = more anomalous; pred=1 значит модель пометила как аномалию)")
out = pd.DataFrame({
    "date": red_test["date"].dt.strftime("%Y-%m"),
    "anomaly_score": red_test_scores.round(4),
    "pred_anomaly": red_test_pred,
})
print(out.to_string(index=False))


# ---------------------------------------------------------------- comparison table
def metrics_of(y_true, y_pred):
    rep = classification_report(y_true, y_pred, labels=[0, 1],
                                target_names=["0", "1"], output_dict=True, zero_division=0)
    return {
        "p0": rep["0"]["precision"], "r0": rep["0"]["recall"], "f0": rep["0"]["f1-score"],
        "p1": rep["1"]["precision"], "r1": rep["1"]["recall"], "f1": rep["1"]["f1-score"],
        "acc": rep["accuracy"],
        "macro_f1": rep["macro avg"]["f1-score"],
    }

# multiclass model — load and project
with open(MODEL_DIR / "baseline_xgboost.pkl", "rb") as fh:
    mc_model = pickle.load(fh)
X_test_raw = test[FEATURES]  # XGBoost handles NaN natively
mc_pred = mc_model.predict(X_test_raw)
mc_pred_bin = (mc_pred > 0).astype(int)
m_mc = metrics_of(y_true, mc_pred_bin)

# binary model
with open(MODEL_DIR / "binary_xgboost.pkl", "rb") as fh:
    bin_model = pickle.load(fh)
bin_pred = bin_model.predict(X_test_raw)
m_bin = metrics_of(y_true, bin_pred)

m_iso = metrics_of(y_true, pred_alarm)

print("\n" + "=" * 70)
print("СРАВНЕНИЕ ТРЁХ МОДЕЛЕЙ (тест, бинарный взгляд: тревога vs норма)")
print("=" * 70)
hdr = f"{'модель':<22s}  {'recall тр.':>10s}  {'prec тр.':>10s}  {'f1 macro':>10s}  {'acc':>6s}"
print(hdr); print("-" * len(hdr))
print(f"  {'multiclass XGBoost':<22s}  {m_mc['r1']:>10.3f}  {m_mc['p1']:>10.3f}  {m_mc['macro_f1']:>10.3f}  {m_mc['acc']:>6.3f}")
print(f"  {'binary XGBoost':<22s}  {m_bin['r1']:>10.3f}  {m_bin['p1']:>10.3f}  {m_bin['macro_f1']:>10.3f}  {m_bin['acc']:>6.3f}")
print(f"  {'IsolationForest':<22s}  {m_iso['r1']:>10.3f}  {m_iso['p1']:>10.3f}  {m_iso['macro_f1']:>10.3f}  {m_iso['acc']:>6.3f}")


# ---------------------------------------------------------------- save model
payload = {
    "model": iso,
    "imputer": imputer,
    "features": FEATURES,
    "contamination": 0.1,
}
out_pkl = MODEL_DIR / "isolation_forest.pkl"
with open(out_pkl, "wb") as fh:
    pickle.dump(payload, fh)
print(f"\nSaved → {out_pkl}")


# ---------------------------------------------------------------- comparison_table.md
def cm_md(cm: np.ndarray) -> str:
    head = "| true \\ pred | 0 | 1 |\n|---|---:|---:|"
    rows = [f"| {i} | {cm[i,0]} | {cm[i,1]} |" for i in range(2)]
    return head + "\n" + "\n".join(rows)

cm_mc  = confusion_matrix(y_true, mc_pred_bin, labels=[0, 1])
cm_bin = confusion_matrix(y_true, bin_pred,    labels=[0, 1])
cm_iso = confusion_matrix(y_true, pred_alarm,  labels=[0, 1])

md = f"""# Сравнение моделей предсказания тревоги

Сгенерировано: {date.today().isoformat()}

Тестовая выборка: **{len(test)} строк** (2019-01-01 .. {test['date'].max().date()}), из них **{int(y_true.sum())} тревог** ({(y_true.mean()*100):.1f}%).
Бинарный взгляд: «тревога» = `label ∈ {{1, 2}}`. Для multi-class модели предсказание собрано как `pred_class ∈ {{1, 2}}`.

## Сводная таблица

| модель | recall (тревога) | precision (тревога) | f1 macro | accuracy |
|---|---:|---:|---:|---:|
| multiclass XGBoost | {m_mc['r1']:.3f} | {m_mc['p1']:.3f} | {m_mc['macro_f1']:.3f} | {m_mc['acc']:.3f} |
| binary XGBoost     | {m_bin['r1']:.3f} | {m_bin['p1']:.3f} | {m_bin['macro_f1']:.3f} | {m_bin['acc']:.3f} |
| IsolationForest    | {m_iso['r1']:.3f} | {m_iso['p1']:.3f} | {m_iso['macro_f1']:.3f} | {m_iso['acc']:.3f} |

## Confusion matrices (бинарно)

### multiclass XGBoost
{cm_md(cm_mc)}

### binary XGBoost
{cm_md(cm_bin)}

### IsolationForest
{cm_md(cm_iso)}

## Anomaly scores для красных месяцев в тесте

«Higher = более аномальный». `pred_anomaly = 1` значит модель пометила месяц аномалией.

| date | anomaly_score | pred_anomaly |
|---|---:|:---:|
{chr(10).join(f"| {r['date']} | {r['anomaly_score']:.4f} | {r['pred_anomaly']} |" for _, r in out.iterrows())}

## Конфигурация IsolationForest

- train: только `label==0` в 2003-01..2018-12 ({len(train_green)} строк)
- features: 17 (те же, что в XGBoost)
- NaN imputation: median по train (`SimpleImputer`)
- params: n_estimators=200, contamination=0.1, random_state=42
"""
md_path = MODEL_DIR / "comparison_table.md"
md_path.write_text(md, encoding="utf-8")
print(f"Saved → {md_path}")
