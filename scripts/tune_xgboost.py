"""Tune XGBoost for crisis-class sensitivity.

Variant A: custom weights {0:1, 1:5, 2:10}
Variant B: threshold 0.15 on P(class=2), baseline balanced weights
Variant C: A + B

Also analyzes 6 missed crises (true=2, pred=0) vs train red-class means.
Saves best variant as model/tuned_xgboost.pkl.
"""
from __future__ import annotations

import pickle
import warnings
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
    "vix_mean", "vix_zscore",
    "fed_rate", "cbr_rate", "cpi_russia",
    "usdrub_vol", "usdrub_zscore",
    "imoex_return", "imoex_vol",
    "ofz_spread_filled",
]
TARGET = "label"
SPLIT_DATE = pd.Timestamp("2019-01-01")

df = pd.read_csv(DATA, parse_dates=["date"])
df = df[df[TARGET].notna()].copy()
df[TARGET] = df[TARGET].astype(int)

train = df[df["date"] < SPLIT_DATE]
test  = df[df["date"] >= SPLIT_DATE]
X_train, y_train = train[FEATURES], train[TARGET]
X_test,  y_test  = test[FEATURES],  test[TARGET]
dates_test = test["date"].reset_index(drop=True)
print(f"Train {len(train)} rows, test {len(test)} rows")


def fit_model(sample_weight: np.ndarray) -> xgb.XGBClassifier:
    m = xgb.XGBClassifier(
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
    m.fit(X_train, y_train, sample_weight=sample_weight, verbose=False)
    return m


def threshold_predict(proba: np.ndarray, thr_red: float = 0.5) -> np.ndarray:
    """If P(class=2) > thr_red → predict 2; else argmax over {0, 1}."""
    out = np.argmax(proba, axis=1)
    mask = proba[:, 2] > thr_red
    out[mask] = 2
    return out


def class2_stats(y_true: pd.Series, y_pred: np.ndarray) -> tuple[float, float, int, int, int]:
    yt = np.array(y_true)
    tp = int(((y_pred == 2) & (yt == 2)).sum())
    fp = int(((y_pred == 2) & (yt != 2)).sum())
    fn = int(((y_pred != 2) & (yt == 2)).sum())
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    return rec, prec, fp, tp, fn


# ============================================================== Baseline (reference)
classes = np.array(sorted(y_train.unique()))
balanced = compute_class_weight(class_weight="balanced", classes=classes, y=y_train)
balanced_map = dict(zip(classes, balanced))
print(f"\nBalanced weights (baseline): {balanced_map}")

m_base = fit_model(y_train.map(balanced_map).values)
proba_base = m_base.predict_proba(X_test)
pred_base = np.argmax(proba_base, axis=1)
rec0, prec0, fp0, tp0, fn0 = class2_stats(y_test, pred_base)


# ============================================================== Variant A: custom weights, argmax
A_W = {0: 1, 1: 5, 2: 10}
m_A = fit_model(y_train.map(A_W).values)
proba_A = m_A.predict_proba(X_test)
pred_A = np.argmax(proba_A, axis=1)
rec_A, prec_A, fp_A, tp_A, fn_A = class2_stats(y_test, pred_A)


# ============================================================== Variant B: balanced weights, threshold 0.15
THR = 0.15
pred_B = threshold_predict(proba_base, thr_red=THR)
rec_B, prec_B, fp_B, tp_B, fn_B = class2_stats(y_test, pred_B)


# ============================================================== Variant C: custom weights, threshold 0.15
pred_C = threshold_predict(proba_A, thr_red=THR)
rec_C, prec_C, fp_C, tp_C, fn_C = class2_stats(y_test, pred_C)


# ============================================================== compare
def fmt(name, rec, prec, fp, tp, fn):
    return f"  {name:30s} recall={rec:.3f}  precision={prec:.3f}  FP={fp:2d}  TP={tp:2d}  FN={fn:2d}"

print("\n=== Class 2 (crisis) sensitivity comparison ===")
print(fmt("Baseline (balanced, thr=argmax)", rec0, prec0, fp0, tp0, fn0))
print(fmt("A  weights {0:1,1:5,2:10}",       rec_A, prec_A, fp_A, tp_A, fn_A))
print(fmt(f"B  balanced + thr P(2)>{THR}",   rec_B, prec_B, fp_B, tp_B, fn_B))
print(fmt(f"C  A + thr P(2)>{THR}",          rec_C, prec_C, fp_C, tp_C, fn_C))

variants = {
    "A": (m_A, pred_A, rec_A, prec_A, fp_A, tp_A, fn_A, "argmax"),
    "B": (m_base, pred_B, rec_B, prec_B, fp_B, tp_B, fn_B, f"thr P(2)>{THR}"),
    "C": (m_A, pred_C, rec_C, prec_C, fp_C, tp_C, fn_C, f"thr P(2)>{THR}"),
}


# ============================================================== full reports for each variant
def full_report(name, y_true, y_pred):
    print(f"\n--- {name} ---")
    print(classification_report(y_true, y_pred, labels=[0,1,2],
                                target_names=["0","1","2"], zero_division=0))
    print("CM (rows=true, cols=pred):")
    print(confusion_matrix(y_true, y_pred, labels=[0,1,2]))

full_report("A", y_test, pred_A)
full_report("B", y_test, pred_B)
full_report("C", y_test, pred_C)


# ============================================================== pick the best by recall (tiebreak: precision)
best = max(variants.items(), key=lambda kv: (kv[1][2], kv[1][3]))
best_name, (best_model, best_pred, best_rec, best_prec, best_fp, best_tp, best_fn, best_rule) = best
print(f"\n>>> Best variant by (recall, precision) on class 2: {best_name}  recall={best_rec:.3f}  precision={best_prec:.3f}")

tuned_path = MODEL_DIR / "tuned_xgboost.pkl"
payload = {
    "variant": best_name,
    "rule": best_rule,
    "model": best_model,
    "threshold_class2": THR if best_name in ("B", "C") else None,
    "features": FEATURES,
}
with open(tuned_path, "wb") as fh:
    pickle.dump(payload, fh)
print(f"Saved best variant → {tuned_path}")


# ============================================================== error analysis: missed crises (baseline)
print("\n" + "=" * 70)
print("ERROR ANALYSIS — 6 пропущенных кризисов baseline (true=2, pred=0)")
print("=" * 70)

missed_mask = (y_test.values == 2) & (pred_base == 0)
missed_dates = dates_test[missed_mask].dt.strftime("%Y-%m").tolist()
print(f"missed months ({int(missed_mask.sum())}): {missed_dates}")

X_test_reset = X_test.reset_index(drop=True)
missed_rows = X_test_reset[missed_mask].copy()
missed_rows.insert(0, "date", dates_test[missed_mask].dt.strftime("%Y-%m").values)

# train red-class means/medians
red_train = train[train[TARGET] == 2][FEATURES]
red_mean = red_train.mean()
red_p10 = red_train.quantile(0.10)
red_p90 = red_train.quantile(0.90)

print(f"\nReference: train red-class stats ({len(red_train)} rows)")
ref = pd.DataFrame({"red_mean": red_mean, "red_p10": red_p10, "red_p90": red_p90}).round(3)
print(ref.to_string())

print("\nMissed months — feature values:")
print(missed_rows.round(3).to_string(index=False))

# flag per-feature outliers vs train red distribution
print("\nFlags ('*' = outside red [p10..p90] band):")
flag = pd.DataFrame(index=missed_rows.index)
flag["date"] = missed_rows["date"].values
for f in FEATURES:
    v = missed_rows[f].values
    lo, hi = red_p10[f], red_p90[f]
    flag[f] = ["*" if (not pd.isna(x) and (x < lo or x > hi)) else "" for x in v]
print(flag.to_string(index=False))


# ============================================================== save tuning_results.md
md_path = MODEL_DIR / "tuning_results.md"
def cm_md(cm: np.ndarray) -> str:
    head = "| true \\ pred | 0 | 1 | 2 |\n|---|---:|---:|---:|"
    rows = [f"| {i} | {cm[i,0]} | {cm[i,1]} | {cm[i,2]} |" for i in range(3)]
    return head + "\n" + "\n".join(rows)

cm_A = confusion_matrix(y_test, pred_A, labels=[0,1,2])
cm_B = confusion_matrix(y_test, pred_B, labels=[0,1,2])
cm_C = confusion_matrix(y_test, pred_C, labels=[0,1,2])

# build flags table as markdown
flag_md_rows = ["| date | " + " | ".join(FEATURES) + " |", "|---|" + "---|" * len(FEATURES)]
for _, row in flag.iterrows():
    flag_md_rows.append("| " + row["date"] + " | " + " | ".join(row[f] or "·" for f in FEATURES) + " |")

# missed values table
mv_rows = ["| date | " + " | ".join(FEATURES) + " |", "|---|" + "---:|" * len(FEATURES)]
for _, row in missed_rows.round(3).iterrows():
    vals = [str(row[f]) if not pd.isna(row[f]) else "NaN" for f in FEATURES]
    mv_rows.append("| " + row["date"] + " | " + " | ".join(vals) + " |")

ref_rows = ["| feature | red_mean | red_p10 | red_p90 |", "|---|---:|---:|---:|"]
for f in FEATURES:
    ref_rows.append(f"| {f} | {red_mean[f]:.3f} | {red_p10[f]:.3f} | {red_p90[f]:.3f} |")

md = f"""# XGBoost — tuning для recall по кризисному классу

## Сравнение вариантов (test, класс 2)

| вариант | правило | recall | precision | FP | TP | FN |
|---|---|---:|---:|---:|---:|---:|
| baseline | balanced + argmax | {rec0:.3f} | {prec0:.3f} | {fp0} | {tp0} | {fn0} |
| **A** | weights {{0:1, 1:5, 2:10}} + argmax | {rec_A:.3f} | {prec_A:.3f} | {fp_A} | {tp_A} | {fn_A} |
| **B** | balanced + thr P(2)>{THR} | {rec_B:.3f} | {prec_B:.3f} | {fp_B} | {tp_B} | {fn_B} |
| **C** | A + thr P(2)>{THR} | {rec_C:.3f} | {prec_C:.3f} | {fp_C} | {tp_C} | {fn_C} |

**Выбран лучший вариант:** **{best_name}** ({best_rule}) — recall={best_rec:.3f}, precision={best_prec:.3f}.
Сохранён в `model/tuned_xgboost.pkl` (payload = {{variant, rule, model, threshold_class2, features}}).

## Confusion matrices

### A
{cm_md(cm_A)}

### B
{cm_md(cm_B)}

### C
{cm_md(cm_C)}

## Разбор 6 пропущенных кризисов (baseline)

Месяцы, где **true = 2, pred = 0**: {", ".join(missed_dates)}

### Эталон — train red-class (n={len(red_train)})

{chr(10).join(ref_rows)}

### Значения признаков в пропущенных месяцах

{chr(10).join(mv_rows)}

### Флаги (`*` — значение вне диапазона train [p10..p90] красного класса)

{chr(10).join(flag_md_rows)}

### Вывод по ошибкам

Если в флаг-таблице по строке много `*` — это нетипичный для модели кризис (распределение не похоже на исторические GFC/2014).
Если флагов мало — модель видела похожие значения, но не научилась их связать с label=2: классическая нехватка данных в минорном классе.
"""
md_path.write_text(md, encoding="utf-8")
print(f"\nSaved tuning report → {md_path}")
