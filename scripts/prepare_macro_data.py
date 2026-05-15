from __future__ import annotations

import json
import os
import re
from pathlib import Path

CACHE_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(CACHE_ROOT / ".mpl-cache"))
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_ROOT / ".cache"))

import matplotlib
import numpy as np
import pandas as pd
import seaborn as sns
import yfinance as yf

matplotlib.use("Agg")
import matplotlib.pyplot as plt


START_DATE = "2014-01-01"
END_DATE = "2026-01-01"

MARKET_TICKERS = {
    "GC=F": "gold_price",
    "CL=F": "oil_price",
    "RUB=X": "usd_rub",
    "^VIX": "vix",
    "^GSPC": "sp500",
}

KNOWN_LOCAL_MARKET_FILES = {
    "gold.csv",
    "brent.csv",
    "usd_rub.csv",
    "sp500.csv",
    "vix.csv",
}

CRISIS_PERIODS = [
    ("2014-11-01", "2015-03-31", "RUB/Oil Shock"),
    ("2020-03-01", "2020-06-30", "COVID Shock"),
    ("2022-02-24", "2022-12-31", "Geopolitical Shock"),
    ("2024-01-01", "2025-12-31", "High Rate / Inflation Period"),
]

TARGET_NAME_MAP = {
    "key_rate": "key_rate",
    "inflation": "inflation",
    "cpi": "inflation",
}


def to_snake_case(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def ensure_directories(project_root: Path) -> tuple[Path, Path]:
    processed_dir = project_root / "data" / "processed"
    figures_dir = project_root / "reports" / "figures"
    processed_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    (project_root / ".cache").mkdir(exist_ok=True)
    (project_root / ".mpl-cache").mkdir(exist_ok=True)
    return processed_dir, figures_dir


def clean_existing_figures(figures_dir: Path) -> None:
    for figure_path in figures_dir.glob("*.png"):
        figure_path.unlink()


def flatten_yfinance_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if not isinstance(df.columns, pd.MultiIndex):
        return df

    collapsed = {}
    for top, bottom in df.columns:
        if bottom == ticker:
            collapsed[top] = df[(top, bottom)]
        else:
            collapsed[f"{top}_{bottom}"] = df[(top, bottom)]
    return pd.DataFrame(collapsed, index=df.index)


def download_market_series(ticker: str, feature_name: str) -> tuple[pd.DataFrame, dict]:
    raw_df = yf.download(
        ticker,
        start=START_DATE,
        end=END_DATE,
        interval="1d",
        progress=False,
        auto_adjust=False,
    )

    source_method = "download"
    flat_df = flatten_yfinance_columns(raw_df, ticker)
    if flat_df.empty:
        history_df = yf.Ticker(ticker).history(
            start=START_DATE,
            end=END_DATE,
            interval="1d",
            auto_adjust=False,
        )
        flat_df = history_df.copy()
        source_method = "history"

    if flat_df.empty:
        raise RuntimeError(f"Downloaded empty dataset for {ticker}")

    price_source = "Adj Close" if "Adj Close" in flat_df.columns else "Close"
    if price_source not in flat_df.columns:
        raise RuntimeError(f"Neither Adj Close nor Close is available for {ticker}")

    series_df = flat_df[[price_source]].rename(columns={price_source: feature_name}).copy()
    series_df.index = pd.to_datetime(series_df.index).tz_localize(None)
    series_df.index.name = "date"
    series_df = series_df.sort_index()
    series_df.index = series_df.index.strftime("%Y-%m-%d")
    series_df = series_df.reset_index()

    metadata = {
        "ticker": ticker,
        "feature_name": feature_name,
        "price_source": price_source,
        "source_method": source_method,
        "rows": len(series_df),
    }
    return series_df, metadata


def build_market_dataset() -> tuple[pd.DataFrame, list[dict]]:
    market_frames = []
    metadata = []
    for ticker, feature_name in MARKET_TICKERS.items():
        series_df, series_meta = download_market_series(ticker, feature_name)
        market_frames.append(series_df.set_index("date"))
        metadata.append(series_meta)

    market_df = pd.concat(market_frames, axis=1).sort_index()
    market_df.index = pd.to_datetime(market_df.index)
    market_df.index.name = "date"
    return market_df, metadata


def find_local_macro_files(project_root: Path) -> list[Path]:
    files = []
    for pattern in ("*.csv", "*.xlsx", "*.xls"):
        files.extend(project_root.rglob(pattern))

    excluded_parts = {"data/processed", "reports/figures", ".git", "__pycache__"}
    relevant = []
    for file_path in files:
        relative = file_path.relative_to(project_root).as_posix()
        if any(part in relative for part in excluded_parts):
            continue
        if file_path.name in KNOWN_LOCAL_MARKET_FILES:
            continue
        relevant.append(file_path)
    return sorted(relevant)


def load_dataframe(file_path: Path) -> pd.DataFrame:
    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
    try:
        df = pd.read_csv(file_path)
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding="cp1251")
    if len(df.columns) == 1 and ";" in df.columns[0]:
        df = pd.read_csv(file_path, sep=";", decimal=",")
    return df


def detect_date_column(df: pd.DataFrame) -> str:
    preferred_names = ["date", "datetime", "month", "period", "time"]
    normalized = {to_snake_case(column): column for column in df.columns}
    for preferred in preferred_names:
        if preferred in normalized:
            return normalized[preferred]

    best_column = None
    best_score = -1.0
    for column in df.columns:
        sample = df[column].dropna().astype(str).head(25)
        if sample.empty:
            continue
        parsed = pd.to_datetime(sample, errors="coerce", dayfirst=True)
        score = parsed.notna().mean()
        if score > best_score:
            best_score = score
            best_column = column

    if best_column is None or best_score < 0.5:
        raise ValueError("Unable to detect date column")
    return best_column


def parse_dates(series: pd.Series) -> pd.Series:
    non_null = series.dropna().astype(str)
    if non_null.empty:
        return pd.to_datetime(series, errors="coerce")

    month_like_share = non_null.str.fullmatch(r"\d{2}\.\d{4}").mean()
    if month_like_share > 0.8:
        return pd.to_datetime("01." + series.astype(str), format="%d.%m.%Y", errors="coerce")

    return pd.to_datetime(series, errors="coerce", dayfirst=False)


def standardize_local_macro_file(file_path: Path, project_root: Path) -> dict | None:
    raw_df = load_dataframe(file_path)
    date_column = detect_date_column(raw_df)
    df = raw_df.copy()
    df[date_column] = parse_dates(df[date_column])
    df = df.dropna(subset=[date_column]).copy()
    df = df.sort_values(date_column).drop_duplicates(subset=[date_column], keep="last")

    rename_map = {date_column: "date"}
    for column in df.columns:
        if column == date_column:
            continue
        snake = to_snake_case(column)
        rename_map[column] = TARGET_NAME_MAP.get(snake, snake)
    df = df.rename(columns=rename_map)

    numeric_columns = []
    for column in df.columns:
        if column == "date":
            continue
        if df[column].dtype == object:
            df[column] = (
                df[column]
                .astype(str)
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
        df[column] = pd.to_numeric(df[column], errors="coerce")
        numeric_columns.append(column)

    numeric_columns = [column for column in numeric_columns if df[column].notna().any()]
    if not numeric_columns:
        return None

    df = df[["date", *numeric_columns]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    return {
        "file_path": file_path.relative_to(project_root).as_posix(),
        "date_column": date_column,
        "features": numeric_columns,
        "data": df,
    }


def build_local_macro_sources(project_root: Path) -> list[dict]:
    sources = []
    for file_path in find_local_macro_files(project_root):
        standardized = standardize_local_macro_file(file_path, project_root)
        if standardized is not None:
            sources.append(standardized)
    return sources


def build_monthly_macro_daily(local_sources: list[dict], daily_index: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not local_sources:
        daily_macro = pd.DataFrame(index=daily_index)
        daily_macro.index.name = "date"
        monthly_levels = pd.DataFrame()
        return daily_macro, monthly_levels

    monthly_level_frames = []
    monthly_feature_frames = []

    for source in local_sources:
        df = source["data"].copy().set_index("date").sort_index()
        monthly_level_frames.append(df[source["features"]])

        feature_frame = pd.DataFrame(index=df.index)
        for column in source["features"]:
            feature_frame[column] = df[column]
            feature_frame[f"{column}_is_original_monthly"] = 1
            feature_frame[f"{column}_lag_1m"] = df[column].shift(1)
            feature_frame[f"{column}_lag_3m"] = df[column].shift(3)
            feature_frame[f"{column}_lag_6m"] = df[column].shift(6)
            feature_frame[f"{column}_monthly_change"] = df[column].diff(1)
            feature_frame[f"{column}_monthly_pct_change"] = df[column].pct_change(1)
        monthly_feature_frames.append(feature_frame)

    monthly_levels = pd.concat(monthly_level_frames, axis=1).sort_index()
    monthly_levels = monthly_levels.loc[:, ~monthly_levels.columns.duplicated()]

    monthly_features = pd.concat(monthly_feature_frames, axis=1).sort_index()
    monthly_features = monthly_features.loc[:, ~monthly_features.columns.duplicated()]
    daily_macro = monthly_features.reindex(daily_index).ffill()
    daily_macro.index.name = "date"
    return daily_macro, monthly_levels


def build_monthly_level_frame(monthly_levels: pd.DataFrame, daily_index: pd.DatetimeIndex) -> pd.DataFrame:
    if monthly_levels.empty:
        level_frame = pd.DataFrame(index=daily_index)
        level_frame.index.name = "date"
        return level_frame

    level_frame = monthly_levels.reindex(daily_index).ffill()
    for column in monthly_levels.columns:
        level_frame[f"{column}_is_original_monthly"] = 1
    level_frame.index.name = "date"
    return level_frame


def build_market_feature_frame(market_df: pd.DataFrame, daily_index: pd.DatetimeIndex) -> pd.DataFrame:
    feature_frame = market_df.copy()
    for column in market_df.columns:
        feature_frame[f"{column}_daily_pct_change"] = market_df[column].pct_change(1, fill_method=None)
        feature_frame[f"{column}_pct_change_7d"] = market_df[column].pct_change(7, fill_method=None)
        feature_frame[f"{column}_pct_change_14d"] = market_df[column].pct_change(14, fill_method=None)
        feature_frame[f"{column}_lag_1d"] = market_df[column].shift(1)
        feature_frame[f"{column}_lag_7d"] = market_df[column].shift(7)
        feature_frame[f"{column}_lag_14d"] = market_df[column].shift(14)
    return feature_frame.reindex(daily_index)


def normalize_for_plot(series: pd.Series) -> pd.Series:
    clean = series.dropna()
    if clean.empty or clean.iloc[0] == 0:
        return series * np.nan
    return series / clean.iloc[0] * 100


def add_crisis_highlights(ax: plt.Axes) -> None:
    for start, end, label in CRISIS_PERIODS:
        ax.axvspan(pd.to_datetime(start), pd.to_datetime(end), alpha=0.14, label=label)


def save_line_plot(data: pd.DataFrame, column: str, title: str, output_path: Path, color: str | None = None) -> str:
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(data.index, data[column], linewidth=1.5, color=color)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel(column)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path.name


def save_figures(
    market_df: pd.DataFrame,
    merged_levels: pd.DataFrame,
    features_df: pd.DataFrame,
    monthly_levels: pd.DataFrame,
    figures_dir: Path,
) -> list[str]:
    saved = []

    for column in ["gold_price", "oil_price", "usd_rub", "vix", "sp500"]:
        if column in market_df.columns:
            saved.append(
                save_line_plot(market_df, column, f"{column} over time", figures_dir / f"{column}_over_time.png")
            )

    for column in ["key_rate", "inflation"]:
        if column in merged_levels.columns:
            saved.append(
                save_line_plot(merged_levels, column, f"{column} over time", figures_dir / f"{column}_over_time.png")
            )

    if "gold_price" in market_df.columns:
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(market_df.index, market_df["gold_price"], linewidth=1.6, color="#b58900")
        add_crisis_highlights(ax)
        handles, labels = ax.get_legend_handles_labels()
        unique_labels = dict(zip(labels, handles))
        ax.legend(unique_labels.values(), unique_labels.keys(), loc="upper left", fontsize=8)
        ax.set_title("gold_price with crisis periods highlighted")
        ax.set_xlabel("Date")
        ax.set_ylabel("gold_price")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        output_name = "gold_price_with_crisis_periods.png"
        fig.savefig(figures_dir / output_name, dpi=150)
        plt.close(fig)
        saved.append(output_name)

    market_comparison = ["gold_price", "oil_price", "usd_rub", "vix", "sp500"]
    fig, ax = plt.subplots(figsize=(14, 6))
    for column in market_comparison:
        if column in market_df.columns:
            ax.plot(market_df.index, normalize_for_plot(market_df[column]), label=column, linewidth=1.4)
    ax.set_title("Normalized comparison: market indicators")
    ax.set_xlabel("Date")
    ax.set_ylabel("Indexed to 100")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    output_name = "normalized_comparison_market.png"
    fig.savefig(figures_dir / output_name, dpi=150)
    plt.close(fig)
    saved.append(output_name)

    macro_comparison = ["gold_price", "usd_rub", "key_rate", "inflation"]
    fig, ax = plt.subplots(figsize=(14, 6))
    for column in macro_comparison:
        if column in merged_levels.columns:
            ax.plot(merged_levels.index, normalize_for_plot(merged_levels[column]), label=column, linewidth=1.4)
    ax.set_title("Normalized comparison: gold_price, usd_rub, key_rate, inflation")
    ax.set_xlabel("Date")
    ax.set_ylabel("Indexed to 100")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    output_name = "normalized_comparison_gold_usd_rub_key_rate_inflation.png"
    fig.savefig(figures_dir / output_name, dpi=150)
    plt.close(fig)
    saved.append(output_name)

    daily_pct_columns = [f"{name}_daily_pct_change" for name in ["gold_price", "oil_price", "usd_rub", "vix", "sp500"]]
    daily_pct_available = [column for column in daily_pct_columns if column in features_df.columns]
    if daily_pct_available:
        corr_df = features_df[daily_pct_available].dropna(how="all").corr()
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(corr_df, cmap="coolwarm", center=0, annot=True, fmt=".2f", ax=ax)
        ax.set_title("Correlation heatmap: daily market pct changes")
        fig.tight_layout()
        output_name = "correlation_heatmap_daily_market_pct_changes.png"
        fig.savefig(figures_dir / output_name, dpi=150)
        plt.close(fig)
        saved.append(output_name)

    market_7d_columns = [f"{name}_pct_change_7d" for name in ["gold_price", "oil_price", "usd_rub", "vix", "sp500"]]
    market_7d_available = [column for column in market_7d_columns if column in features_df.columns]
    if market_7d_available:
        corr_df = features_df[market_7d_available].dropna(how="all").corr()
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(corr_df, cmap="coolwarm", center=0, annot=True, fmt=".2f", ax=ax)
        ax.set_title("Correlation heatmap: 7-day market pct changes")
        fig.tight_layout()
        output_name = "correlation_heatmap_market_7d_pct_changes.png"
        fig.savefig(figures_dir / output_name, dpi=150)
        plt.close(fig)
        saved.append(output_name)

    rolling_pairs = [
        ("gold_price", "oil_price", "rolling_corr_gold_vs_oil.png"),
        ("gold_price", "usd_rub", "rolling_corr_gold_vs_usd_rub.png"),
        ("gold_price", "vix", "rolling_corr_gold_vs_vix.png"),
        ("gold_price", "sp500", "rolling_corr_gold_vs_sp500.png"),
    ]
    for left, right, output_name in rolling_pairs:
        left_col = f"{left}_daily_pct_change"
        right_col = f"{right}_daily_pct_change"
        if left_col not in features_df.columns or right_col not in features_df.columns:
            continue
        rolling_corr = features_df[left_col].rolling(window=90, min_periods=30).corr(features_df[right_col])
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(features_df.index, rolling_corr, linewidth=1.4)
        ax.axhline(0, color="black", linewidth=0.8, alpha=0.5)
        ax.set_title(f"90-day rolling correlation: {left} vs {right}")
        ax.set_xlabel("Date")
        ax.set_ylabel("Correlation")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(figures_dir / output_name, dpi=150)
        plt.close(fig)
        saved.append(output_name)

    lag_rows = []
    gold_base = "gold_price_daily_pct_change"
    if gold_base in features_df.columns:
        for feature in ["oil_price", "usd_rub", "vix", "sp500"]:
            feature_base = f"{feature}_daily_pct_change"
            if feature_base not in features_df.columns:
                continue
            for horizon, suffix in [(1, "1d"), (7, "7d"), (14, "14d")]:
                corr = features_df[gold_base].corr(features_df[feature_base].shift(horizon))
                lag_rows.append({"feature": feature, "horizon": suffix, "correlation": corr})

    if lag_rows:
        lag_corr_df = pd.DataFrame(lag_rows)
        fig, ax = plt.subplots(figsize=(12, 6))
        sns.barplot(data=lag_corr_df, x="feature", y="correlation", hue="horizon", ax=ax)
        ax.set_title("Lag correlation for daily market indicators relative to gold")
        ax.set_xlabel("Feature")
        ax.set_ylabel("Correlation")
        fig.tight_layout()
        output_name = "lag_correlation_daily_market_features.png"
        fig.savefig(figures_dir / output_name, dpi=150)
        plt.close(fig)
        saved.append(output_name)

    if "gold_price" in market_df.columns and not monthly_levels.empty:
        gold_monthly_return = market_df["gold_price"].resample("ME").last().pct_change()
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        comparisons = [
            ("inflation", "gold_monthly_return vs inflation_monthly_change"),
            ("key_rate", "gold_monthly_return vs key_rate_monthly_change"),
        ]
        plotted = False
        for ax, (macro_feature, title) in zip(axes, comparisons):
            if macro_feature not in monthly_levels.columns:
                ax.axis("off")
                continue
            macro_change = monthly_levels[macro_feature].resample("ME").last().diff(1)
            plot_df = pd.concat(
                [
                    gold_monthly_return.rename("gold_monthly_return"),
                    macro_change.rename(f"{macro_feature}_monthly_change"),
                ],
                axis=1,
            ).dropna()
            if plot_df.empty:
                ax.axis("off")
                continue
            sns.regplot(
                data=plot_df,
                x="gold_monthly_return",
                y=f"{macro_feature}_monthly_change",
                scatter_kws={"alpha": 0.7},
                line_kws={"color": "crimson"},
                ax=ax,
            )
            ax.set_title(title)
            plotted = True
        if plotted:
            fig.tight_layout()
            output_name = "monthly_correlation_gold_vs_macro.png"
            fig.savefig(figures_dir / output_name, dpi=150)
            saved.append(output_name)
        plt.close(fig)

    return saved


def build_summary(
    project_root: Path,
    market_metadata: list[dict],
    local_sources: list[dict],
    market_df: pd.DataFrame,
    merged_df: pd.DataFrame,
    features_df: pd.DataFrame,
    figures: list[str],
) -> str:
    daily_market_features = list(market_df.columns)
    monthly_features = sorted(
        {
            feature
            for source in local_sources
            for feature in source["features"]
        }
    )
    all_features = [column for column in merged_df.columns if not column.endswith("_is_original_monthly")]

    daily_pct_columns = [f"{feature}_daily_pct_change" for feature in daily_market_features]
    daily_corr_notes = []
    if all(column in features_df.columns for column in daily_pct_columns):
        corr_matrix = features_df[daily_pct_columns].corr()
        masked = corr_matrix.abs().copy()
        np.fill_diagonal(masked.values, np.nan)
        ranked = masked.stack().sort_values(ascending=False)
        if not ranked.empty:
            left, right = ranked.index[0]
            value = corr_matrix.loc[left, right]
            daily_corr_notes.append(
                f"Самая заметная связь среди daily market pct_change наблюдается между `{left}` и `{right}` с корреляцией около `{value:.2f}`."
            )

    if "gold_price_daily_pct_change" in features_df.columns and "vix_daily_pct_change" in features_df.columns:
        rolling_sample = features_df["gold_price_daily_pct_change"].corr(features_df["vix_daily_pct_change"])
        if pd.notna(rolling_sample):
            daily_corr_notes.append(
                f"Связь `gold_price` и `vix` в daily-изменениях выглядит умеренной и меняющейся во времени; суммарная корреляция на всём периоде около `{rolling_sample:.2f}`."
            )

    if monthly_features:
        daily_corr_notes.append(
            "Показатели `inflation` и `key_rate` анализируются отдельно как monthly/event-based признаки: для них основными производными стали `lag_1m`, `lag_3m`, `lag_6m`, `monthly_change` и `monthly_pct_change`."
        )

    missing_counts = merged_df.isna().sum().sort_values(ascending=False)
    missing_lines = [f"- `{column}`: {int(value)}" for column, value in missing_counts.items()]

    summary_path_lines = "\n".join(
        f"- `{source['file_path']}`: дата `{source['date_column']}`, признаки `{', '.join(source['features'])}`."
        for source in local_sources
    )
    if not summary_path_lines:
        summary_path_lines = "- Локальные monthly/event-based файлы не были найдены."

    figure_lines = "\n".join(f"- `{name}`" for name in figures)

    return f"""# Research Summary

## 1. Цель исследования

На этом этапе мы не обучаем модель, а определяем потенциальные признаки и проверяем, есть ли визуальные и корреляционные зависимости между макроэкономическими индикаторами. Основная цель текущей версии пайплайна — отделить реальные daily market series от monthly/event-based макроэкономических рядов и не смешивать их в одну логику лагов.

## 2. Какие источники данных использованы

Daily market data были загружены через `yfinance` за период `{START_DATE}` - `2025-12-31`:

{chr(10).join(f"- `{meta['ticker']}` -> `{meta['feature_name']}` (источник цены: `{meta['price_source']}`, метод загрузки: `{meta['source_method']}`)." for meta in market_metadata)}

Локальные monthly/event-based источники:

{summary_path_lines}

## 3. Какие признаки вошли в итоговый датасет

Базовые daily market признаки:

{chr(10).join(f"- `{feature}`" for feature in daily_market_features)}

Monthly/event-based макро признаки:

{chr(10).join(f"- `{feature}`" for feature in monthly_features) if monthly_features else "- Нет локальных monthly/event-based признаков."}

## 4. Как данные были приведены к дневной частоте

- Daily market data загружены в исходной торговой дневной частоте через `yfinance` и не были агрегированы из monthly-рядов.
- Monthly macro data не интерполируются, а только приводятся к общей дневной сетке через `forward fill`.
- Общий daily dataset строится на календарном индексе, поэтому рыночные признаки остаются наблюдаемыми только в торговые дни, а выходные и праздники не заполняются искусственно.
- Daily лаги для monthly-признаков больше не используются как основные признаки.

## 5. Какие лаги и изменения были добавлены

- Для daily market features используются `daily_pct_change`, `pct_change_7d`, `pct_change_14d`, а также `lag_1d`, `lag_7d`, `lag_14d`.
- Для monthly macro features используются `lag_1m`, `lag_3m`, `lag_6m`, `monthly_change`, `monthly_pct_change`.
- Такой дизайн отделяет рыночную краткосрочную динамику от редких макрообновлений и лучше соответствует экономическому смыслу рядов.

## 6. Какие зависимости визуально заметны

{chr(10).join(f"- {note}" for note in daily_corr_notes)}

## 7. Какие признаки потенциально можно использовать для будущей ML-модели

- `gold_price`, `oil_price`, `usd_rub`, `vix`, `sp500` как daily market indicators риска, спроса на защитные активы, волатильности и аппетита к риску.
- `inflation` и `key_rate` как макроэкономические признаки более медленного обновления, которые могут работать как regime-level контекст.
- Daily returns и rolling correlations рыночных рядов как кандидаты на признаки раннего предупреждения.
- Monthly changes и month-level lags для макро рядов как признаки фона денежно-кредитной и инфляционной среды.

## 8. Какие ограничения есть у анализа

- Monthly/event-based макро показатели не дают внутримесячной новой информации, даже после переноса на daily index через `forward fill`.
- Рыночные daily ряды содержат пропуски в не-торговые дни, что корректно с точки зрения данных, но требует аккуратной обработки в будущей модели.
- Корреляционные графики отражают совместную динамику, но не доказывают причинность и не означают, что модель уже умеет предсказывать кризисы.
- Анализ ограничен теми локальными макро файлами, которые уже находились в проекте, и тикерами, доступными через `yfinance`.

## Краткий технический отчет

- Итоговый merged dataset покрывает период `{merged_df.index.min().strftime('%Y-%m-%d')}` - `{merged_df.index.max().strftime('%Y-%m-%d')}`.
- В merged dataset строк: `{len(merged_df)}`.
- Итоговые артефакты:
  - `data/processed/macro_daily_market_data.csv`
  - `data/processed/macro_daily_merged.csv`
  - `data/processed/macro_features_with_lags.csv`
- Сохранённые графики:
{figure_lines}
- Остаточные пропуски по столбцам:
{chr(10).join(missing_lines)}
"""


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    processed_dir, figures_dir = ensure_directories(project_root)
    clean_existing_figures(figures_dir)

    market_df, market_metadata = build_market_dataset()
    market_output = processed_dir / "macro_daily_market_data.csv"
    market_df.reset_index().assign(date=lambda df: df["date"].dt.strftime("%Y-%m-%d")).to_csv(market_output, index=False)

    daily_index = pd.date_range(START_DATE, "2025-12-31", freq="D")

    local_sources = build_local_macro_sources(project_root)
    daily_macro_features, monthly_levels = build_monthly_macro_daily(local_sources, daily_index)
    daily_macro_levels = build_monthly_level_frame(monthly_levels, daily_index)

    market_levels_daily = market_df.reindex(daily_index)
    market_levels_daily.index.name = "date"

    merged_df = pd.concat([market_levels_daily, daily_macro_levels], axis=1)
    merged_df.index.name = "date"
    merged_output = processed_dir / "macro_daily_merged.csv"
    merged_df.reset_index().assign(date=lambda df: df["date"].dt.strftime("%Y-%m-%d")).to_csv(merged_output, index=False)

    market_features = build_market_feature_frame(market_df, daily_index)
    features_df = pd.concat([market_features, daily_macro_features], axis=1)
    features_df.index.name = "date"
    features_output = processed_dir / "macro_features_with_lags.csv"
    features_df.reset_index().assign(date=lambda df: df["date"].dt.strftime("%Y-%m-%d")).to_csv(features_output, index=False)

    merged_levels_for_plots = pd.concat([market_levels_daily, daily_macro_levels[monthly_levels.columns] if not monthly_levels.empty else daily_macro_levels], axis=1)
    figures = save_figures(
        market_df=market_df,
        merged_levels=merged_levels_for_plots,
        features_df=features_df,
        monthly_levels=monthly_levels,
        figures_dir=figures_dir,
    )

    summary_text = build_summary(
        project_root=project_root,
        market_metadata=market_metadata,
        local_sources=local_sources,
        market_df=market_df,
        merged_df=merged_df,
        features_df=features_df,
        figures=figures,
    )
    summary_path = project_root / "reports" / "research_summary.md"
    summary_path.write_text(summary_text, encoding="utf-8")

    report = {
        "yfinance_tickers_loaded": [
            {
                "ticker": meta["ticker"],
                "feature_name": meta["feature_name"],
                "price_source": meta["price_source"],
                "source_method": meta["source_method"],
                "rows": meta["rows"],
            }
            for meta in market_metadata
        ],
        "local_files_used": [source["file_path"] for source in local_sources],
        "coverage_start": merged_df.index.min().strftime("%Y-%m-%d"),
        "coverage_end": merged_df.index.max().strftime("%Y-%m-%d"),
        "daily_dataset_rows": len(merged_df),
        "created_features": list(features_df.columns),
        "saved_figures": figures,
        "rewritten_outputs": [
            "data/processed/macro_daily_market_data.csv",
            "data/processed/macro_daily_merged.csv",
            "data/processed/macro_features_with_lags.csv",
            "reports/research_summary.md",
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
