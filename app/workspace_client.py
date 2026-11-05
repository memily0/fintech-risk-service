"""Offline client for the ArcShift analyst workspace."""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'product_build/arcshift_v1/fixtures/ui_scenarios.json'
SNAPSHOT = 'synthetic-ui-001'
POLICY = 'synthetic-warning-v1'
WARNING_ID = f'{SNAPSHOT}:{POLICY}'
AS_OF = '2026-11-05T08:00:00+03:00'
REPORT_OBSERVATION_FIELDS = (
    'series_id', 'name', 'unit', 'geography', 'frequency', 'definition_id', 'source_id',
    'calendar_id', 'reference_period', 'value', 'published_at', 'received_at',
    'revision_id', 'snapshot_id', 'quality', 'synthetic',
)
STATUSES = {
    'new': 'Новое', 'acknowledged': 'Принято', 'in_review': 'В проверке',
    'closed': 'Закрыто', 'dismissed': 'Отклонено',
}
SERIES = {
    'fx': ('USD/RUB · условный обменный курс', '₽ / USD', 'Россия', True),
    'equity': ('Условный индекс российского рынка акций с длинным названием', 'пункты', 'Россия', True),
    'global': ('Brent · условная цена', 'USD / баррель', 'Мировой контекст', False),
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _observations(series_id, values):
    name, unit, geography, export = SERIES[series_id]
    rows = []
    for day, value in enumerate(values, 26):
        period = f'2026-10-{day}'
        hour = 19 if day == 29 else 18
        rows.append({
            'series_id': series_id, 'name': name, 'unit': unit, 'geography': geography,
            'frequency': 'daily', 'definition_id': f'synthetic:{series_id}:v1',
            'source_id': 'synthetic:arcshift-ui', 'calendar_id': 'synthetic-session-calendar-v1',
            'reference_period': period, 'value': value,
            'published_at': f'{period}T{hour}:30:00+03:00' if value is not None and day != 30 else None,
            'received_at': f'{period}T{hour}:35:00+03:00' if value is not None else None,
            'revision_id': 'r2' if day == 29 else 'r1',
            'snapshot_id': SNAPSHOT, 'quality': 'missing' if value is None else 'observed',
            'export_allowed': export, 'synthetic': True,
        })
    previous = dict(rows[3], value=values[3] - 1, revision_id='r1', quality='superseded',
                    published_at='2026-10-29T18:30:00+03:00', received_at='2026-10-29T18:35:00+03:00')
    return rows[:3] + [previous] + rows[3:]


HISTORIES = {
    'fx': _observations('fx', (89.3, 90.0, None, 90.6, 91.2)),
    'equity': _observations('equity', (2710, 2705, 2720, 2709, 2694)),
    'global': _observations('global', (72.3, 72.1, 73.0, 72.8, 73.1)),
}


class UnavailableClient:
    def workspace(self, scenario, refreshed_at):
        return {'state': 'unavailable', 'synthetic': False, 'signal': None,
                'series': {}, 'information_as_of': None, 'refreshed_at': refreshed_at}


class FixtureClient:
    def __init__(self, db_path: Path, actor: str | None = None):
        self.db_path = db_path
        self.actor = actor

    def workspace(self, scenario, refreshed_at):
        fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        scenarios = {item['id']: item for item in fixture['scenarios']}
        item = scenarios.get(scenario, {'state': scenario, 'synthetic': True, 'signal': None})
        has_history = item['state'] in {'historical_demo', 'stale', 'market_closed'}
        signal = item['signal']
        if signal:
            signal = dict(
                signal, signal_id=f'{SNAPSHOT}:demo-signal', target_definition_id='synthetic:stress-proxy:v1',
                geography='RU', frequency='daily', feature_snapshot_id=SNAPSHOT,
                data_snapshot_id=SNAPSHOT, generated_at=signal['forecast_origin'],
                validation_id=None, policy_id=POLICY,
            )
        return dict(
            item, signal=signal, series={key: [dict(row) for row in rows] for key, rows in HISTORIES.items()}
            if has_history else {}, fixture_version=fixture['fixture_version'],
            information_as_of=('2026-11-01T12:00:00+03:00' if scenario == 'market_closed' else AS_OF)
            if has_history else None,
            refreshed_at=refreshed_at,
        )

    @contextmanager
    def _store(self):
        if not self.actor:
            raise PermissionError('Требуется демо-вход')
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS reviews (
                    actor TEXT, warning TEXT, status TEXT, note TEXT, updated_at TEXT,
                    PRIMARY KEY (actor, warning)
                );
                CREATE TABLE IF NOT EXISTS review_events (
                    actor TEXT, warning TEXT, status TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS watchlists (actor TEXT PRIMARY KEY, series TEXT);
                CREATE TABLE IF NOT EXISTS reports (
                    actor TEXT, id TEXT, payload TEXT, PRIMARY KEY (actor, id)
                );
            ''')
            yield db

    def review(self):
        with self._store() as db:
            row = db.execute('SELECT status, note, updated_at FROM reviews WHERE actor=? AND warning=?',
                             (self.actor, WARNING_ID)).fetchone()
        return dict(zip(('status', 'note', 'updated_at'), row or ('new', '', None)))

    def save_review(self, status, note):
        note = note.strip()
        if status not in STATUSES or len(note) > 1500:
            raise ValueError('Проверьте статус и длину заметки (до 1500 символов).')
        if status in {'closed', 'dismissed'} and not note:
            raise ValueError('Для закрытия или отклонения добавьте заметку.')
        updated_at = now()
        with self._store() as db:
            db.execute('''INSERT INTO reviews VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(actor, warning) DO UPDATE SET status=excluded.status,
                note=excluded.note, updated_at=excluded.updated_at''',
                       (self.actor, WARNING_ID, status, note, updated_at))
            db.execute('INSERT INTO review_events VALUES (?, ?, ?, ?)',
                       (self.actor, WARNING_ID, status, updated_at))

    def watchlist(self):
        with self._store() as db:
            row = db.execute('SELECT series FROM watchlists WHERE actor=?', (self.actor,)).fetchone()
        return json.loads(row[0]) if row else ['fx', 'equity']

    def save_watchlist(self, series_ids):
        selected = list(dict.fromkeys(series_ids))
        if any(series_id not in SERIES for series_id in selected):
            raise ValueError('В списке есть неизвестный ряд.')
        with self._store() as db:
            db.execute('''INSERT INTO watchlists VALUES (?, ?)
                ON CONFLICT(actor) DO UPDATE SET series=excluded.series''',
                       (self.actor, json.dumps(selected)))

    def create_report(self):
        review = self.review()
        source = self.workspace('historical_demo', None)
        report_id = uuid4().hex
        payload = {
            'id': report_id, 'synthetic': True, 'snapshot_id': SNAPSHOT,
            'fixture_version': source['fixture_version'], 'created_at': now(),
            'signal': source['signal'], 'review': review, 'warning_id': WARNING_ID,
            'observations': [{field: row[field] for field in REPORT_OBSERVATION_FIELDS}
                             for rows in source['series'].values() for row in rows if row['export_allowed']],
        }
        with self._store() as db:
            db.execute('INSERT INTO reports VALUES (?, ?, ?)',
                       (self.actor, report_id, json.dumps(payload, ensure_ascii=False)))
        return report_id

    def report_ids(self):
        with self._store() as db:
            return [row[0] for row in db.execute(
                'SELECT id FROM reports WHERE actor=? ORDER BY rowid DESC', (self.actor,))]

    def report(self, report_id):
        with self._store() as db:
            row = db.execute('SELECT payload FROM reports WHERE actor=? AND id=?',
                             (self.actor, report_id)).fetchone()
        if not row:
            raise LookupError('Отчёт недоступен')
        return json.loads(row[0])
