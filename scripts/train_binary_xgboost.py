"""Binary XGBoost: 0 = норма, 1 = стресс OR кризис.

Same 17 features and same time split as the 3-class baseline.
Compares to the multiclass model collapsed to binary {0} vs {1,2}.
Outputs:
  model/binary_xgboost.pkl
  model/binary_metrics.md
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
TARGET = "label"
SPLIT_DATE = pd.Timestamp("2019-01-01")


df = pd.read_csv(DATA, parse_dates=["date"])
df = df[df[TARGET].notna()].copy()
df[TARGET] = df[TARGET].astype(int)
df["label_binary"] = (df[TARGET] > 0).astype(int)

train = df[df["date"] < SPLIT_DATE]
test  = df[df["date"] >= SPLIT_DATE]
X_train, y_train_bin = train[FEATURES], train["label_binary"]
X_test,  y_test_bin  = test[FEATURES],  test["label_binary"]
y_train_mc = train[TARGET]
y_test_mc  = test[TARGET]

print(f"Train: {len(train)} rows  ({train['date'].min().date()} .. {train['date'].max().date()})")
print(f"Test:  {len(test)} rows   ({test['date'].min().date()} .. {test['date'].max().date()})")

def dist_bin(s: pd.Series) -> str:
    vc = s.value_counts().sort_index()
    return ", ".join(f"{int(k)}={int(v)} ({v/len(s)*100:.1f}%)" for k, v in vc.items())

print(f"  train (binary): {dist_bin(y_train_bin)}")
print(f"  test  (binary): {dist_bin(y_test_bin)}")


# ---------------------------------------------------------------- scale_pos_weight
n_neg = int((y_train_bin == 0).sum())
n_pos = int((y_train_bin == 1).sum())
spw = n_neg / max(n_pos, 1)
print(f"\nscale_pos_weight = {n_neg}/{n_pos} = {spw:.3f}")


# ---------------------------------------------------------------- train
model = xgb.XGBClassifier(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    objective="binary:logistic",
    eval_metric="logloss",
    use_label_encoder=False,
    tree_method="hist",
    scale_pos_weight=spw,
    random_state=42,
)
model.fit(X_train, y_train_bin, verbose=False)
print("Model trained.")


# ---------------------------------------------------------------- evaluate binary
y_pred_bin = model.predict(X_test)
print("\n=== Binary model (test) ===")
print(classification_report(y_test_bin, y_pred_bin, labels=[0, 1],
                            target_names=["0 (норма)", "1 (стресс∪кризис)"],
                            zero_division=0))
cm_bin = confusion_matrix(y_test_bin, y_pred_bin, labels=[0, 1])
print("Confusion matrix:")
print(cm_bin)


# ---------------------------------------------------------------- multiclass projected to binary
mc_pkl = MODEL_DIR / "baseline_xgboost.pkl"
with open(mc_pkl, "rb") as fh:
    mc_model = pickle.load(fh)
y_pred_mc = mc_model.predict(X_test)
y_pred_mc_bin = (y_pred_mc > 0).astype(int)

print("\n=== Multiclass projected to binary (test) ===")
print(classification_report(y_test_bin, y_pred_mc_bin, labels=[0, 1],
                            target_names=["0 (норма)", "1 (стресс∪кризис)"],
                            zero_division=0))
cm_mc_bin = confusion_matrix(y_test_bin, y_pred_mc_bin, labels=[0, 1])
print("Confusion matrix:")
print(cm_mc_bin)


# ---------------------------------------------------------------- feature importance
imp = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False)
print("\nFeature importance (binary, top 10):")
for k, v in imp.head(10).items():
    print(f"  {k:22s} {v:.4f}")


# ---------------------------------------------------------------- save model
out_pkl = MODEL_DIR / "binary_xgboost.pkl"
with open(out_pkl, "wb") as fh:
    pickle.dump(model, fh)
print(f"\nSaved model → {out_pkl}")


# ---------------------------------------------------------------- side-by-side metrics
def metrics_of(y_true, y_pred):
    rep = classification_report(y_true, y_pred, labels=[0, 1],
                                target_names=["0", "1"], output_dict=True, zero_division=0)
    return {
        "p0": rep["0"]["precision"], "r0": rep["0"]["recall"], "f0": rep["0"]["f1-score"],
        "p1": rep["1"]["precision"], "r1": rep["1"]["recall"], "f1": rep["1"]["f1-score"],
        "acc": rep["accuracy"],
        "macro_f1": rep["macro avg"]["f1-score"],
    }

m_bin = metrics_of(y_test_bin, y_pred_bin)
m_mc  = metrics_of(y_test_bin, y_pred_mc_bin)

print("\n=== Side-by-side (test, binary view) ===")
hdr = f"{'metric':<22s}  {'binary':>10s}  {'multiclass→bin':>16s}"
print(hdr); print("-" * len(hdr))
for label, key in [
    ("precision (norma)",  "p0"),
    ("recall (norma)",     "r0"),
    ("f1 (norma)",         "f0"),
    ("precision (alarm)",  "p1"),
    ("recall (alarm)",     "r1"),
    ("f1 (alarm)",         "f1"),
    ("accuracy",           "acc"),
    ("macro f1",           "macro_f1"),
]:
    print(f"  {label:<22s}  {m_bin[key]:>10.3f}  {m_mc[key]:>16.3f}")


# ---------------------------------------------------------------- save metrics.md
def cm_md(cm: np.ndarray, labels=("0","1")) -> str:
    head = f"| true \\ pred | {labels[0]} | {labels[1]} |\n|---|---:|---:|"
    rows = [f"| {labels[i]} | {cm[i,0]} | {cm[i,1]} |" for i in range(2)]
    return head + "\n" + "\n".join(rows)

md = f"""# Binary XGBoost — норма vs тревога

Сгенерировано: {date.today().isoformat()}  ·  скрипт: `scripts/train_binary_xgboost.py`

## Конфигурация

- **label_binary** = 1 если `label > 0` (стресс или кризис), иначе 0
- **Признаки** ({len(FEATURES)}): те же, что в трёхклассовой модели
- **Split**: train 2003-01..2018-12 ({len(train)} строк), test 2019-01..{test['date'].max().date()} ({len(test)} строк)
- **scale_pos_weight** = n_neg/n_pos = {n_neg}/{n_pos} = **{spw:.3f}**
- XGBoost: n_estimators=200, max_depth=4, lr=0.05, `binary:logistic`, eval=`logloss`, tree=`hist`

### Распределение классов
| split | label=0 (норма) | label=1 (тревога) |
|---|---:|---:|
| train | {(y_train_bin == 0).sum()} ({(y_train_bin == 0).mean()*100:.1f}%) | {(y_train_bin == 1).sum()} ({(y_train_bin == 1).mean()*100:.1f}%) |
| test  | {(y_test_bin == 0).sum()} ({(y_test_bin == 0).mean()*100:.1f}%) | {(y_test_bin == 1).sum()} ({(y_test_bin == 1).mean()*100:.1f}%) |

## Classification report (test)

| class | precision | recall | f1 | support |
|---|---:|---:|---:|---:|
| 0 (норма) | {m_bin['p0']:.3f} | {m_bin['r0']:.3f} | {m_bin['f0']:.3f} | {int((y_test_bin==0).sum())} |
| 1 (тревога) | {m_bin['p1']:.3f} | {m_bin['r1']:.3f} | {m_bin['f1']:.3f} | {int((y_test_bin==1).sum())} |
| **accuracy** | | | **{m_bin['acc']:.3f}** | {len(y_test_bin)} |
| macro avg | | | {m_bin['macro_f1']:.3f} | |

## Confusion matrix (binary)

{cm_md(cm_bin)}

## Сравнение: бинарная vs трёхклассовая (спроецированная)

«Тревога» в обоих случаях = pred ∈ {{1, 2}}, истина = label ∈ {{1, 2}}.

| метрика | binary | multiclass→binary |
|---|---:|---:|
| precision (норма)  | {m_bin['p0']:.3f} | {m_mc['p0']:.3f} |
| recall (норма)     | {m_bin['r0']:.3f} | {m_mc['r0']:.3f} |
| f1 (норма)         | {m_bin['f0']:.3f} | {m_mc['f0']:.3f} |
| precision (тревога)| {m_bin['p1']:.3f} | {m_mc['p1']:.3f} |
| recall (тревога)   | {m_bin['r1']:.3f} | {m_mc['r1']:.3f} |
| f1 (тревога)       | {m_bin['f1']:.3f} | {m_mc['f1']:.3f} |
| accuracy           | {m_bin['acc']:.3f} | {m_mc['acc']:.3f} |
| macro f1           | {m_bin['macro_f1']:.3f} | {m_mc['macro_f1']:.3f} |

### Confusion matrix — multiclass spectrum collapsed to binary
{cm_md(cm_mc_bin)}

## Feature importance (топ 10)

| feature | importance |
|---|---:|
{chr(10).join(f"| {k} | {v:.4f} |" for k, v in imp.head(10).items())}
"""
md_path = MODEL_DIR / "binary_metrics.md"
md_path.write_text(md, encoding="utf-8")
print(f"Saved metrics → {md_path}")
