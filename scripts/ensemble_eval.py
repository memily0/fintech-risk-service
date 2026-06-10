"""Ensemble: multiclass XGBoost ∧ IsolationForest (AND) and ∨ (OR).

Loads model/baseline_xgboost.pkl, model/binary_xgboost.pkl,
model/isolation_forest.pkl and evaluates on the same time-split test set.

Outputs model/ensemble_results.md.
"""
from __future__ import annotations

import pickle
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
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

test = df[df["date"] >= SPLIT_DATE].reset_index(drop=True)
y_true = test["label_binary"].values
dates_test = test["date"]
print(f"Test: {len(test)} rows, alarms={int(y_true.sum())}")


# ---------------------------------------------------------------- predictions
with open(MODEL_DIR / "baseline_xgboost.pkl", "rb") as fh:
    mc = pickle.load(fh)
mc_pred = mc.predict(test[FEATURES])
pred_mc_alarm = (mc_pred > 0).astype(int)

with open(MODEL_DIR / "binary_xgboost.pkl", "rb") as fh:
    bn = pickle.load(fh)
pred_bin_alarm = bn.predict(test[FEATURES]).astype(int)

with open(MODEL_DIR / "isolation_forest.pkl", "rb") as fh:
    iso_payload = pickle.load(fh)
iso = iso_payload["model"]; imputer = iso_payload["imputer"]
X_test_imp = imputer.transform(test[FEATURES])
iso_raw = iso.predict(X_test_imp)  # 1 normal, -1 anomaly
pred_iso_alarm = (iso_raw == -1).astype(int)


# ---------------------------------------------------------------- ensembles
pred_and = (pred_mc_alarm & pred_iso_alarm).astype(int)
pred_or  = (pred_mc_alarm | pred_iso_alarm).astype(int)


# ---------------------------------------------------------------- metrics helpers
def metrics(y_true, y_pred):
    rep = classification_report(y_true, y_pred, labels=[0, 1],
                                target_names=["0", "1"], output_dict=True, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    return rep, cm

def fmt(rep):
    return (rep["1"]["recall"], rep["1"]["precision"], rep["1"]["f1-score"],
            rep["macro avg"]["f1-score"], rep["accuracy"])


reports = {
    "multiclass XGBoost": metrics(y_true, pred_mc_alarm),
    "binary XGBoost":     metrics(y_true, pred_bin_alarm),
    "IsolationForest":    metrics(y_true, pred_iso_alarm),
    "Ансамбль AND":       metrics(y_true, pred_and),
    "Ансамбль OR":        metrics(y_true, pred_or),
}

print("\n=== Ensembles ===")
print("Months flagged by ensemble AND:")
and_dates = dates_test[pred_and == 1].dt.strftime("%Y-%m").tolist()
print(" ", and_dates)
print("Months flagged by ensemble OR:")
or_dates = dates_test[pred_or == 1].dt.strftime("%Y-%m").tolist()
print(" ", or_dates)

print("\n=== Summary (alarm class) ===")
hdr = f"{'модель':<22s}  {'recall':>7s}  {'prec':>7s}  {'f1':>7s}  {'macro f1':>10s}  {'acc':>6s}"
print(hdr); print("-" * len(hdr))
for name, (rep, cm) in reports.items():
    r, p, f, mf, acc = fmt(rep)
    print(f"  {name:<22s}  {r:>7.3f}  {p:>7.3f}  {f:>7.3f}  {mf:>10.3f}  {acc:>6.3f}")


# ---------------------------------------------------------------- confusion matrices
def cm_str(cm):
    return f"TN={cm[0,0]} FP={cm[0,1]} | FN={cm[1,0]} TP={cm[1,1]}"

print("\nConfusion matrices:")
for name, (rep, cm) in reports.items():
    print(f"  {name:<22s}  {cm_str(cm)}")


# ---------------------------------------------------------------- compose dates table
test_aug = pd.DataFrame({
    "date": dates_test.dt.strftime("%Y-%m"),
    "label": test["label"].values,
    "mc": pred_mc_alarm,
    "iso": pred_iso_alarm,
    "AND": pred_and,
    "OR": pred_or,
})
print("\nFlagged months (label, mc, iso, AND, OR):")
print(test_aug[(test_aug["AND"] == 1) | (test_aug["OR"] == 1)].to_string(index=False))


# ---------------------------------------------------------------- save markdown
def cm_md(cm):
    head = "| true \\ pred | 0 | 1 |\n|---|---:|---:|"
    rows = [f"| {i} | {cm[i,0]} | {cm[i,1]} |" for i in range(2)]
    return head + "\n" + "\n".join(rows)

def list_md(dates):
    return ", ".join(f"`{d}`" for d in dates) if dates else "_(пусто)_"

and_rows = test_aug[test_aug["AND"] == 1]
or_rows  = test_aug[test_aug["OR"]  == 1]

rep_and, cm_and = reports["Ансамбль AND"]
rep_or,  cm_or  = reports["Ансамбль OR"]
r_and, p_and, f_and, mf_and, acc_and = fmt(rep_and)
r_or,  p_or,  f_or,  mf_or,  acc_or  = fmt(rep_or)

# build summary table
def row(name):
    r, p, f, mf, acc = fmt(reports[name][0])
    return f"| {name} | {r:.3f} | {p:.3f} | {f:.3f} | {mf:.3f} | {acc:.3f} |"

# month-by-month flag table (only rows where any model fired or label>0)
flag_rows = test_aug[(test_aug["mc"] | test_aug["iso"] | (test_aug["label"] > 0)) > 0]
flag_md = "| date | label | mc | iso | AND | OR |\n|---|:---:|:---:|:---:|:---:|:---:|"
for _, r in flag_rows.iterrows():
    flag_md += f"\n| {r['date']} | {r['label']} | {r['mc']} | {r['iso']} | {r['AND']} | {r['OR']} |"

md = f"""# Ансамбли — AND и OR над multiclass XGBoost + IsolationForest

Сгенерировано: {date.today().isoformat()}

Тест: **{len(test)} строк** (2019-01-01 .. {dates_test.max().date()}), тревог **{int(y_true.sum())}**.

## Правила

- **multiclass XGBoost**: тревога = `pred ∈ {{1, 2}}` (исходно 3-классовая модель)
- **IsolationForest**: тревога = месяц помечен аномалией (contamination=0.1)
- **AND**: финальная тревога только если **обе** модели согласны
- **OR**: финальная тревога если хотя бы **одна** модель тревожится

## Ансамбль AND

**Recall:** {r_and:.3f} · **Precision:** {p_and:.3f} · **f1 (тревога):** {f_and:.3f} · **macro f1:** {mf_and:.3f}

Месяцы, помеченные AND ({len(and_rows)}): {list_md(and_rows['date'].tolist())}

{cm_md(cm_and)}

## Ансамбль OR

**Recall:** {r_or:.3f} · **Precision:** {p_or:.3f} · **f1 (тревога):** {f_or:.3f} · **macro f1:** {mf_or:.3f}

Месяцы, помеченные OR ({len(or_rows)}): {list_md(or_rows['date'].tolist())}

{cm_md(cm_or)}

## Итоговая таблица всех 5 моделей

| модель | recall (тревога) | precision (тревога) | f1 (тревога) | macro f1 | accuracy |
|---|---:|---:|---:|---:|---:|
{row("multiclass XGBoost")}
{row("binary XGBoost")}
{row("IsolationForest")}
{row("Ансамбль AND")}
{row("Ансамбль OR")}

## Раскладка по месяцам

`mc` = multiclass XGB alarm; `iso` = IsolationForest alarm. Показаны только месяцы, где хотя бы одна модель тревожилась или истинная метка > 0.

{flag_md}
"""
out = MODEL_DIR / "ensemble_results.md"
out.write_text(md, encoding="utf-8")
print(f"\nSaved → {out}")
