"""ReportLab/LongTable renderer adapted from Nikita's 7f0a403 report module."""

import csv
from functools import lru_cache
from html import escape
from io import BytesIO, StringIO
from pathlib import Path
from threading import RLock


PDF_LOCK = RLock()
STATUS = {"acknowledged": "Принят", "in_review": "В разборе", "closed": "Закрыт", "dismissed": "Отклонён"}


def safe_csv(value):
    if type(value) in (int, float):
        return value
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def csv_bytes(report):
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("report_id", "data_snapshot_id", "series_id", "resource_id", "reference_start", "reference_end", "value", "units", "published_at", "received_at", "revision", "is_latest", "synthetic", "source_rights_status", "warning_id", "signal_id", "policy_id"))
    for revision in report.observations:
        row = revision.observation
        writer.writerow([safe_csv(value) for value in (report.report_id, report.data_snapshot_id, row.series_id, row.resource_id, row.reference_start, row.reference_end, row.value, row.units, row.published_at.isoformat() if row.published_at else "unknown", row.received_at.isoformat(), revision.revision_number, str(revision.is_latest).lower(), "true", "not_admitted", report.review.review.warning_id or "", report.review.review.signal_id or "", report.review.review.policy_id or "")])
    return output.getvalue().encode("utf-8-sig")


@lru_cache(maxsize=1)
def pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font = TTFont("ArcShiftLiberation", str(Path(__file__).resolve().parent / "fonts/LiberationSans-Regular.ttf"))
    if not all(ord(char) in font.face.charToGlyph for char in "АБВГДЯабвгдяЁё"):
        raise ValueError("Cyrillic font is incomplete")
    pdfmetrics.registerFont(font)
    return "ArcShiftLiberation"


def pdf_bytes(report):
    with PDF_LOCK:
        return render_pdf(report)


def render_pdf(report):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    output = BytesIO()
    body = ParagraphStyle("body", fontName=pdf_font(), fontSize=9, leading=13, spaceAfter=7)
    heading = ParagraphStyle("heading", parent=body, fontSize=20, leading=25, spaceAfter=14)
    small = ParagraphStyle("small", parent=body, fontSize=7, leading=10)

    def para(value, style=body):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)

    review = report.review.review
    signal = review.scenario.signal
    content = [para("ARCSHIFT / СИНТЕТИЧЕСКИЕ ДАННЫЕ"), para("Отчёт о разборе", heading), para("Отчёт: " + str(report.report_id)), para("Снимок данных: " + report.data_snapshot_id), para("Снимок сценария: " + review.snapshot_id), para(f"Разбор {review.review_id} / версия {review.revision}"), para("Текущий прогноз недоступен. Модель и реальные источники не допущены.")]
    if review.warning_id:
        content.extend([para("Warning ID " + review.warning_id), para("Signal ID " + review.signal_id), para("Policy ID " + review.policy_id)])
    if signal is not None:
        content.extend([para(f"Только пример: score {signal.score}; {signal.score_kind}"), para(f"Горизонт примера: {signal.horizon_value} календарных дней; модель {signal.model_version}"), para("Информация примера на: " + signal.information_as_of.isoformat())])
    else:
        content.append(para("Сигнал отсутствует: " + review.scenario.state))
    content.extend([Spacer(1, 5), para("Личная проверка: " + STATUS[review.status]), para(review.note or "Вывод не указан"), para("Наблюдения и ревизии / только синтетические примеры")])
    table = [[para(value, small) for value in ("Ряд / единица", "Период / ревизия", "Значение", "Публикация", "Получение")]]
    for revision in report.observations:
        row = revision.observation
        table.append([para(value, small) for value in (row.series_id + " / " + row.units, f"{row.reference_start} / {row.reference_end} / r{revision.revision_number}" + ("" if revision.is_latest else " / заменена"), row.value, row.published_at.isoformat() if row.published_at else "Неизвестно", row.received_at.isoformat())])
    if report.observations:
        observations = LongTable(table, repeatRows=1, colWidths=(116, 108, 45, 115, 115), hAlign="LEFT")
        observations.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7efeb")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        content.append(observations)
    else:
        content.append(para("Наблюдения для отчёта не выбраны."))
    content.extend([Spacer(1, 10), para("Журнал статусов")])
    for event in report.review.events:
        content.append(para(f"v{event.revision}: {STATUS[event.status]} / Unix UTC {event.occurred_at}"))
    content.append(para("Закрытие разбора не подтверждает точность модели. Не является оценкой текущего кризисного риска."))
    SimpleDocTemplate(output, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=43, bottomMargin=43, title="ArcShift / синтетический отчёт").build(content)
    return output.getvalue()
