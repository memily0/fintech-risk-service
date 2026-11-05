"""Run against the local Streamlit entry point. See docs/arcshift-v1-nikita.md."""

import json
import os
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


URL = os.getenv('ARCSHIFT_UI_URL', 'http://127.0.0.1:8767')
ARTIFACTS = Path('output/playwright/arcshift-v1')
PDF_EXAMPLE = Path('output/pdf/arcshift-v1-demo.pdf')
NOTE = 'Синтетическая заметка: проверить разрыв ряда.'
WARNING = 'Предупреждение о рыночном стрессе'


def sidebar(page):
    expand = page.get_by_test_id('stExpandSidebarButton')
    if expand.is_visible():
        expand.click()
    return page.get_by_test_id('stSidebar')


def hide_mobile_sidebar(page):
    close = page.get_by_test_id('stSidebarCollapseButton')
    if page.viewport_size['width'] < 821 and close.is_visible():
        close.click()


def nav(page, section):
    sidebar(page).get_by_text(section, exact=True).click()
    expect(page.get_by_role('heading', name=section, exact=True)).to_be_visible()
    hide_mobile_sidebar(page)


def choose(page, label, choice, scope=None):
    box = (scope or page).get_by_test_id('stSelectbox').filter(has_text=label)
    box.get_by_role('button', name='Open', exact=True).click()
    page.get_by_role('option', name=choice, exact=True).click()


def button(page, name):
    return page.get_by_role('button', name=name, exact=True)


def login(page, alias):
    nav(page, 'Аккаунт')
    choose(page, 'Демо-аккаунт', alias)
    button(page, 'Войти в демо').click()
    expect(page.get_by_text(f'Активен аккаунт «{alias}».')).to_be_visible()


class WorkspaceBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        PDF_EXAMPLE.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def start(self, width=1440):
        context = self.browser.new_context(viewport={'width': width, 'height': 960}, accept_downloads=True)
        self.addCleanup(context.close)
        page = context.new_page()
        page.set_default_timeout(10000)
        page.goto(URL)
        expect(page.get_by_text('СИНТЕТИЧЕСКИЕ ДАННЫЕ · ДЕМО')).to_be_visible(timeout=20000)
        expect(page.locator('.arc-card')).to_have_count(3)
        return page

    def test_workflow_isolation_and_downloads(self):
        page = self.start()
        requests = []
        page.on('request', lambda request: requests.append(urlsplit(request.url).path))
        login(page, 'Демо A')
        nav(page, 'Предупреждения')
        warning = page.get_by_role('heading', name=WARNING)
        expect(warning).to_have_count(1)
        refresh = page.get_by_role('button', name='Обновить проверку')
        as_of = page.get_by_text('Информация на', exact=True).locator('xpath=following-sibling::dd')
        before = as_of.inner_text()
        refresh.click()
        refresh.click()
        expect(warning).to_have_count(1)
        expect(as_of).to_have_text(before)
        button(page, 'Разобрать сигнал').click()
        expect(page.get_by_text('Синтетическая оценка · 0.35')).to_be_visible()
        expect(page.get_by_text('synthetic-no-fitted-model / нет', exact=True)).to_be_visible()
        button(page, 'Перейти к личной проверке').click()
        choose(page, 'Решение', 'Закрыто')
        button(page, 'Сохранить проверку').click()
        expect(page.get_by_text('Для закрытия или отклонения добавьте заметку.')).to_be_visible()
        page.get_by_role('textbox', name='Личная заметка').fill(NOTE)
        button(page, 'Сохранить проверку').click()
        expect(page.get_by_text('Личная проверка сохранена.')).to_be_visible()
        nav(page, 'Предупреждения')
        choose(page, 'Статус проверки', 'Новое')
        expect(page.get_by_text('По выбранному фильтру предупреждений нет.')).to_be_visible()
        choose(page, 'Статус проверки', 'Закрыто')
        expect(warning).to_have_count(1)

        nav(page, 'Список наблюдения')
        brent = page.get_by_role('checkbox', name='Brent · условная цена')
        page.get_by_test_id('stCheckbox').get_by_text('Brent · условная цена', exact=True).click()
        expect(brent).to_be_checked()
        button(page, 'Сохранить список').click()
        expect(page.get_by_text('Список сохранён.')).to_be_visible()

        nav(page, 'Отчёты')
        button(page, 'Создать отчёт').click()
        expect(page.get_by_text(NOTE, exact=True)).to_be_visible()
        links = page.frame_locator('iframe')
        files = {}
        for format_ in ('PDF', 'CSV', 'JSON'):
            link = links.get_by_role('link', name=f'Скачать {format_}')
            expect(link).to_have_attribute('href', re.compile(r'^data:'))
            with page.expect_download() as downloaded:
                link.click()
            path = ARTIFACTS / downloaded.value.suggested_filename
            downloaded.value.save_as(path)
            files[format_] = path.read_bytes()
            path.unlink()
        PDF_EXAMPLE.write_bytes(files['PDF'])
        report = json.loads(files['JSON'])
        self.assertEqual(report['review']['note'], NOTE)
        self.assertEqual(report['snapshot_id'], 'synthetic-ui-001')
        self.assertNotIn(b'Brent', files['CSV'])
        self.assertEqual({row['series_id'] for row in report['observations']}, {'equity', 'fx'})
        self.assertFalse(any(path.startswith('/media/') for path in requests))
        page.screenshot(path=ARTIFACTS / 'private-report-1440.png', full_page=True, animations='disabled')

        nav(page, 'Аккаунт')
        button(page, 'Выйти').click()
        nav(page, 'Отчёты')
        expect(page.get_by_text('Войдите в демо-аккаунт, чтобы открыть личный раздел.')).to_be_visible()
        expect(page.get_by_text(NOTE, exact=True)).to_have_count(0)
        file_response = page.request.get(f'{URL}/reports/{report["id"]}.pdf')
        self.assertFalse(file_response.body().startswith(b'%PDF'))
        login(page, 'Демо B')
        nav(page, 'Отчёты')
        expect(page.get_by_text('Сохранённых отчётов пока нет.')).to_be_visible()
        nav(page, 'Личная проверка')
        expect(page.get_by_role('textbox', name='Личная заметка')).to_have_value('')
        nav(page, 'Предупреждения')
        expect(page.get_by_text('Личный статус · Новое')).to_be_visible()
        nav(page, 'Список наблюдения')
        expect(brent).not_to_be_checked()
        nav(page, 'Аккаунт')
        button(page, 'Выйти').click()
        login(page, 'Демо A')
        nav(page, 'Список наблюдения')
        expect(brent).to_be_checked()
        nav(page, 'Отчёты')
        expect(page.get_by_text(NOTE, exact=True)).to_be_visible()
        self.assertFalse(any(path.startswith('/media/') for path in requests))

    def test_data_states_and_real_gate(self):
        page = self.start()
        nav(page, 'Разбор сигнала')
        expect(page.get_by_text('Синтетическая оценка · 0.35')).to_be_visible()
        for label, message in (
            ('Загрузка', 'Загрузка снимка.'),
            ('Пустой набор', 'Нет доступной истории'),
            ('Ошибка источника', 'Источник временно недоступен.'),
            ('Устарело', 'Данные устарели.'),
            ('Горизонт не поддерживается', 'Выбранный горизонт не поддерживается.'),
            ('Пропуск данных', 'Не хватает обязательных наблюдений.'),
            ('Рынок закрыт', 'Рынок закрыт по демонстрационному календарю.'),
            ('Свеча не закрыта', 'Дневная свеча ещё не закрыта.'),
        ):
            with self.subTest(label=label):
                choose(page, 'Сценарий данных', label, sidebar(page))
                expect(page.get_by_text(message, exact=False).last).to_be_visible()
                expect(page.get_by_text('Синтетическая оценка · 0.35')).to_have_count(0)
        choose(page, 'Режим данных', 'Рабочий режим', sidebar(page))
        expect(page.get_by_text('Рабочий режим недоступен.', exact=False)).to_be_visible()
        expect(page.get_by_text('СИНТЕТИЧЕСКИЕ ДАННЫЕ · ДЕМО')).to_have_count(0)
        nav(page, 'Методология')
        expect(page.get_by_text('OOS-оценка и её фолды недоступны.')).to_be_visible()
        choose(page, 'Режим данных', 'Синтетическое демо', sidebar(page))
        choose(page, 'Сценарий данных', 'Пустой набор', sidebar(page))
        nav(page, 'История рядов')
        expect(page.get_by_text('Нет доступной истории для выбранного набора.')).to_be_visible()
        expect(page.get_by_role('table')).to_have_count(0)

    def test_layout_history_keyboard_and_text_zoom(self):
        for width in (375, 768, 1440):
            with self.subTest(width=width):
                page = self.start(width)
                expect(page.get_by_test_id('stPlotlyChart')).to_be_visible()
                page.screenshot(path=ARTIFACTS / f'overview-{width}.png', full_page=True, animations='disabled')
                nav(page, 'История рядов')
                expect(page.get_by_role('table').get_by_text('Пересмотрено')).to_be_visible()
                expect(page.get_by_role('table').get_by_text('Неизвестно').first).to_be_visible()
                expect(page.get_by_role('table').get_by_text('Пропуск', exact=True).first).to_be_visible()
                choose(page, 'Показатель', 'Условный индекс российского рынка акций с длинным названием')
                expect(page.get_by_role('table').get_by_text('2694', exact=True)).to_be_visible()

                panel = sidebar(page)
                radio = panel.locator('input[type=radio]').nth(1)
                radio.focus()
                radio.press('ArrowDown')
                expect(page.get_by_role('heading', name='Предупреждения', exact=True)).to_be_visible()
                hide_mobile_sidebar(page)
                button(page, 'Разобрать сигнал').focus()
                button(page, 'Разобрать сигнал').press('Enter')
                expect(page.get_by_text('Синтетическая оценка · 0.35')).to_be_visible()
                page.evaluate("document.documentElement.style.fontSize = '200%'")
                expect(page.get_by_role('heading', name='Разбор сигнала')).to_be_visible()
                self.assertTrue(page.locator('main').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'))
                details = page.locator('.arc-details')
                expect(details).to_be_visible()
                details.scroll_into_view_if_needed()
                page.screenshot(path=ARTIFACTS / f'investigation-{width}-zoom200.png', full_page=True,
                                animations='disabled')
        page = self.start(375)
        login(page, 'Демо A')
        page.evaluate("document.documentElement.style.fontSize = '200%'")
        nav(page, 'Личная проверка')
        page.get_by_role('textbox', name='Личная заметка').fill(NOTE)
        button(page, 'Сохранить проверку').press('Enter')
        expect(page.get_by_text('Личная проверка сохранена.')).to_be_visible()
        button(page, 'Перейти к отчётам').press('Enter')
        button(page, 'Создать отчёт').press('Enter')
        expect(page.frame_locator('iframe').get_by_role('link', name='Скачать PDF')).to_be_visible()
        self.assertTrue(page.locator('main').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'))


if __name__ == '__main__':
    unittest.main()
