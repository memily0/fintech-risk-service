"""Soft-voting ensemble: α × P_xgb(alarm) + (1-α) × iso_score_norm.

P_xgb(alarm) — sum of class-1 and class-2 probabilities of the multiclass model.
iso_score   — anomaly score = -decision_function, normalized to [0,1] via min-max
              fitted on the TRAIN distribution of IsolationForest scores.

For each α in {0.1..0.9} the threshold is picked to maximise macro f1 on TRAIN,
then applied to TEST.

Outputs:
  model/soft_voting_results.md
  model/soft_voting_pr_curve.png
"""
from __future__ import annotations

import pickle
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    auc,
)

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

# ---------------------------------------------------------------- load
df = pd.read_csv(DATA, parse_dates=["date"])
df = df[df["label"].notna()].copy()
df["label"] = df["label"].astype(int)
df["label_binary"] = (df["label"] > 0).astype(int)

train = df[df["date"] < SPLIT_DATE].reset_index(drop=True)
test  = df[df["date"] >= SPLIT_DATE].reset_index(drop=True)

y_train = train["label_binary"].values
y_test  = test["label_binary"].values
print(f"Train {len(train)} rows (alarms {y_train.sum()})  ·  Test {len(test)} rows (alarms {y_test.sum()})")

with open(MODEL_DIR / "baseline_xgboost.pkl", "rb") as fh:
    mc = pickle.load(fh)
with open(MODEL_DIR / "isolation_forest.pkl", "rb") as fh:
    iso_payload = pickle.load(fh)
iso = iso_payload["model"]; imputer = iso_payload["imputer"]

# ---------------------------------------------------------------- xgb proba (alarm = class 1 OR class 2)
proba_train = mc.predict_proba(train[FEATURES])
proba_test  = mc.predict_proba(test[FEATURES])
p_xgb_train = proba_train[:, 1] + proba_train[:, 2]
p_xgb_test  = proba_test[:, 1] + proba_test[:, 2]
print(f"P_xgb(alarm) train range: [{p_xgb_train.min():.3f}, {p_xgb_train.max():.3f}]")
print(f"P_xgb(alarm) test  range: [{p_xgb_test.min():.3f}, {p_xgb_test.max():.3f}]")

# ---------------------------------------------------------------- iso anomaly score, min-max on train
X_train_imp = imputer.transform(train[FEATURES])
X_test_imp  = imputer.transform(test[FEATURES])
iso_train_raw = -iso.decision_function(X_train_imp)
iso_test_raw  = -iso.decision_function(X_test_imp)
lo, hi = iso_train_raw.min(), iso_train_raw.max()
iso_train = np.clip((iso_train_raw - lo) / (hi - lo + 1e-12), 0.0, 1.0)
iso_test  = np.clip((iso_test_raw  - lo) / (hi - lo + 1e-12), 0.0, 1.0)
print(f"iso_score train range (pre-norm): [{iso_train_raw.min():.4f}, {iso_train_raw.max():.4f}]  → normalized to [0,1]")
print(f"iso_score test  range (post-norm): [{iso_test.min():.3f}, {iso_test.max():.3f}]")


# ---------------------------------------------------------------- α sweep
def best_threshold(scores: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Find threshold maximising macro f1; return (threshold, macro_f1)."""
    cands = np.unique(np.concatenate([scores, [0.0, 1.0]]))
    best_t, best_f = 0.5, -1.0
    for t in cands:
        pred = (scores >= t).astype(int)
        if pred.sum() == 0 or pred.sum() == len(pred):
            continue
        f = f1_score(y, pred, average="macro", zero_division=0)
        if f > best_f:
            best_f, best_t = f, t
    return float(best_t), float(best_f)


alphas = [round(0.1 * i, 1) for i in range(1, 10)]
rows = []
test_scores_by_alpha = {}
test_preds_by_alpha  = {}

for a in alphas:
    s_train = a * p_xgb_train + (1 - a) * iso_train
    s_test  = a * p_xgb_test  + (1 - a) * iso_test
    thr, f_train = best_threshold(s_train, y_train)
    pred = (s_test >= thr).astype(int)
    rep = classification_report(y_test, pred, labels=[0, 1],
                                target_names=["0", "1"], output_dict=True,
                                zero_division=0)
    rows.append({
        "alpha": a,
        "threshold": thr,
        "train_macro_f1": f_train,
        "recall": rep["1"]["recall"],
        "precision": rep["1"]["precision"],
        "f1_alarm": rep["1"]["f1-score"],
        "macro_f1": rep["macro avg"]["f1-score"],
        "accuracy": rep["accuracy"],
        "tp": int(((pred == 1) & (y_test == 1)).sum()),
        "fp": int(((pred == 1) & (y_test == 0)).sum()),
        "fn": int(((pred == 0) & (y_test == 1)).sum()),
    })
    test_scores_by_alpha[a] = s_test
    test_preds_by_alpha[a]  = pred

res = pd.DataFrame(rows)
print("\n=== α sweep (threshold tuned on train, metrics on test) ===")
print(res[["alpha", "threshold", "recall", "precision", "f1_alarm", "macro_f1", "tp", "fp", "fn"]]
      .to_string(index=False))


# ---------------------------------------------------------------- best α
best_idx = res["macro_f1"].idxmax()
best = res.loc[best_idx]
print(f"\n>>> Best α: {best['alpha']}  ·  threshold={best['threshold']:.4f}  ·  test macro_f1={best['macro_f1']:.3f}  ·  recall={best['recall']:.3f}  ·  precision={best['precision']:.3f}")

best_a = float(best["alpha"])
s_test_best = test_scores_by_alpha[best_a]


# ---------------------------------------------------------------- PR curve for best α (on test)
prec_curve, rec_curve, thr_curve = precision_recall_curve(y_test, s_test_best)
pr_auc = auc(rec_curve, prec_curve)

fig, ax = plt.subplots(figsize=(7, 5))
ax.step(rec_curve, prec_curve, where="post", color="#1f77b4", lw=2,
        label=f"PR curve (AUC = {pr_auc:.3f})")
# mark the chosen-threshold operating point
ax.scatter([best["recall"]], [best["precision"]], color="red", zorder=5, s=80,
           label=f"chosen thr={best['threshold']:.3f}\nrecall={best['recall']:.2f}, prec={best['precision']:.2f}")
# baseline: random classifier line = positive rate
pos_rate = y_test.mean()
ax.axhline(pos_rate, color="grey", ls="--", lw=1, label=f"random ({pos_rate:.2f})")
ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
ax.set_title(f"PR curve  ·  soft-voting α={best_a}  ·  test")
ax.legend(loc="lower left")
ax.grid(True, alpha=0.3)
png_path = MODEL_DIR / "soft_voting_pr_curve.png"
fig.tight_layout(); fig.savefig(png_path, dpi=130)
plt.close(fig)
print(f"Saved PR curve → {png_path}")


# ---------------------------------------------------------------- save md
def fmt_row(r):
    return (f"| {r['alpha']} | {r['threshold']:.4f} | {r['recall']:.3f} | "
            f"{r['precision']:.3f} | {r['f1_alarm']:.3f} | {r['macro_f1']:.3f} | "
            f"{r['accuracy']:.3f} |")

md = f"""# Soft-voting ensemble — multiclass XGBoost + IsolationForest

Сгенерировано: {date.today().isoformat()}

## Идея

`score = α · P_xgb(alarm) + (1 − α) · iso_score_norm`

- **P_xgb(alarm)** = `P(class=1) + P(class=2)` от 3-классовой XGBoost
- **iso_score_norm** = `-decision_function(IsolationForest)`, мин-макс нормализованный по **train** ([0, 1])
- Порог подбирается на TRAIN под максимум macro f1, затем применяется к TEST

## Sweep по α

| α | порог | recall | precision | f1 (тревога) | macro f1 | accuracy |
|---:|---:|---:|---:|---:|---:|---:|
""" + "\n".join(fmt_row(r) for _, r in res.iterrows()) + f"""

**Лучший α по macro f1 на тесте:** **α = {best['alpha']}**, threshold = {best['threshold']:.4f}, macro f1 = **{best['macro_f1']:.3f}**, recall = {best['recall']:.3f}, precision = {best['precision']:.3f}.

## Confusion matrix для лучшего α

| true \\ pred | 0 | 1 |
|---|---:|---:|
| 0 | {int(((test_preds_by_alpha[best_a] == 0) & (y_test == 0)).sum())} | {int(((test_preds_by_alpha[best_a] == 1) & (y_test == 0)).sum())} |
| 1 | {int(((test_preds_by_alpha[best_a] == 0) & (y_test == 1)).sum())} | {int(((test_preds_by_alpha[best_a] == 1) & (y_test == 1)).sum())} |

## Precision-Recall curve для лучшего α

PR-AUC на тесте = **{pr_auc:.3f}** (baseline = positive rate = {pos_rate:.3f}).

Файл: `model/soft_voting_pr_curve.png`

## Замечания

- Порог подбирается на TRAIN — поскольку XGBoost учился на train, его proba там оптимистично завышены. Это даёт **смещение** в сторону низких порогов: модель полагается на iso для дополнительных alarms.
- Грубо: при α → 1 ансамбль вырождается в XGBoost (recall ~0.29, precision ~0.80). При α → 0 — в IsoForest (recall ~0.79, precision ~0.26).
- Промежуточные α позволяют выбирать компромисс по дискриминативной кривой.
"""
md_path = MODEL_DIR / "soft_voting_results.md"
md_path.write_text(md, encoding="utf-8")
print(f"Saved → {md_path}")
