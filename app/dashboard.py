from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Дашборд рыночного риска",
    layout="wide",
)


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "final_dataset.csv"
CHART_BG = "#0e1117"
CHART_GRID = "rgba(255,255,255,0.12)"

CRISIS_PERIODS = {
    "Весь период": None,
    "Валютный стресс 2014": ("2014-11-01", "2015-03-31"),
    "COVID-19 2020": ("2020-02-15", "2020-08-31"),
    "Рыночный стресс 2022": ("2022-02-01", "2022-12-31"),
    "Свой диапазон": None,
}
SCALE_ABSOLUTE = "Абсолютные значения"
SCALE_INDEXED = "Индекс, старт = 100"
SCALE_ZSCORE = "Z-score"
SCALE_MODES = [SCALE_ABSOLUTE, SCALE_INDEXED, SCALE_ZSCORE]

DEFAULT_INDICATORS = ["usd_rub", "eur_rub", "imoex", "brent", "vix", "sp500"]
KPI_COLUMNS = [
    "usd_rub",
    "eur_rub",
    "imoex",
    "vix",
    "brent",
    "gold",
    "sp500",
    "key_rate",
    "inflation",
    "real_key_rate",
    "ofz_10y",
    "ofz_spread_10_2",
]
LABEL_TO_COL = {
    "USD/RUB": "usd_rub",
    "EUR/RUB": "eur_rub",
    "IMOEX": "imoex",
    "Brent": "brent",
    "VIX": "vix",
    "S&P500": "sp500",
    "Золото": "gold",
    "Ключевая ставка": "key_rate",
    "Инфляция": "inflation",
    "Реальная ключевая ставка": "real_key_rate",
    "ОФЗ 1 год": "ofz_1y",
    "ОФЗ 2 года": "ofz_2y",
    "ОФЗ 5 лет": "ofz_5y",
    "ОФЗ 10 лет": "ofz_10y",
    "Спред ОФЗ 10–2 года": "ofz_spread_10_2",
    "Волатильность USD/RUB": "usd_volatility",
    "Волатильность IMOEX": "imoex_volatility",
    "Просадка IMOEX": "imoex_drawdown",
    "IMOEX z-score": "imoex_zscore",
}
COL_TO_LABEL = {column: label for label, column in LABEL_TO_COL.items()}
LABELS = COL_TO_LABEL
COLOR_MAP = {
    "usd_rub": "#60a5fa",
    "eur_rub": "#2dd4bf",
    "imoex": "#f59e0b",
    "vix": "#fb7185",
    "brent": "#a3e635",
    "gold": "#facc15",
    "sp500": "#c084fc",
    "key_rate": "#34d399",
    "inflation": "#f87171",
    "real_key_rate": "#38bdf8",
    "ofz_1y": "#93c5fd",
    "ofz_2y": "#22d3ee",
    "ofz_5y": "#c084fc",
    "ofz_10y": "#fb923c",
    "ofz_spread_10_2": "#f472b6",
    "usd_volatility": "#60a5fa",
    "imoex_volatility": "#fbbf24",
    "imoex_drawdown": "#f43f5e",
    "imoex_zscore": "#fdba74",
}
LABEL_COLOR_MAP = {label: COLOR_MAP[column] for column, label in COL_TO_LABEL.items() if column in COLOR_MAP}


@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    print(f"[dashboard] raw data shape={df.shape}")
    print(f"[dashboard] raw data columns={list(df.columns)}")
    if "date" not in df.columns:
        raise ValueError("Column 'date' is required in data/final_dataset.csv")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for column in df.columns:
        if column != "date":
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    print(f"[dashboard] prepared data shape={df.shape}")
    print(f"[dashboard] prepared data dtypes={df.dtypes.astype(str).to_dict()}")
    return df


def fmt_label(column: str) -> str:
    return LABELS.get(column, column)


def labels_for_columns(columns: list[str]) -> list[str]:
    return [fmt_label(column) for column in columns]


def columns_for_labels(labels: list[str]) -> list[str]:
    return [LABEL_TO_COL[label] for label in labels if label in LABEL_TO_COL]


def missing_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column not in df.columns]


def available_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column in df.columns]


def show_missing_warning(df: pd.DataFrame, columns: list[str], context: str) -> None:
    missing = missing_columns(df, columns)
    if missing:
        st.warning(
            f"{context}: пропущены колонки {', '.join(fmt_label(column) for column in missing)}. "
            "Соответствующие элементы пропущены."
        )


def line_chart(
    df: pd.DataFrame,
    columns: list[str],
    title: str,
    y_title: str = "Значение",
    height: int = 450,
) -> go.Figure | None:
    plot_columns = available_columns(df, columns)
    if not plot_columns:
        return None

    chart_df = df[["date", *plot_columns]].copy()
    chart_df = chart_df.dropna(subset=plot_columns, how="all")
    if chart_df.empty:
        return None

    plot_df = chart_df.melt(
        id_vars="date",
        value_vars=plot_columns,
        var_name="indicator",
        value_name="value",
    )
    plot_df = plot_df.dropna(subset=["value"])
    if plot_df.empty:
        return None
    plot_df["indicator"] = plot_df["indicator"].map(COL_TO_LABEL).fillna(plot_df["indicator"])

    fig = px.line(
        plot_df,
        x="date",
        y="value",
        color="indicator",
        color_discrete_map=LABEL_COLOR_MAP,
        labels={"date": "Дата", "value": y_title, "indicator": "Индикатор"},
        title=title,
        template="plotly_dark",
        render_mode="svg",
    )
    fig.update_traces(line=dict(width=2.5), connectgaps=False)
    fig.update_layout(
        template="plotly_dark",
        height=height,
        hovermode="x unified",
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        font=dict(color="#F5F5F5"),
        legend_title_text="Индикатор",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=20, r=20, t=70, b=20),
        xaxis=dict(showgrid=True, gridcolor=CHART_GRID, zeroline=False),
        yaxis=dict(title=y_title, showgrid=True, gridcolor=CHART_GRID, zeroline=False),
    )
    return fig


def normalized_chart(df: pd.DataFrame, columns: list[str], title: str) -> go.Figure | None:
    plot_columns = available_columns(df, columns)
    if not plot_columns:
        return None

    normalized = pd.DataFrame({"date": df["date"]})
    valid_columns = []
    skipped_columns = []
    for column in plot_columns:
        series = df[column].dropna()
        if series.empty:
            skipped_columns.append(column)
            continue
        base_value = float(series.iloc[0])
        if pd.isna(base_value) or base_value == 0:
            skipped_columns.append(column)
        else:
            normalized[column] = df[column] / base_value * 100
            valid_columns.append(column)

    if skipped_columns:
        st.warning(
            "Нормализация пропущена для рядов без стартового значения: "
            + ", ".join(fmt_label(column) for column in skipped_columns)
        )
    return line_chart(normalized, valid_columns, title, y_title="Индекс, старт = 100")


def zscore_chart(df: pd.DataFrame, columns: list[str], title: str) -> go.Figure | None:
    plot_columns = available_columns(df, columns)
    if not plot_columns:
        return None

    scaled = pd.DataFrame({"date": df["date"]})
    valid_columns = []
    skipped_columns = []
    for column in plot_columns:
        series = df[column]
        std = series.std(skipna=True)
        if pd.isna(std) or std == 0:
            skipped_columns.append(column)
            continue
        scaled[column] = (series - series.mean(skipna=True)) / std
        valid_columns.append(column)

    if skipped_columns:
        st.warning(
            "Z-score пропущен для рядов без вариативности: "
            + ", ".join(fmt_label(column) for column in skipped_columns)
        )
    return line_chart(scaled, valid_columns, title, y_title="Z-score")


def scaled_line_chart(df: pd.DataFrame, columns: list[str], title: str, scale_mode: str) -> go.Figure | None:
    if scale_mode == SCALE_INDEXED:
        return normalized_chart(df, columns, f"{title} ({SCALE_INDEXED.lower()})")
    if scale_mode == SCALE_ZSCORE:
        return zscore_chart(df, columns, f"{title} (z-score)")
    return line_chart(df, columns, f"{title} ({SCALE_ABSOLUTE.lower()})", y_title="Значение")


def get_delta_style(indicator: str, delta: float) -> tuple[str, str]:
    risk_up = {"usd_rub", "eur_rub", "vix", "inflation", "key_rate", "ofz_10y", "real_key_rate"}
    good_up = {"imoex", "sp500"}
    if pd.isna(delta) or abs(delta) < 1e-12:
        return "→", "neutral"
    if indicator in risk_up:
        return ("↑", "bad") if delta > 0 else ("↓", "good")
    if indicator in good_up:
        return ("↑", "good") if delta > 0 else ("↓", "bad")
    return ("↑" if delta > 0 else "↓"), "neutral"


def latest_value_with_30d_change(df: pd.DataFrame, column: str) -> tuple[str, str, str]:
    if column not in df.columns:
        return "n/a", "→ за 30 дней: н/д", "neutral"

    series_df = df[["date", column]].dropna()
    if series_df.empty:
        return "n/a", "→ за 30 дней: н/д", "neutral"

    latest_row = series_df.iloc[-1]
    latest_value = latest_row[column]
    latest_date = latest_row["date"]
    value_text = f"{latest_value:,.2f}"

    past_df = series_df[series_df["date"] <= latest_date - pd.Timedelta(days=30)]
    if past_df.empty:
        return value_text, "→ за 30 дней: н/д", "neutral"

    past_value = past_df.iloc[-1][column]
    if pd.isna(past_value):
        return value_text, "→ за 30 дней: н/д", "neutral"

    delta = latest_value - past_value
    arrow, style = get_delta_style(column, delta)
    if abs(past_value) > 1e-12:
        delta_pct = delta / abs(past_value) * 100
        delta_text = f"{arrow} за 30 дней: {delta:+,.2f} ({delta_pct:+.1f}%)"
    else:
        delta_text = f"{arrow} за 30 дней: {delta:+,.2f}"
    return value_text, delta_text, style


def render_kpi_card(label: str, value_text: str, delta_text: str, style: str) -> str:
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value_text}</div>
        <div class="kpi-delta {style}">{delta_text}</div>
    </div>
    """


def rolling_corr(df: pd.DataFrame, left: str, right: str, window: int) -> pd.DataFrame | None:
    if left not in df.columns or right not in df.columns:
        return None
    pair_df = df[["date", left, right]].copy()
    pair_df["correlation"] = pair_df[left].rolling(window=window, min_periods=max(5, window // 2)).corr(pair_df[right])
    pair_df = pair_df.dropna(subset=["correlation"])
    return pair_df


def zscore(series: pd.Series) -> pd.Series:
    std = series.std(skipna=True)
    if pd.isna(std) or std == 0:
        return pd.Series(np.nan, index=series.index)
    return (series - series.mean(skipna=True)) / std


def build_composite_stress_index(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    components: dict[str, pd.Series] = {}

    if "vix" in df.columns:
        components["Z-score VIX"] = zscore(df["vix"])
    if "usd_volatility" in df.columns:
        components["Z-score волатильности USD/RUB"] = zscore(df["usd_volatility"])
    if "imoex_volatility" in df.columns:
        components["Z-score волатильности IMOEX"] = zscore(df["imoex_volatility"])
    if "imoex_drawdown" in df.columns:
        components["Z-score просадки IMOEX"] = zscore(df["imoex_drawdown"].abs())
    if "ofz_spread_10_2" in df.columns:
        components["Z-score инверсии спреда ОФЗ"] = zscore(-df["ofz_spread_10_2"])

    result = pd.DataFrame({"date": df["date"]})
    for name, series in components.items():
        result[name] = series

    component_columns = [column for column in result.columns if column != "date"]
    if component_columns:
        result["stress_index"] = result[component_columns].mean(axis=1, skipna=True)
    else:
        result["stress_index"] = np.nan
    return result, component_columns


def show_chart_or_info(fig: go.Figure | None, empty_message: str) -> None:
    if fig is None:
        st.info(empty_message)
    else:
        st.plotly_chart(fig, width="stretch", theme=None)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stToolbar"] {
            display: none;
        }
        .kpi-card {
            padding: 0.35rem 0 0.7rem 0;
        }
        .kpi-label {
            color: #f5f5f5;
            font-size: 0.92rem;
            font-weight: 650;
            margin-bottom: 0.2rem;
        }
        .kpi-value {
            color: #ffffff;
            font-size: 2.05rem;
            font-weight: 700;
            line-height: 1.15;
            margin-bottom: 0.32rem;
        }
        .kpi-delta {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.18rem 0.48rem;
            font-size: 0.84rem;
            font-weight: 650;
            line-height: 1.15;
        }
        .kpi-delta.good {
            color: #86efac;
            background: rgba(34, 197, 94, 0.18);
        }
        .kpi-delta.bad {
            color: #fca5a5;
            background: rgba(239, 68, 68, 0.18);
        }
        .kpi-delta.neutral {
            color: #d1d5db;
            background: rgba(148, 163, 184, 0.18);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    df = load_data()
    inject_styles()

    st.title("Дашборд рыночного риска")
    st.caption("Оперативный мониторинг рыночных индикаторов, стресс-метрик и доходностей ОФЗ.")

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()

    st.sidebar.header("Фильтры")
    regime = st.sidebar.selectbox("Рыночный режим", list(CRISIS_PERIODS.keys()), index=0)
    rolling_window = st.sidebar.selectbox("Окно rolling", [7, 14, 30, 60, 90], index=2)
    scale_mode = st.sidebar.selectbox("Режим первого графика", SCALE_MODES, index=0)

    numeric_columns = [column for column in df.columns if column != "date" and pd.api.types.is_numeric_dtype(df[column])]
    indicator_options = labels_for_columns(numeric_columns)
    indicator_default_cols = [column for column in DEFAULT_INDICATORS if column in numeric_columns] or numeric_columns[:6]
    indicator_default = labels_for_columns(indicator_default_cols)
    selected_labels = st.sidebar.multiselect(
        "Основные индикаторы",
        options=indicator_options,
        default=indicator_default,
    )
    selected_cols = columns_for_labels(selected_labels)

    if regime != "Свой диапазон" and CRISIS_PERIODS[regime] is not None:
        start_default, end_default = CRISIS_PERIODS[regime]
        start_date = pd.to_datetime(start_default).date()
        end_date = pd.to_datetime(end_default).date()
    else:
        start_date = min_date
        end_date = max_date

    selected_range = st.sidebar.date_input(
        "Диапазон дат",
        value=(start_date, end_date),
        min_value=min_date,
        max_value=max_date,
    )

    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        custom_start, custom_end = selected_range
    else:
        custom_start, custom_end = start_date, end_date

    filter_start = pd.to_datetime(custom_start)
    filter_end = pd.to_datetime(custom_end)
    filtered_df = df[(df["date"] >= filter_start) & (df["date"] <= filter_end)].copy()

    if filtered_df.empty:
        st.error("После фильтрации не осталось данных. Измените диапазон дат.")
        return

    show_missing_warning(df, KPI_COLUMNS, "KPI блок")

    st.subheader("Последний снимок рынка")
    kpi_columns = st.columns(4)
    for idx, column in enumerate(KPI_COLUMNS):
        value_text, delta_text, delta_style = latest_value_with_30d_change(filtered_df, column)
        kpi_columns[idx % 4].markdown(
            render_kpi_card(fmt_label(column), value_text, delta_text, delta_style),
            unsafe_allow_html=True,
        )

    tabs = st.tabs(
        [
            "Обзор рынка",
            "Индикаторы стресса",
            "Ставки и ОФЗ",
            "Корреляции",
            "Качество данных",
        ]
    )

    with tabs[0]:
        st.markdown("Показывает динамику выбранных индикаторов за фильтрованный период и помогает быстро увидеть направление рынка.")
        show_missing_warning(filtered_df, selected_cols, "Обзор рынка")
        show_chart_or_info(
            scaled_line_chart(filtered_df, selected_cols, "Динамика выбранных индикаторов", scale_mode),
            "Нет доступных данных для выбранных индикаторов.",
        )
        if scale_mode == SCALE_ABSOLUTE:
            st.caption(
                "В режиме абсолютных значений показатели с маленьким масштабом, например VIX или USD/RUB, "
                "могут выглядеть «прижатыми» на фоне крупных индексов. Для сравнения относительной динамики "
                "используйте нормализацию к 100 или Z-score."
            )

        show_chart_or_info(
            normalized_chart(filtered_df, selected_cols, "Нормализованное сравнение выбранных индикаторов"),
            "Нельзя построить нормализованное сравнение для выбранных рядов.",
        )
        st.caption("Нормализация к 100 позволяет сравнить относительное движение рядов с разными масштабами.")

        show_chart_or_info(
            line_chart(filtered_df, ["usd_rub", "eur_rub"], "USD/RUB и EUR/RUB", y_title="Курс"),
            "Недостаточно данных для валютного блока.",
        )
        st.caption("Рост пары означает ослабление рубля, снижение означает укрепление рубля.")

        show_chart_or_info(
            line_chart(filtered_df, ["imoex", "sp500"], "IMOEX и S&P500", y_title="Значение индекса"),
            "Недостаточно данных для сравнения индексов.",
        )
        st.caption("График нужен для сопоставления локального российского рынка и глобального риск-аппетита.")

    with tabs[1]:
        show_missing_warning(
            filtered_df,
            ["vix", "usd_volatility", "imoex_volatility", "imoex_drawdown", "imoex_zscore", "ofz_spread_10_2"],
            "Индикаторы стресса",
        )

        stress_texts = {
            "vix": "VIX показывает уровень глобальной волатильности и неприятия риска.",
            "usd_volatility": "Волатильность отражает нестабильность курса USD/RUB и локальное напряжение на валютном рынке.",
            "imoex_volatility": "Волатильность IMOEX показывает, насколько нервным стал российский рынок акций.",
            "imoex_drawdown": "Просадка показывает падение индекса от исторического максимума.",
            "imoex_zscore": "Z-score показывает, насколько текущее значение IMOEX отклоняется от своей исторической нормы.",
            "ofz_spread_10_2": "Спред ОФЗ характеризует форму кривой доходности и ожидания рынка по ставкам и риску.",
        }

        for column in ["vix", "usd_volatility", "imoex_volatility", "imoex_drawdown", "imoex_zscore", "ofz_spread_10_2"]:
            st.markdown(stress_texts[column])
            show_chart_or_info(
                line_chart(filtered_df, [column], f"{fmt_label(column)}: динамика"),
                f"Нет доступных данных для {fmt_label(column)}.",
            )

    with tabs[2]:
        st.markdown("Ключевая ставка и инфляция помогают оценить жесткость денежно-кредитной политики, а реальная ключевая ставка показывает ее реальную жесткость.")
        show_chart_or_info(
            line_chart(filtered_df, ["key_rate", "inflation", "real_key_rate"], "Ставка, инфляция и реальная ключевая ставка", y_title="Проценты"),
            "Недостаточно данных для блока ставок и инфляции.",
        )

        st.markdown("Кривая ОФЗ показывает ожидания рынка по ставкам, премии за риск и изменение формы срочной структуры.")
        show_chart_or_info(
            line_chart(filtered_df, ["ofz_1y", "ofz_2y", "ofz_5y", "ofz_10y"], "Доходности ОФЗ по срокам", y_title="Доходность"),
            "Недостаточно данных для графика доходностей ОФЗ.",
        )

        show_chart_or_info(
            line_chart(filtered_df, ["ofz_spread_10_2"], "Спред ОФЗ 10–2 года", y_title="Спред"),
            "Нет данных для спреда ОФЗ 10–2 года.",
        )

        curve_columns = ["ofz_1y", "ofz_2y", "ofz_5y", "ofz_10y"]
        curve_available = available_columns(filtered_df, curve_columns)
        latest_curve = filtered_df[["date", *curve_available]].dropna(how="all")
        if len(curve_available) == len(curve_columns) and not latest_curve.empty:
            last_row = latest_curve.dropna(subset=curve_columns, how="any").tail(1)
            if not last_row.empty:
                curve_fig = go.Figure(
                    data=[
                        go.Scatter(
                            x=["1Y", "2Y", "5Y", "10Y"],
                            y=[last_row.iloc[0][column] for column in curve_columns],
                            mode="lines+markers",
                            line=dict(color="#ea580c", width=3),
                            marker=dict(size=10),
                        )
                    ]
                )
                curve_fig.update_layout(
                    template="plotly_dark",
                    title=f"Срез кривой доходности на {last_row.iloc[0]['date'].date()}",
                    xaxis_title="Срок",
                    yaxis_title="Доходность",
                    height=380,
                    paper_bgcolor=CHART_BG,
                    plot_bgcolor=CHART_BG,
                    font=dict(color="#F5F5F5"),
                    margin=dict(l=20, r=20, t=60, b=20),
                )
                st.plotly_chart(curve_fig, width="stretch", theme=None)
            else:
                st.info("Для среза кривой доходности нет полной последней точки по всем срокам.")
        else:
            st.info("Для среза кривой доходности нужны колонки ОФЗ 1 год, 2 года, 5 лет и 10 лет.")

    with tabs[3]:
        st.markdown("Тепловая карта показывает общую взаимосвязь признаков за выбранный период.")
        corr_options = st.multiselect(
            "Признаки для корреляции",
            options=indicator_options,
            default=selected_labels if selected_labels else labels_for_columns(numeric_columns[:6]),
            key="corr_features",
        )
        corr_columns = available_columns(filtered_df, columns_for_labels(corr_options))
        if len(corr_columns) >= 2:
            corr_df = filtered_df[corr_columns].corr(numeric_only=True)
            corr_df = corr_df.rename(index=COL_TO_LABEL, columns=COL_TO_LABEL)
            heatmap = px.imshow(
                corr_df,
                text_auto=".2f",
                aspect="auto",
                color_continuous_scale="RdBu_r",
                zmin=-1,
                zmax=1,
                title="Корреляционная матрица",
                template="plotly_dark",
            )
            heatmap.update_layout(
                height=560,
                paper_bgcolor=CHART_BG,
                plot_bgcolor=CHART_BG,
                font=dict(color="#F5F5F5"),
                margin=dict(l=20, r=20, t=60, b=20),
            )
            st.plotly_chart(heatmap, width="stretch", theme=None)
        else:
            st.info("Для корреляционной матрицы выберите хотя бы два числовых признака.")

        st.markdown("Скользящая корреляция показывает, как связь между двумя рынками менялась во времени.")
        pairs = [
            ("usd_rub", "brent", "USD/RUB и Brent"),
            ("imoex", "brent", "IMOEX и Brent"),
            ("imoex", "vix", "IMOEX и VIX"),
            ("usd_rub", "vix", "USD/RUB и VIX"),
        ]
        for left, right, title in pairs:
            pair_df = rolling_corr(filtered_df, left, right, rolling_window)
            if pair_df is None or pair_df.empty:
                st.info(f"Нет данных для скользящей корреляции: {title}.")
                continue
            fig = px.line(
                pair_df,
                x="date",
                y="correlation",
                title=f"{title}: скользящая корреляция ({rolling_window} дн.)",
                labels={"date": "Дата", "correlation": "Корреляция"},
                template="plotly_dark",
                render_mode="svg",
            )
            fig.add_hline(y=0, line_dash="dash", line_color="#64748b")
            fig.update_traces(line=dict(width=2.5, color="#60a5fa"))
            fig.update_layout(
                height=330,
                hovermode="x unified",
                paper_bgcolor=CHART_BG,
                plot_bgcolor=CHART_BG,
                font=dict(color="#F5F5F5"),
                margin=dict(l=20, r=20, t=60, b=20),
                xaxis=dict(showgrid=True, gridcolor=CHART_GRID, zeroline=False),
                yaxis=dict(showgrid=True, gridcolor=CHART_GRID, zeroline=False),
            )
            st.plotly_chart(fig, width="stretch", theme=None)

    with tabs[4]:
        st.markdown("Проверка качества данных помогает быстро понять покрытие, пропуски и доступность признаков.")
        shape_col, date_col = st.columns(2)
        shape_col.metric("Строки x колонки", f"{filtered_df.shape[0]} x {filtered_df.shape[1]}")
        date_col.metric("Диапазон дат", f"{filtered_df['date'].min().date()} -> {filtered_df['date'].max().date()}")

        missing_table = filtered_df.isna().sum().reset_index()
        missing_table.columns = ["Колонка", "Пропуски"]
        missing_table["Доля пропусков"] = (missing_table["Пропуски"] / len(filtered_df)).round(4)
        st.dataframe(missing_table.sort_values("Пропуски", ascending=False), width="stretch", hide_index=True)

        st.markdown("Последние 20 строк")
        st.dataframe(filtered_df.tail(20), width="stretch")

        st.markdown("Доступные колонки")
        st.dataframe(pd.DataFrame({"Колонка": filtered_df.columns}), width="stretch", hide_index=True)

        with st.expander("Отладочные проверки данных"):
            debug_cols = available_columns(filtered_df, selected_cols)
            st.write("Размер полного датасета:", df.shape)
            st.write("Размер после фильтра:", filtered_df.shape)
            st.write("Выбранные подписи:", selected_labels)
            st.write("Выбранные колонки:", debug_cols)
            st.write("Типы данных:")
            st.dataframe(
                pd.DataFrame({"Колонка": df.columns, "Тип": [str(df[column].dtype) for column in df.columns]}),
                width="stretch",
                hide_index=True,
            )

            if debug_cols:
                selected_debug_df = filtered_df[["date", *debug_cols]].copy()
                st.write("Первые строки выбранных колонок")
                st.dataframe(selected_debug_df.head(), width="stretch", hide_index=True)
                st.write("Последние строки выбранных колонок")
                st.dataframe(selected_debug_df.tail(), width="stretch", hide_index=True)

                selected_missing = pd.DataFrame(
                    {
                        "Колонка": debug_cols,
                        "Доля пропусков, %": [(filtered_df[column].isna().mean() * 100).round(2) for column in debug_cols],
                    }
                )
                st.write("Доля пропусков по выбранным колонкам")
                st.dataframe(selected_missing, width="stretch", hide_index=True)

                selected_minmax = filtered_df[debug_cols].agg(["min", "max"]).T.reset_index()
                selected_minmax.columns = ["Колонка", "Минимум", "Максимум"]
                st.write("Минимум и максимум по выбранным колонкам")
                st.dataframe(selected_minmax, width="stretch", hide_index=True)
            else:
                st.warning("Не выбраны доступные числовые колонки для отладочного просмотра.")


if __name__ == "__main__":
    main()
