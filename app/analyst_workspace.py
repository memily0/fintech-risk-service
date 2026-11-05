"""Streamlit workspace for ArcShift V1."""

from base64 import b64encode
from datetime import date
from html import escape
import os
from pathlib import Path
from uuid import uuid4

import plotly.graph_objects as go
import streamlit as st

from workspace_client import FixtureClient, POLICY, ROOT, SERIES, SNAPSHOT, STATUSES, UnavailableClient, WARNING_ID, now
from workspace_reports import csv_bytes, json_bytes, pdf_bytes, timestamp


PAGES = (
    'Обзор России', 'История рядов', 'Предупреждения', 'Разбор сигнала', 'Личная проверка',
    'Список наблюдения', 'Отчёты', 'Аккаунт', 'Методология',
)
SCENARIOS = {
    'historical_demo': 'Исторический пример', 'loading': 'Загрузка', 'empty': 'Пустой набор',
    'error': 'Ошибка источника', 'stale': 'Устарело', 'unsupported': 'Горизонт не поддерживается',
    'missing': 'Пропуск данных', 'market_closed': 'Рынок закрыт', 'incomplete_bar': 'Свеча не закрыта',
}
STATES = {
    'loading': ('info', 'Загрузка снимка. Значения появятся после завершения загрузки.'),
    'empty': ('info', 'Нет доступной истории для выбранного набора.'),
    'error': ('error', 'Источник временно недоступен. Повторите проверку позже.'),
    'stale': ('warning', 'Данные устарели. Текущая оценка риска недоступна.'),
    'unsupported': ('warning', 'Выбранный горизонт не поддерживается. Оценка недоступна.'),
    'missing': ('warning', 'Не хватает обязательных наблюдений. Оценка недоступна.'),
    'market_closed': ('info', 'Рынок закрыт по демонстрационному календарю. Свежесть проверяется по последней завершённой сессии.'),
    'incomplete_bar': ('warning', 'Дневная свеча ещё не закрыта. Оценка недоступна.'),
}
CSS = """
<style>
[data-testid="stMainBlockContainer"] {max-width: 76rem; padding-top: 3rem;}
[data-testid="stSidebar"] {border-right: 1px solid #cbd5e1;}
.arc-banner {
    padding: 1.1rem 1.25rem; color: #eaf2ff; background: #14283f;
    border: 1px solid #32516d; border-radius: .8rem; margin-bottom: .5rem;
}
.arc-banner strong {display: block; color: #93ddf3; letter-spacing: .06em; font-size: .82rem;}
.arc-banner p {margin: .35rem 0 0; line-height: 1.55; overflow-wrap: anywhere;}
.arc-card {padding: .9rem; background: #edf5fc; color: #14283f; border-radius: .65rem;
           border: 1px solid #c2d7e9; height: 100%; overflow-wrap: anywhere;}
.arc-card strong {display: block; font-size: 1.55rem; line-height: 1.4;}
.arc-card span {display: block; line-height: 1.5;}
.arc-details {display: grid; grid-template-columns: minmax(8rem, 1fr) 2fr; gap: .55rem 1rem;
              padding: 0; margin: 0;}
.arc-details dt {font-weight: 600;}
.arc-details dd {margin: 0; overflow-wrap: anywhere;}
[data-testid="stText"] {white-space: pre-wrap; overflow-wrap: anywhere;}
[data-testid="stHeading"], [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] {
    overflow-wrap: anywhere;
}
@media (max-width: 820px) {
    [data-testid="stMainBlockContainer"] {padding: 3.4rem 1rem 2rem;}
    [data-testid="stHeading"] h1 {font-size: 2rem;}
    [data-testid="stHeading"] h2 {font-size: 1.45rem;}
    [data-testid="stHorizontalBlock"] {flex-wrap: wrap;}
    [data-testid="stColumn"] {flex-basis: 100% !important; min-width: 0 !important;}
    .arc-details {grid-template-columns: 1fr;}
    .arc-details dd {margin-bottom: .55rem;}
}
</style>
"""


def _go(page):
    st.session_state.arc_page = page


def _refresh():
    st.session_state.arc_refreshed = now()


def _set_account(alias):
    previous = st.session_state.get('arc_alias')
    actor = st.session_state.arc_accounts.get(previous)
    if actor:
        for key in list(st.session_state):
            if key.startswith(f'private:{actor}:'):
                del st.session_state[key]
    st.session_state.arc_alias = alias


def _account():
    st.write('Регистрация в рабочем продукте предусмотрена без кода приглашения. '
             'В этой сборке доступна симуляция регистрации и входа в текущей сессии браузера.')
    if st.session_state.arc_alias:
        st.success(f'Активен аккаунт «{st.session_state.arc_alias}».')
        st.button('Выйти', on_click=_set_account, args=(None,))
        return
    alias = st.selectbox('Демо-аккаунт', list(st.session_state.arc_accounts))
    st.button('Войти в демо', on_click=_set_account, args=(alias,))
    if st.button('Создать демо-аккаунт'):
        alias = f'Демо {len(st.session_state.arc_accounts) + 1}'
        st.session_state.arc_accounts[alias] = uuid4().hex
        _set_account(alias)
        st.rerun()


def _private(client):
    if client.actor:
        st.caption(f'Демо-аккаунт · {st.session_state.arc_alias}')
        return True
    st.info('Войдите в демо-аккаунт, чтобы открыть личный раздел.')
    st.button('Открыть аккаунт', on_click=_go, args=('Аккаунт',))
    return False


def _current_rows(rows):
    return sorted((row for row in rows if row['quality'] != 'superseded'),
                  key=lambda row: row['reference_period'])


def _chart(rows, unit, key):
    current = _current_rows(rows)
    if all(row['value'] is None for row in current):
        st.info('В выбранном периоде нет значений для графика.')
        return
    fig = go.Figure(go.Scatter(
        x=[row['reference_period'] for row in current],
        y=[row['value'] for row in current],
        mode='lines+markers', connectgaps=False, line={'color': '#16748c', 'width': 3},
        hovertemplate='%{x|%d.%m.%Y}<br>%{y}<extra></extra>',
    ))
    fig.update_layout(height=280, margin={'l': 15, 'r': 15, 't': 16, 'b': 38}, yaxis_title=unit)
    fig.update_xaxes(type='date', tickformat='%d.%m', dtick=86_400_000)
    st.plotly_chart(fig, width='stretch', key=key, config={'displayModeBar': False})
    st.caption('Пропуски разрывают линию. Таблица истории доступна с клавиатуры.')


def _overview(data):
    st.write('Ряды России и мировые факторы для контекста. Горизонт демонстрационного сигнала — 30 календарных дней.')
    if not data['series']:
        return
    columns = st.columns(3)
    for column, rows in zip(columns, data['series'].values()):
        row = _current_rows(rows)[-1]
        column.html(
            f'<div class="arc-card"><span>{escape(row["name"])}</span>'
            f'<strong>{row["value"]} {escape(row["unit"])}</strong>'
            f'<span>Период {row["reference_period"]}</span></div>'
        )
    st.subheader('Условная динамика USD/RUB')
    _chart(data['series']['fx'], SERIES['fx'][1], 'overview-chart')
    if data['signal']:
        st.button('Открыть предупреждения', on_click=_go, args=('Предупреждения',))


def _history(data):
    if not data['series']:
        return
    series = st.selectbox('Показатель', list(data['series']), format_func=lambda key: SERIES[key][0])
    rows = data['series'][series]
    _, unit, geography, export = SERIES[series]
    st.caption(f'{geography} · {unit} · ежедневно · {rows[0]["definition_id"]} · {rows[0]["source_id"]}')
    st.caption(f'Календарь {rows[0]["calendar_id"]} · снимок {SNAPSHOT} · '
               f'экспорт {"разрешён" if export else "недоступен"}')
    first = date.fromisoformat(min(row['reference_period'] for row in rows))
    last = date.fromisoformat(max(row['reference_period'] for row in rows))
    selected = st.date_input('Период наблюдения', (first, last), key=f'range-{series}')
    if len(selected) != 2:
        st.info('Выберите начало и конец периода.')
        return
    rows = [row for row in rows if selected[0] <= date.fromisoformat(row['reference_period']) <= selected[1]]
    _chart(rows, unit, 'history-chart')
    if not rows:
        st.info('В выбранном периоде нет наблюдений.')
        return
    st.table([{
        'Период': row['reference_period'],
        'Значение': str(row['value']) if row['value'] is not None else 'Пропуск',
        'Единица': unit, 'Публикация': timestamp(row['published_at']),
        'Получение': timestamp(row['received_at']), 'Ревизия': row['revision_id'],
        'Качество': {'observed': 'Наблюдение', 'missing': 'Пропуск', 'superseded': 'Пересмотрено'}[row['quality']],
    } for row in sorted(rows, key=lambda row: (row['reference_period'], row['revision_id']))])


def _warnings(data, client):
    status = client.review()['status'] if client.actor and data['signal'] else 'new'
    statuses = {'all': 'Все статусы', **STATUSES}
    selected = st.selectbox('Статус проверки', list(statuses), format_func=statuses.get)
    if not data['signal'] or selected not in {'all', status}:
        st.info('По выбранному фильтру предупреждений нет.')
        return
    with st.container(border=True):
        st.subheader('Предупреждение о рыночном стрессе')
        st.caption(WARNING_ID)
        st.write(f'Личный статус · {STATUSES[status]}' if client.actor else 'Для личного статуса войдите в демо.')
        st.button('Разобрать сигнал', on_click=_go, args=('Разбор сигнала',))


def _investigation(signal):
    if not signal:
        st.info('Сигнал для разбора отсутствует.')
        return
    st.subheader(f'Синтетическая оценка · {signal["score"]}')
    st.caption('Шкала оценки без калибровки. Вероятность события и действующий сигнал недоступны.')
    details = {
        'Задача / определение цели': f'{signal["task_id"]} / {signal["target_definition_id"]}',
        'География / частота': f'{signal["geography"]} / {signal["frequency"]}',
        'Горизонт': f'{signal["horizon_value"]} календарных дней',
        'Снимки данных и признаков': f'{signal["data_snapshot_id"]} / {signal["feature_snapshot_id"]}',
        'Модель / валидация': f'{signal["model_version"]} / нет',
        'Дата сигнала / формирования': f'{timestamp(signal["forecast_origin"])} / {timestamp(signal["generated_at"])}',
        'Политика / статус': f'{signal["policy_id"]} / {signal["validity_status"]}',
    }
    st.html('<dl class="arc-details">' + ''.join(
        f'<dt>{escape(label)}</dt><dd>{escape(value)}</dd>' for label, value in details.items()
    ) + '</dl>')
    st.info('Вклады признаков отсутствуют. Для допустимой логистической модели вклады выражаются в logit units.')
    st.button('Перейти к личной проверке', on_click=_go, args=('Личная проверка',))


def _review(client, signal):
    if not _private(client):
        return
    if not signal:
        st.info('Для проверки нужен доступный сигнал.')
        return
    current = client.review()
    with st.form(f'private:{client.actor}:review'):
        status = st.selectbox('Решение', list(STATUSES), index=list(STATUSES).index(current['status']),
                              format_func=STATUSES.get, key=f'private:{client.actor}:status')
        note = st.text_area('Личная заметка', current['note'], max_chars=1500, key=f'private:{client.actor}:note',
                            help='Используйте вымышленные данные для проверки демо.')
        if st.form_submit_button('Сохранить проверку'):
            try:
                client.save_review(status, note)
            except ValueError as error:
                st.error(str(error))
            else:
                current = client.review()
                st.success('Личная проверка сохранена.')
    st.caption(f'{WARNING_ID} · обновлено {timestamp(current["updated_at"])}')
    st.caption('Статус отражает решение аналитика. Качество модели оценивается отдельно.')
    st.button('Перейти к отчётам', on_click=_go, args=('Отчёты',))


def _watchlist(client):
    if not _private(client):
        return
    saved = client.watchlist()
    st.write('Выберите ряды для наблюдения.')
    with st.form(f'private:{client.actor}:watchlist'):
        selected = [series_id for series_id, series in SERIES.items()
                    if st.checkbox(series[0], value=series_id in saved,
                                   key=f'private:{client.actor}:watch:{series_id}')]
        if st.form_submit_button('Сохранить список'):
            client.save_watchlist(selected)
            st.success('Список сохранён.')


def _download_links(report):
    files = [
        ('CSV', 'csv', 'text/csv', csv_bytes(report)),
        ('JSON', 'json', 'application/json', json_bytes(report)),
    ]
    try:
        pdf = pdf_bytes(report, STATUSES[report['review']['status']])
    except (ImportError, OSError) as error:
        st.error(f'Выгрузка PDF недоступна. {error}')
    else:
        files.insert(0, ('PDF', 'pdf', 'application/pdf', pdf))
    # Inline file bytes are sent to the authorized browser session only.
    links = ' '.join(
        f'<a download="arcshift-{escape(report["id"])}.{extension}" '
        f'href="data:{mime};base64,{b64encode(data).decode("ascii")}">Скачать {label}</a>'
        for label, extension, mime, data in files
    )
    st.iframe(
        '<html lang="ru"><style>body{margin:0;font:1rem system-ui;display:flex;flex-wrap:wrap;gap:.5rem}'
        'a{padding:.35rem .55rem;background:#e7f0fb;color:#124475;border-radius:.3rem}'
        'a:focus-visible{outline:2px solid #0e517d;outline-offset:-2px}</style>'
        f'<body>{links}</body></html>',
        tab_index=0, alt='Выгрузки выбранного отчёта',
    )


def _reports(client, signal):
    if not _private(client):
        return
    st.write('Отчёт сохраняет версию снимка и вашу проверку на момент создания. Brent доступен только для просмотра.')
    report_key = f'private:{client.actor}:report'
    if st.button('Создать отчёт', disabled=not signal):
        st.session_state[report_key] = client.create_report()
    ids = client.report_ids()
    if not ids:
        st.info('Сохранённых отчётов пока нет.')
        return
    report = client.report(st.selectbox('Сохранённый отчёт', ids, key=report_key))
    st.caption(f'Снимок {report["snapshot_id"]} · сформирован {timestamp(report["created_at"])}')
    st.write(f'Статус в отчёте · {STATUSES[report["review"]["status"]]}')
    if report['review']['note']:
        st.text(report['review']['note'])
    _download_links(report)


def _methodology():
    st.subheader('Границы задачи')
    st.write('Демо показывает условный прокси будущего рыночного стресса для России '
             'на 30 календарных дней. Глобальные ряды служат контекстом. '
             'Производственное определение таргета, покрытие и допустимые горизонты ожидают допуска.')
    st.subheader('История качества')
    st.info('OOS-оценка и её фолды недоступны.')
    st.write('Архивная fitted-история относится к обучающей выборке. Рабочий прогноз требует отдельного допуска. '
             'Калибровка, ошибки рабочего прогноза и экономический эффект пока не подтверждены.')
    st.caption(f'Демонстрационная политика {POLICY}')


def render_workspace():
    st.set_page_config(page_title='ArcShift · Рабочее место аналитика', layout='wide')
    st.html(CSS)
    if 'arc_accounts' not in st.session_state:
        st.session_state.arc_accounts = {alias: uuid4().hex for alias in ('Демо A', 'Демо B')}
        st.session_state.arc_alias = None
        _refresh()
    with st.sidebar:
        st.markdown('### ArcShift V1')
        mode = st.selectbox('Режим данных', ('Синтетическое демо', 'Рабочий режим'), on_change=_refresh)
        page = st.radio('Раздел', PAGES, key='arc_page')
        demo = mode == 'Синтетическое демо'
        scenario = st.selectbox('Сценарий данных', list(SCENARIOS), format_func=SCENARIOS.get,
                                on_change=_refresh) if demo else None
        st.button('Обновить проверку', on_click=_refresh)
        if demo:
            st.caption(f'Сессия · {st.session_state.arc_alias or "гость"}')

    actor = st.session_state.arc_accounts.get(st.session_state.arc_alias)
    store = Path(os.getenv('ARCSHIFT_DEMO_DB', str(ROOT / '.cache/arcshift-ui/demo.sqlite3')))
    client = FixtureClient(store, actor) if demo else UnavailableClient()
    data = client.workspace(scenario, st.session_state.arc_refreshed)
    st.title(page)
    if data['state'] == 'unavailable':
        st.warning('Рабочий режим недоступен. Требуются допуск данных и модели и подключение API I03/I04.')
        st.caption(f'Проверка интерфейса · {timestamp(data["refreshed_at"])}')
        if page == 'Методология':
            _methodology()
        return
    st.html('<div class="arc-banner"><strong>СИНТЕТИЧЕСКИЕ ДАННЫЕ · ДЕМО</strong>'
            '<p>Россия · рабочее место аналитика. Текущая оценка риска недоступна.</p></div>')
    st.caption(f'Информация на {timestamp(data["information_as_of"])} · '
               f'проверка интерфейса {timestamp(data["refreshed_at"])}')
    if data['state'] in STATES:
        severity, message = STATES[data['state']]
        getattr(st, severity)(message)
    else:
        st.caption(f'Исторический пример · снимок {SNAPSHOT} · набор {data["fixture_version"]}')
    signal = data['signal']
    views = {
        'Обзор России': (_overview, (data,)), 'История рядов': (_history, (data,)),
        'Предупреждения': (_warnings, (data, client)), 'Разбор сигнала': (_investigation, (signal,)),
        'Личная проверка': (_review, (client, signal)), 'Список наблюдения': (_watchlist, (client,)),
        'Отчёты': (_reports, (client, signal)), 'Аккаунт': (_account, ()), 'Методология': (_methodology, ()),
    }
    view, args = views[page]
    view(*args)
