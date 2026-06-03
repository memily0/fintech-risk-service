from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "final_dataset.csv"
DEFAULT_PREDICTIONS_PATH = PROJECT_ROOT / "data" / "model_predictions.csv"
DEFAULT_METRICS_PATH = PROJECT_ROOT / "data" / "model_metrics.json"
DEFAULT_ARTIFACT_DIR = PROJECT_ROOT / "models" / "artifacts"

HORIZONS_DAYS = [7, 30, 90]
STRESS_THRESHOLD = 1.0
RANDOM_STATE = 42
LOGISTIC_REGRESSION_C = 0.01

MODEL_INPUT_COLUMNS = [
    "gold",
    "brent",
    "usd_rub",
    "eur_rub",
    "imoex",
    "vix",
    "sp500",
    "ofz_1y",
    "ofz_2y",
    "ofz_5y",
    "ofz_10y",
    "key_rate",
    "inflation",
    "ofz_spread_10_2",
    "usd_volatility",
    "imoex_volatility",
    "imoex_drawdown",
    "imoex_zscore",
    "real_key_rate",
]

RATE_LIKE_COLUMNS = {
    "ofz_1y",
    "ofz_2y",
    "ofz_5y",
    "ofz_10y",
    "key_rate",
    "inflation",
    "ofz_spread_10_2",
    "real_key_rate",
    "usd_volatility",
    "imoex_volatility",
    "imoex_drawdown",
    "imoex_zscore",
}

FEATURE_LABELS = {
    "gold": "Gold",
    "brent": "Brent",
    "usd_rub": "USD/RUB",
    "eur_rub": "EUR/RUB",
    "imoex": "IMOEX",
    "vix": "VIX",
    "sp500": "S&P500",
    "ofz_1y": "OFZ 1Y",
    "ofz_2y": "OFZ 2Y",
    "ofz_5y": "OFZ 5Y",
    "ofz_10y": "OFZ 10Y",
    "key_rate": "Key rate",
    "inflation": "Inflation",
    "ofz_spread_10_2": "OFZ 10Y-2Y spread",
    "usd_volatility": "USD/RUB volatility",
    "imoex_volatility": "IMOEX volatility",
    "imoex_drawdown": "IMOEX drawdown",
    "imoex_zscore": "IMOEX z-score",
    "real_key_rate": "Real key rate",
}


@dataclass
class FoldMetrics:
    train_end: str
    test_start: str
    test_end: str
    observations: int
    positive_rate: float
    roc_auc: float | None
    pr_auc: float | None
    brier_score: float


def trailing_zscore(series: pd.Series, window: int = 756, min_periods: int = 252) -> pd.Series:
    mean = series.rolling(window, min_periods=min_periods).mean().shift(1)
    std = series.rolling(window, min_periods=min_periods).std().shift(1).replace(0, np.nan)
    return ((series - mean) / std).clip(-6, 6)


def load_dataset(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    if "date" not in raw.columns:
        raise ValueError(f"{path} must contain a date column")
    converted = {"date": pd.to_datetime(raw["date"], errors="coerce")}
    for column in raw.columns:
        if column != "date":
            converted[column] = pd.to_numeric(raw[column], errors="coerce")
    df = pd.DataFrame(converted, columns=raw.columns)
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    missing = [column for column in MODEL_INPUT_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError("Missing model input columns: " + ", ".join(missing))
    return df


def build_stress_frame(df: pd.DataFrame) -> pd.DataFrame:
    raw_components = {
        "VIX": df["vix"],
        "USD/RUB volatility": df["usd_volatility"],
        "IMOEX volatility": df["imoex_volatility"],
        "IMOEX drawdown": df["imoex_drawdown"].abs(),
        "OFZ curve inversion": -df["ofz_spread_10_2"],
    }
    component_data: dict[str, pd.Series] = {"date": df["date"]}
    for label, series in raw_components.items():
        component_data[label] = trailing_zscore(series)
    result = pd.DataFrame(component_data)
    component_columns = [column for column in result.columns if column != "date"]
    stress_score = result[component_columns].mean(axis=1, skipna=True)
    return result.assign(
        stress_score=stress_score,
        stress_event=stress_score >= STRESS_THRESHOLD,
    )


def future_event_target(event: pd.Series, horizon_days: int) -> pd.Series:
    shifted_events = [event.shift(-offset) for offset in range(1, horizon_days + 1)]
    return pd.concat(shifted_events, axis=1).max(axis=1)


def add_target_columns(df: pd.DataFrame, stress: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    target_columns = {
        "stress_score": stress["stress_score"],
        "stress_event": stress["stress_event"].astype("float"),
    }
    max_date = result["date"].max()
    for horizon in HORIZONS_DAYS:
        target = future_event_target(stress["stress_event"].astype("float"), horizon)
        target = target.mask(result["date"] > max_date - pd.Timedelta(days=horizon))
        target_columns[f"target_{horizon}d"] = target
    return result.assign(**target_columns)


def add_model_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    features = pd.DataFrame(index=df.index)
    for column in MODEL_INPUT_COLUMNS:
        series = df[column]
        features[f"{column}__level_z"] = trailing_zscore(series)
        for window in [7, 30, 90]:
            lagged = series.shift(window)
            delta = series - lagged
            if column in RATE_LIKE_COLUMNS:
                features[f"{column}__delta_{window}d"] = delta
            else:
                denominator = lagged.abs().replace(0, np.nan)
                features[f"{column}__return_{window}d"] = delta / denominator
        features[f"{column}__missing"] = series.isna().astype(int)

    features = features.replace([np.inf, -np.inf], np.nan)
    feature_names = features.columns.tolist()
    return features, feature_names


def make_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    class_weight="balanced",
                    C=LOGISTIC_REGRESSION_C,
                    max_iter=2000,
                    random_state=RANDOM_STATE,
                    solver="lbfgs",
                ),
            ),
        ]
    )


def probability_to_regime(probability: float) -> str:
    if probability >= 0.8:
        return "Crisis"
    if probability >= 0.6:
        return "Stress"
    if probability >= 0.4:
        return "Elevated"
    if probability >= 0.2:
        return "Watch"
    return "Normal"


def safe_roc_auc(y_true: pd.Series, y_score: np.ndarray) -> float | None:
    if y_true.nunique(dropna=True) < 2:
        return None
    return float(roc_auc_score(y_true, y_score))


def safe_pr_auc(y_true: pd.Series, y_score: np.ndarray) -> float | None:
    if y_true.nunique(dropna=True) < 2:
        return None
    return float(average_precision_score(y_true, y_score))


def evaluate_walk_forward(
    features: pd.DataFrame,
    target: pd.Series,
    dates: pd.Series,
    cutoffs: list[str],
) -> tuple[list[FoldMetrics], pd.Series]:
    predictions = pd.Series(np.nan, index=features.index, dtype=float)
    metrics: list[FoldMetrics] = []
    cutoff_dates = [pd.Timestamp(value) for value in cutoffs]

    for idx, cutoff in enumerate(cutoff_dates):
        next_cutoff = cutoff_dates[idx + 1] if idx + 1 < len(cutoff_dates) else dates.max() + pd.Timedelta(days=1)
        train_mask = (dates < cutoff) & target.notna()
        test_mask = (dates >= cutoff) & (dates < next_cutoff) & target.notna()
        if train_mask.sum() < 200 or test_mask.sum() == 0:
            continue
        y_train = target.loc[train_mask].astype(int)
        y_test = target.loc[test_mask].astype(int)
        if y_train.nunique() < 2:
            continue

        pipeline = make_pipeline()
        pipeline.fit(features.loc[train_mask], y_train)
        y_score = pipeline.predict_proba(features.loc[test_mask])[:, 1]
        predictions.loc[test_mask] = y_score
        metrics.append(
            FoldMetrics(
                train_end=(cutoff - pd.Timedelta(days=1)).date().isoformat(),
                test_start=cutoff.date().isoformat(),
                test_end=(next_cutoff - pd.Timedelta(days=1)).date().isoformat(),
                observations=int(test_mask.sum()),
                positive_rate=float(y_test.mean()),
                roc_auc=safe_roc_auc(y_test, y_score),
                pr_auc=safe_pr_auc(y_test, y_score),
                brier_score=float(brier_score_loss(y_test, y_score)),
            )
        )

    return metrics, predictions


def transformed_feature_matrix(pipeline: Pipeline, features: pd.DataFrame) -> np.ndarray:
    imputed = pipeline.named_steps["imputer"].transform(features)
    return pipeline.named_steps["scaler"].transform(imputed)


def pretty_feature_name(feature: str) -> str:
    column, _, suffix = feature.partition("__")
    base = FEATURE_LABELS.get(column, column)
    suffix_label = {
        "level_z": "level z-score",
        "delta_7d": "7d change",
        "delta_30d": "30d change",
        "delta_90d": "90d change",
        "return_7d": "7d return",
        "return_30d": "30d return",
        "return_90d": "90d return",
        "missing": "missing flag",
    }.get(suffix, suffix)
    return f"{base}: {suffix_label}"


def top_driver_text(pipeline: Pipeline, row_features: pd.DataFrame, feature_names: list[str], limit: int = 5) -> str:
    scaled = transformed_feature_matrix(pipeline, row_features)
    coefs = pipeline.named_steps["model"].coef_[0]
    contributions = scaled[0] * coefs
    order = np.argsort(np.abs(contributions))[::-1]
    parts = []
    for feature_index in order[:limit]:
        value = contributions[feature_index]
        direction = "+" if value >= 0 else "-"
        parts.append(f"{pretty_feature_name(feature_names[feature_index])} ({direction}{abs(value):.2f})")
    return "; ".join(parts)


def train_horizon_model(
    full_df: pd.DataFrame,
    features: pd.DataFrame,
    feature_names: list[str],
    horizon: int,
    artifact_dir: Path,
) -> tuple[pd.DataFrame, dict]:
    target_name = f"target_{horizon}d"
    target = full_df[target_name]
    valid_mask = target.notna()
    y = target.loc[valid_mask].astype(int)
    if y.nunique() < 2:
        raise RuntimeError(f"Target {target_name} has fewer than two classes")

    cutoffs = ["2018-01-01", "2020-01-01", "2022-01-01", "2024-01-01"]
    fold_metrics, cv_predictions = evaluate_walk_forward(features, target, full_df["date"], cutoffs)

    final_pipeline = make_pipeline()
    final_pipeline.fit(features.loc[valid_mask], y)
    probabilities = final_pipeline.predict_proba(features)[:, 1]

    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"crisis_logreg_{horizon}d.joblib"
    joblib.dump(
        {
            "pipeline": final_pipeline,
            "feature_names": feature_names,
            "horizon_days": horizon,
            "stress_threshold": STRESS_THRESHOLD,
            "model_type": "balanced_logistic_regression",
            "regularization_c": LOGISTIC_REGRESSION_C,
        },
        artifact_path,
    )

    rows = []
    for idx, probability in enumerate(probabilities):
        row_features = features.iloc[[idx]]
        rows.append(
            {
                "date": full_df.loc[idx, "date"].date().isoformat(),
                "horizon_days": horizon,
                "stress_score": full_df.loc[idx, "stress_score"],
                "stress_event": bool(full_df.loc[idx, "stress_event"]),
                "target": target.loc[idx] if pd.notna(target.loc[idx]) else np.nan,
                "probability": probability,
                "regime": probability_to_regime(float(probability)),
                "top_drivers": top_driver_text(final_pipeline, row_features, feature_names),
                "cv_probability": cv_predictions.loc[idx] if pd.notna(cv_predictions.loc[idx]) else np.nan,
            }
        )

    latest_idx = full_df.index[-1]
    latest_probability = float(probabilities[-1])
    metric_payload = {
        "horizon_days": horizon,
        "artifact_path": str(artifact_path.relative_to(PROJECT_ROOT)),
        "target_positive_rate": float(y.mean()),
        "training_observations": int(valid_mask.sum()),
        "latest_date": full_df.loc[latest_idx, "date"].date().isoformat(),
        "latest_probability": latest_probability,
        "latest_regime": probability_to_regime(latest_probability),
        "folds": [asdict(metric) for metric in fold_metrics],
    }
    scored_folds = [metric for metric in fold_metrics if metric.roc_auc is not None]
    if scored_folds:
        metric_payload["mean_roc_auc"] = float(np.mean([metric.roc_auc for metric in scored_folds if metric.roc_auc is not None]))
        metric_payload["mean_pr_auc"] = float(np.mean([metric.pr_auc for metric in scored_folds if metric.pr_auc is not None]))
        metric_payload["mean_brier_score"] = float(np.mean([metric.brier_score for metric in scored_folds]))

    return pd.DataFrame(rows), metric_payload


def train_models(data_path: Path, predictions_path: Path, metrics_path: Path, artifact_dir: Path) -> dict:
    df = load_dataset(data_path)
    stress = build_stress_frame(df)
    full_df = add_target_columns(df, stress)
    features, feature_names = add_model_features(full_df)

    prediction_frames = []
    horizon_metrics = []
    for horizon in HORIZONS_DAYS:
        predictions, metrics = train_horizon_model(full_df, features, feature_names, horizon, artifact_dir)
        prediction_frames.append(predictions)
        horizon_metrics.append(metrics)

    prediction_output = pd.concat(prediction_frames, ignore_index=True)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    prediction_output.to_csv(predictions_path, index=False)

    metrics_payload = {
        "model_version": "mvp_1_balanced_logistic_regression",
        "generated_from": str(data_path.relative_to(PROJECT_ROOT)),
        "stress_threshold": STRESS_THRESHOLD,
        "regularization_c": LOGISTIC_REGRESSION_C,
        "horizons_days": HORIZONS_DAYS,
        "feature_count": len(feature_names),
        "features": feature_names,
        "horizons": horizon_metrics,
        "notes": [
            "Target is a future stress event based on a trailing z-score composite stress index.",
            "Feature transformations use lagged / trailing information only.",
            "This is an MVP baseline for product demonstration, not a production crisis model.",
        ],
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False) + "\n")
    return metrics_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train MVP crisis early-warning models.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS_PATH)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics = train_models(args.data, args.predictions, args.metrics, args.artifact_dir)
    print("[model] wrote", args.predictions)
    print("[model] wrote", args.metrics)
    for horizon in metrics["horizons"]:
        auc = horizon.get("mean_roc_auc")
        auc_text = "n/a" if auc is None else f"{auc:.3f}"
        print(
            f"[model] horizon={horizon['horizon_days']}d "
            f"latest={horizon['latest_probability']:.3f} "
            f"regime={horizon['latest_regime']} "
            f"mean_roc_auc={auc_text}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
