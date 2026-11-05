"""Render the same authorized report snapshot in three formats."""

import csv
from functools import lru_cache
from html import escape
from io import BytesIO, StringIO
import json
import os
from pathlib import Path

from workspace_client import REPORT_OBSERVATION_FIELDS


def timestamp(value):
    return value.replace('T', ' ') if value else 'Неизвестно'


def csv_bytes(report):
    output = StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=REPORT_OBSERVATION_FIELDS)
    writer.writeheader()
    writer.writerows(report['observations'])
    return output.getvalue().encode('utf-8-sig')


def json_bytes(report):
    return json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8')


@lru_cache
def _pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    paths = [
        os.getenv('ARCSHIFT_PDF_FONT'),
        Path(os.getenv('WINDIR', 'C:/Windows')) / 'Fonts/arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for path in paths:
        if path and Path(path).is_file():
            pdfmetrics.registerFont(TTFont('ArcShift', str(path)))
            return 'ArcShift'
    raise OSError('Укажите путь к шрифту с кириллицей в ARCSHIFT_PDF_FONT.')


def pdf_bytes(report, status_label):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    signal = report['signal']
    review = report['review']
    output = BytesIO()
    font = _pdf_font()
    body = ParagraphStyle('body', fontName=font, fontSize=9, leading=13,
                          textColor=colors.HexColor('#172b43'), spaceAfter=6)
    heading = ParagraphStyle('heading', parent=body, fontSize=20, leading=25, spaceAfter=12)
    small = ParagraphStyle('small', parent=body, fontSize=7.5, leading=10)

    def para(value, style=body):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)

    content = [
        para('ARCSHIFT / СИНТЕТИЧЕСКИЕ ДАННЫЕ'),
        para('Отчёт о проверке сигнала', heading),
        para(f"Снимок {report['snapshot_id']} · набор {report['fixture_version']}"),
        para(f"Отчёт {report['id']} · сформирован {timestamp(report['created_at'])}"),
        para(f"Информация на {timestamp(signal['information_as_of'])} · дата сигнала "
             f"{timestamp(signal['forecast_origin'])}"),
        para(f"{signal['geography']} · {signal['task_id']} · {signal['horizon_value']} календарных дней"),
        para(f"Оценка {signal['score']} · {signal['score_kind']} · {signal['validity_status']}"),
        para(f"Модель {signal['model_version']} · политика {signal['policy_id']}"),
        para('Калибровка не проверена. Текущая оценка риска недоступна.'),
        Spacer(1, 6),
        para(f"Личная проверка · {status_label} · {timestamp(review['updated_at']) if review['updated_at'] else 'без изменений'}"),
        para(review['note'] or 'Заметка отсутствует.'),
        Spacer(1, 8),
        para('Наблюдения, разрешённые для выгрузки'),
    ]
    table = [[para(label, small) for label in
              ('Ряд / единица', 'Период / ревизия', 'Значение', 'Публикация', 'Получение')]]
    for row in report['observations']:
        cells = (f"{row['series_id']} · {row['unit']}",
                 f"{row['reference_period']} · {row['revision_id']}",
                 row['value'] if row['value'] is not None else 'Пропуск',
                 timestamp(row['published_at']), timestamp(row['received_at']))
        table.append([para(value, small) for value in cells])
    observations = LongTable(table, repeatRows=1, colWidths=(77, 95, 57, 134, 136), hAlign='LEFT')
    observations.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbe9f9')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5fa')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    content.append(observations)
    SimpleDocTemplate(output, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=43,
                      bottomMargin=43, title='ArcShift — синтетический отчёт').build(content)
    return output.getvalue()
