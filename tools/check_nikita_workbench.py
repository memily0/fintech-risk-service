"""Local browser acceptance of the Nikita follow-up. Synthetic data only."""

import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote, urlsplit

from playwright.sync_api import expect, sync_playwright

from arcshift_v1.auth import read_local_outbox


ROOT = Path(__file__).resolve().parents[1]
BASE_API = "/api/v1/workspace"
ARTIFACTS = ROOT / "output/playwright/nikita-followup"


def sign_in(context, base, database, email):
    credentials = {"email": email, "password": "Synthetic-only-followup-password"}
    headers = {"Origin": base}
    assert context.request.post(base + "/api/v1/auth/register", data=credentials, headers=headers).status == 202
    token = read_local_outbox(database, email)[0]["token"]
    assert context.request.post(base + "/api/v1/auth/verify-email", data={"token": token}, headers=headers).status == 204
    assert context.request.post(base + "/api/v1/auth/login", data=credentials, headers=headers).status == 204


def watch(page, errors, external, base):
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url) if not request.url.startswith(base) else None)


def navigate(page, view):
    page.locator(f'[data-view="{view}"]').click()
    expect(page.locator(f'[data-view="{view}"]')).to_have_attribute("aria-current", "page")

def refresh(page):
    control = page.locator("#refresh-button")
    control.click()
    expect(control).to_be_enabled()


def verify_fake_market(browser, base):
    context = browser.new_context()
    catalog = context.request.get(base + "/api/v1/market/series").json()
    ids = [row["series_id"] for row in catalog["series"][:4]]
    histories = {series: context.request.get(base + "/api/v1/market/series/" + series + "/history").json()
                 for series in ids}
    page = context.new_page()
    errors, external = [], []
    watch(page, errors, external, base)
    mode = {"state": "loading", "catalog_calls": 0}
    waiting = []

    def fake(route):
        path = unquote(urlsplit(route.request.url).path)
        if mode["state"] == "loading":
            waiting.append(route)
            return
        if path.endswith("/series"):
            result = copy.deepcopy(catalog)
            result["series"] = [row for row in result["series"] if row["series_id"] in ids]
            mode["catalog_calls"] += 1
            result["data_snapshot_id"] = "fake-A" if mode["state"] == "mismatch" or (mode["state"] == "race" and mode["catalog_calls"] == 1) else "fake-B"
        else:
            series = path.split("/series/")[1].removesuffix("/history")
            result = copy.deepcopy(histories[series])
            result["data_snapshot_id"] = "fake-B"
            if mode["state"] == "partial":
                if series == ids[0]:
                    result["observations"] = []
                elif series == ids[1]:
                    for row in result["observations"]:
                        row["is_latest"] = False
                elif series == ids[2]:
                    for row in result["observations"]:
                        row["observation"]["value"] = None
                else:
                    for row in result["observations"]:
                        row["observation"]["value"] = 0
            elif mode["state"] == "failure" and series == ids[0]:
                route.fulfill(status=503, json={"detail": {"code": "fixture_store_unavailable"}})
                return
            elif mode["state"] in ("stale", "missing", "market_closed", "error"):
                result["data_state"] = mode["state"]
        route.fulfill(json=result)

    page.route("**/api/v1/market/series**", fake)
    page.goto(base, wait_until="domcontentloaded")
    expect(page.locator("#market-status")).to_have_text("Получение опубликованного снимка")
    mode["state"] = "partial"
    for route in waiting:
        fake(route)
    expect(page.locator(".market-card")).to_have_count(4)
    expect(page.locator(".market-value").nth(0)).to_have_text("Нет актуальной ревизии")
    expect(page.locator(".market-value").nth(1)).to_have_text("Нет актуальной ревизии")
    expect(page.locator(".market-value").nth(2)).to_have_text("Пропуск")
    expect(page.locator(".market-value").nth(3)).to_have_text("0")
    for state, label in (("stale", "Данные устарели"), ("missing", "Пропуск данных"),
                         ("market_closed", "Плановое закрытие рынка"), ("error", "Источник недоступен")):
        mode["state"] = state
        refresh(page)
        expect(page.locator(".market-card .detail-message").first).to_have_text(label)
    mode["state"] = "failure"
    refresh(page)
    expect(page.locator(".market-card .detail-message").first).to_have_text("История ряда недоступна")
    expect(page.locator(".market-value").nth(3)).not_to_have_text("Нет актуальной ревизии")
    mode["state"] = "race"
    mode["catalog_calls"] = 0
    refresh(page)
    expect(page.locator(".market-card")).to_have_count(4)
    page.locator(".market-card .button").first.click()
    expect(page.locator("#history-metadata")).to_contain_text("fake-B")
    expect(page.locator("#history-metadata")).not_to_contain_text("fake-A")
    assert mode["catalog_calls"] >= 2
    page.screenshot(path=ARTIFACTS / "history-snapshot-B.png", full_page=True, animations="disabled")
    mode["state"] = "mismatch"
    refresh(page)
    expect(page.locator("#market-status")).to_have_text("Снимок обновляется. Повторите проверку.")
    expect(page.locator(".market-card")).to_have_count(0)
    expect(page.locator("#history-rows tr")).to_have_count(0)
    assert not errors, errors
    assert not external, external
    context.close()


def verify_workflow(browser, base, database):
    context = browser.new_context(viewport={"width": 1440, "height": 1080}, accept_downloads=True)
    sign_in(context, base, database, "nikita-a@example.test")
    page = context.new_page()
    errors, external = [], []
    watch(page, errors, external, base)
    page.goto(base)
    expect(page.locator(".market-card")).to_have_count(7)
    assert page.locator("#market-chart svg").bounding_box()["height"] > 100
    expect(page.locator(".market-card .market-value").first).not_to_have_text("Нет актуальной ревизии")
    page.get_by_role("button", name="Наблюдать показатель", exact=True).first.click()
    expect(page.locator("#watch-count")).to_have_text("1")
    navigate(page, "watchlist")
    page.locator("#indicator-watchlist .button").first.click()
    expect(page.locator("#history-rows tr").first).to_be_visible()
    expect(page.locator("#history-metadata")).to_contain_text("market-")
    navigate(page, "warnings")
    expect(page.locator(".warning-row")).to_have_count(2)
    ids = page.locator(".warning-row").evaluate_all("(rows) => rows.map(row => row.dataset.warningId)")
    assert len(set(ids)) == 2
    for _ in range(2):
        refresh(page)
        expect(page.locator(".warning-row")).to_have_count(2)
    assert ids == page.locator(".warning-row").evaluate_all("(rows) => rows.map(row => row.dataset.warningId)")
    page.screenshot(path=ARTIFACTS / "queue-1440.png", full_page=True, animations="disabled")
    page.get_by_role("button", name="Разобрать предупреждение").first.click()
    expect(page.locator("#review-note")).to_be_visible()
    page.locator("#review-note").fill("Вымышленная заметка Никиты <script>synthetic</script>")
    page.locator("#review-status").select_option("in_review")
    page.get_by_role("button", name="Сохранить вывод", exact=True).click()
    expect(page.locator("#notice")).to_contain_text("Вывод сохранён")
    page.get_by_role("button", name="Сохранить отчёт", exact=True).click()
    expect(page.locator("#report-detail")).to_contain_text("Вымышленная заметка")
    reports = context.request.get(base + BASE_API + "/reports").json()["reports"]
    assert len(reports) == 1
    for extension in ("PDF", "CSV", "JSON"):
        with page.expect_download() as download:
            page.get_by_role("button", name="Скачать " + extension, exact=True).click()
        assert download.value.failure() is None
    page.screenshot(path=ARTIFACTS / "saved-report-1440.png", full_page=True, animations="disabled")
    navigate(page, "model")
    expect(page.locator("#model-metadata")).to_contain_text("ru_market_stress_onset_v1")
    expect(page.locator("#current-signal-state")).to_have_text("Недоступен")
    bob = browser.new_context()
    sign_in(bob, base, database, "nikita-b@example.test")
    bob_page = bob.new_page()
    watch(bob_page, errors, external, base)
    bob_page.goto(base)
    navigate(bob_page, "warnings")
    expect(bob_page.locator(".warning-status")).to_have_text(["Новое", "Новое"])
    for suffix in ("", "/export.pdf", "/export.csv", "/export.json"):
        assert bob.request.get(base + BASE_API + "/reports/" + reports[0]["report_id"] + suffix).status == 404
    for width in (375, 768, 1440):
        page.set_viewport_size({"width": width, "height": 1080})
        navigate(page, "monitor")
        expect(page.locator(".market-card")).to_have_count(7)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=ARTIFACTS / f"overview-{width}.png", full_page=True, animations="disabled")
        navigate(page, "warnings")
        page.evaluate("document.documentElement.style.fontSize='200%'")
        first = page.get_by_role("button", name="Разобрать предупреждение").first
        first.focus()
        first.press("Enter")
        expect(page.locator("#review-note")).to_be_visible()
        page.screenshot(path=ARTIFACTS / f"review-{width}-zoom200.png", full_page=True, animations="disabled")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), page.evaluate("() => ({viewport:innerWidth, width:document.documentElement.scrollWidth, x:scrollX, overflow:[...document.querySelectorAll('body *')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>[e.tagName,e.className,e.clientWidth,e.scrollWidth]).slice(-15)})")
        page.evaluate("document.documentElement.style.fontSize=''")
    second_tab = context.new_page()
    second_tab.goto(base)
    navigate(second_tab, "reports")
    expect(second_tab.locator("#report-detail")).to_contain_text("Вымышленная заметка")
    page.get_by_role("button", name="Выйти", exact=True).click()
    expect(second_tab.locator("#account-email")).to_have_text("")
    expect(second_tab.locator("#report-detail")).not_to_contain_text("Вымышленная заметка")
    assert context.request.get(base + BASE_API + "/reports/" + reports[0]["report_id"]).status == 401
    assert bob.request.get(base + BASE_API + "/warnings").status == 200
    assert not errors, errors
    assert not external, external
    context.close()
    bob.close()


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ROOT / ".cache").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nikita-check-", dir=ROOT / ".cache") as temporary:
        database = Path(temporary) / "synthetic.sqlite3"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, ARCSHIFT_ENVIRONMENT="test", ARCSHIFT_DB_PATH=str(database),
                   ARCSHIFT_HOST="127.0.0.1", ARCSHIFT_PORT=str(port), ARCSHIFT_STORAGE_BACKEND="sqlite", PYTHONUTF8="1")
        server = subprocess.Popen([sys.executable, "-m", "arcshift_v1"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context()
                for _ in range(100):
                    try:
                        if context.request.get(base + "/readyz").ok:
                            break
                    except Exception:
                        pass
                    if server.poll() is not None:
                        raise RuntimeError("Local synthetic server exited")
                    time.sleep(.1)
                else:
                    raise RuntimeError("Local readiness timeout")
                context.close()
                verify_fake_market(browser, base)
                verify_workflow(browser, base, database)
                browser.close()
                print("PASS partial/null/zero histories, A/B snapshots, queue, ownership, exports, logout, layouts, keyboard, 200% text, zero external requests")
        finally:
            server.terminate()
            server.wait(timeout=15)


if __name__ == "__main__":
    main()
