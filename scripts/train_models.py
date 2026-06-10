"""Train all models in a single pipeline.

Inputs:  data/processed/dataset_monthly.csv
Outputs:
  model/baseline_xgboost.pkl   — 3-class XGBoost
  model/binary_xgboost.pkl     — binary XGBoost
  model/isolation_forest.pkl   — IsolationForest (with imputer)
  model/soft_voting.pkl        — α=0.4 ensemble parameters + threshold
Также печатает финальную таблицу сравнения.
"""
from __future__ import annotations

import pickle
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, f1_score
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
SPLIT_DATE = pd.Timestamp("2019-01-01")
ALPHA = 0.4  # soft-voting weight from sweep


def split_and_load():
    df = pd.read_csv(DATA, parse_dates=["date"])
    df = df[df["label"].notna()].copy()
    df["label"] = df["label"].astype(int)
    df["label_binary"] = (df["label"] > 0).astype(int)
    train = df[df["date"] < SPLIT_DATE].reset_index(drop=True)
    test  = df[df["date"] >= SPLIT_DATE].reset_index(drop=True)
    return train, test


def train_multiclass(train: pd.DataFrame) -> xgb.XGBClassifier:
    y = train["label"]
    classes = np.array(sorted(y.unique()))
    cw = compute_class_weight(class_weight="balanced", classes=classes, y=y)
    sw = y.map(dict(zip(classes, cw))).values
    m = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        objective="multi:softprob", num_class=3, eval_metric="mlogloss",
        use_label_encoder=False, tree_method="hist", random_state=42,
    )
    m.fit(train[FEATURES], y, sample_weight=sw, verbose=False)
    return m


def train_binary(train: pd.DataFrame) -> xgb.XGBClassifier:
    y = train["label_binary"]
    n_neg, n_pos = int((y == 0).sum()), int((y == 1).sum())
    m = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        objective="binary:logistic", eval_metric="logloss",
        use_label_encoder=False, tree_method="hist",
        scale_pos_weight=n_neg / max(n_pos, 1), random_state=42,
    )
    m.fit(train[FEATURES], y, verbose=False)
    return m


def train_isoforest(train: pd.DataFrame) -> tuple[IsolationForest, SimpleImputer]:
    green = train[train["label"] == 0]
    imp = SimpleImputer(strategy="median")
    X = imp.fit_transform(green[FEATURES])
    iso = IsolationForest(n_estimators=200, contamination=0.1,
                          random_state=42, n_jobs=-1)
    iso.fit(X)
    return iso, imp


def tune_softvoting(p_xgb_train, iso_train_norm, y_train, alpha) -> float:
    s = alpha * p_xgb_train + (1 - alpha) * iso_train_norm
    cands = np.unique(np.concatenate([s, [0.0, 1.0]]))
    best_t, best_f = 0.5, -1.0
    for t in cands:
        pred = (s >= t).astype(int)
        if pred.sum() in (0, len(pred)):
            continue
        f = f1_score(y_train, pred, average="macro", zero_division=0)
        if f > best_f:
            best_f, best_t = f, t
    return float(best_t)


def summarize(name, y_true, y_pred):
    rep = classification_report(y_true, y_pred, labels=[0, 1],
                                target_names=["0", "1"], output_dict=True,
                                zero_division=0)
    return {
        "model": name,
        "recall": rep["1"]["recall"],
        "precision": rep["1"]["precision"],
        "f1_alarm": rep["1"]["f1-score"],
        "macro_f1": rep["macro avg"]["f1-score"],
        "accuracy": rep["accuracy"],
    }


def main():
    train, test = split_and_load()
    print(f"Train {len(train)} rows  ·  Test {len(test)} rows  ·  alarms test = {int(test['label_binary'].sum())}")

    # multiclass
    mc = train_multiclass(train)
    with open(MODEL_DIR / "baseline_xgboost.pkl", "wb") as fh:
        pickle.dump(mc, fh)

    # binary
    bn = train_binary(train)
    with open(MODEL_DIR / "binary_xgboost.pkl", "wb") as fh:
        pickle.dump(bn, fh)

    # iso
    iso, imp = train_isoforest(train)
    with open(MODEL_DIR / "isolation_forest.pkl", "wb") as fh:
        pickle.dump({"model": iso, "imputer": imp, "features": FEATURES,
                     "contamination": 0.1}, fh)

    # predictions on test
    y_test = test["label_binary"].values
    proba_test = mc.predict_proba(test[FEATURES])
    p_xgb_test = proba_test[:, 1] + proba_test[:, 2]
    mc_pred_alarm = (mc.predict(test[FEATURES]) > 0).astype(int)
    bn_pred_alarm = bn.predict(test[FEATURES]).astype(int)

    X_test_imp = imp.transform(test[FEATURES])
    iso_test_raw = -iso.decision_function(X_test_imp)
    iso_pred_alarm = (iso.predict(X_test_imp) == -1).astype(int)

    # need train-side scores for soft-voting threshold
    proba_train = mc.predict_proba(train[FEATURES])
    p_xgb_train = proba_train[:, 1] + proba_train[:, 2]
    X_train_imp = imp.transform(train[FEATURES])
    iso_train_raw = -iso.decision_function(X_train_imp)
    lo, hi = iso_train_raw.min(), iso_train_raw.max()
    iso_train_norm = np.clip((iso_train_raw - lo) / (hi - lo + 1e-12), 0, 1)
    iso_test_norm  = np.clip((iso_test_raw  - lo) / (hi - lo + 1e-12), 0, 1)

    threshold = tune_softvoting(p_xgb_train, iso_train_norm,
                                train["label_binary"].values, ALPHA)
    sv_test_score = ALPHA * p_xgb_test + (1 - ALPHA) * iso_test_norm
    sv_pred = (sv_test_score >= threshold).astype(int)

    with open(MODEL_DIR / "soft_voting.pkl", "wb") as fh:
        pickle.dump({
            "alpha": ALPHA, "threshold": threshold,
            "iso_norm_lo": float(lo), "iso_norm_hi": float(hi),
            "features": FEATURES,
            "note": "score = alpha*P_xgb(alarm) + (1-alpha)*iso_score_normalized; alarm if score >= threshold",
        }, fh)

    # ensembles for completeness
    and_pred = (mc_pred_alarm & iso_pred_alarm).astype(int)
    or_pred  = (mc_pred_alarm | iso_pred_alarm).astype(int)

    rows = [
        summarize("multiclass XGBoost", y_test, mc_pred_alarm),
        summarize("binary XGBoost",     y_test, bn_pred_alarm),
        summarize("IsolationForest",    y_test, iso_pred_alarm),
        summarize("Ансамбль AND",       y_test, and_pred),
        summarize("Ансамбль OR",        y_test, or_pred),
        summarize(f"Soft voting α={ALPHA}", y_test, sv_pred),
    ]
    res = pd.DataFrame(rows)

    print("\n=== Финальное сравнение моделей (test 2019-01..end) ===")
    print(res.to_string(index=False, formatters={
        "recall": "{:.3f}".format, "precision": "{:.3f}".format,
        "f1_alarm": "{:.3f}".format, "macro_f1": "{:.3f}".format,
        "accuracy": "{:.3f}".format,
    }))

    print(f"\nSoft-voting threshold (tuned on train): {threshold:.4f}")
    print(f"All models saved to {MODEL_DIR}/")


if __name__ == "__main__":
    main()
