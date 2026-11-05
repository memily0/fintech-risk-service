import csv
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from uuid import uuid4

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from workspace_client import FixtureClient, SNAPSHOT, UnavailableClient, WARNING_ID
from workspace_reports import csv_bytes, json_bytes, pdf_bytes


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.path = Path('.cache/arcshift-ui-tests') / f'{uuid4().hex}.sqlite3'
        self.alice = FixtureClient(self.path, 'synthetic-a')
        self.bob = FixtureClient(self.path, 'synthetic-b')
        self.guest = FixtureClient(self.path)

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_invalid_states_never_offer_score(self):
        for state in ('loading', 'empty', 'error', 'missing', 'unsupported', 'stale',
                      'market_closed', 'incomplete_bar'):
            with self.subTest(state=state):
                self.assertIsNone(self.alice.workspace(state, 'refresh')['signal'])
        working = UnavailableClient().workspace('historical_demo', 'refresh')
        self.assertEqual(working['state'], 'unavailable')
        self.assertIsNone(working['signal'])
        self.assertFalse(working['series'])

    def test_refresh_preserves_warning_and_as_of(self):
        first = self.alice.workspace('historical_demo', 'first')
        second = self.bob.workspace('historical_demo', 'second')
        self.assertEqual(first['information_as_of'], second['information_as_of'])
        self.assertEqual(first['signal'], second['signal'])
        self.assertNotEqual(first['refreshed_at'], second['refreshed_at'])
        self.assertEqual(first['signal']['score_kind'], 'synthetic_uncalibrated_score')
        self.assertIsNone(first['series']['fx'][2]['value'])
        self.assertIsNone(first['series']['fx'][-1]['published_at'])
        self.assertIsNotNone(first['series']['fx'][-1]['received_at'])
        self.assertEqual(first['series']['fx'][3]['quality'], 'superseded')
        self.assertLess(first['series']['fx'][3]['received_at'], first['series']['fx'][4]['received_at'])

    def test_private_review_watchlist_and_audit(self):
        for status in ('closed', 'dismissed'):
            with self.assertRaises(ValueError):
                self.alice.save_review(status, '   ')
        self.alice.save_review('acknowledged', '')
        self.alice.save_review('in_review', 'Синтетическая заметка')
        self.alice.save_review('closed', 'Проверка выполнена в демо')
        self.assertEqual(self.bob.review()['status'], 'new')
        self.assertEqual(self.alice.review()['status'], 'closed')
        self.assertTrue(self.alice.review()['updated_at'].endswith('+00:00'))
        with closing(sqlite3.connect(self.path)) as db:
            events = db.execute('SELECT warning, status FROM review_events ORDER BY rowid').fetchall()
        self.assertEqual(events, [(WARNING_ID, 'acknowledged'), (WARNING_ID, 'in_review'), (WARNING_ID, 'closed')])
        self.alice.save_watchlist(['global', 'fx', 'global'])
        self.bob.save_watchlist([])
        self.assertEqual(FixtureClient(self.path, self.alice.actor).watchlist(), ['global', 'fx'])
        self.assertEqual(self.bob.watchlist(), [])
        with self.assertRaises(PermissionError):
            self.guest.review()
        with self.assertRaises(PermissionError):
            self.guest.save_watchlist(['fx'])

    def test_immutable_report_and_rights_in_all_formats(self):
        note = 'Синтетическая заметка <b>с разметкой</b>'
        self.alice.save_review('closed', note)
        report_id = self.alice.create_report()
        self.alice.save_review('dismissed', 'Новое решение')
        report = self.alice.report(report_id)
        self.assertEqual(report['snapshot_id'], SNAPSHOT)
        self.assertEqual(report['review']['note'], note)
        self.assertFalse(self.bob.report_ids())
        with self.assertRaises(LookupError):
            self.bob.report(report_id)
        with self.assertRaises(PermissionError):
            self.guest.report(report_id)
        csv_rows = list(csv.DictReader(io.StringIO(csv_bytes(report).decode('utf-8-sig'))))
        self.assertEqual(len(csv_rows), len(report['observations']))
        self.assertEqual({row['series_id'] for row in csv_rows}, {'fx', 'equity'})
        self.assertEqual(json.loads(json_bytes(report)), report)
        self.assertEqual({row['series_id'] for row in report['observations']}, {'fx', 'equity'})
        pdf = PdfReader(io.BytesIO(pdf_bytes(report, 'Закрыто')))
        content = '\n'.join(page.extract_text() for page in pdf.pages)
        for expected in (SNAPSHOT, 'СИНТЕТИЧЕСКИЕ ДАННЫЕ', note, 'Неизвестно', '2026-10-30'):
            self.assertIn(expected, content)
        self.assertNotIn('Brent', content)

    def test_empty_csv_keeps_headers_without_observation_rows(self):
        report = self.alice.report(self.alice.create_report())
        full_csv = csv.DictReader(io.StringIO(csv_bytes(report).decode('utf-8-sig')))

        empty_report = dict(report, observations=[])
        empty_csv = csv.DictReader(io.StringIO(csv_bytes(empty_report).decode('utf-8-sig')))

        self.assertEqual(empty_csv.fieldnames, full_csv.fieldnames)
        self.assertEqual(list(empty_csv), [])


if __name__ == '__main__':
    unittest.main()
