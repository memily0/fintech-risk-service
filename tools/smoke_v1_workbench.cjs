/* Local-only browser integration check; all accounts and evidence are synthetic. */
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const net = require("node:net");
const { spawn, spawnSync } = require("node:child_process");
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const python = path.join(root, ".venv-v1/bin/python");
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function main() {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "arcshift-workbench-"));
  const evidence = process.env.ARCSHIFT_BROWSER_EVIDENCE_DIR;
  if (evidence) fs.mkdirSync(evidence, { recursive: true });
  let child, browser, context;
  let stopped = false;
  const errors = [], external = [];
  try {
    const port = await freePort(), base = `http://127.0.0.1:${port}`;
    const env = { ...process.env, ARCSHIFT_ENVIRONMENT: "test", ARCSHIFT_DATA_MODE: "synthetic", ARCSHIFT_HOST: "127.0.0.1", ARCSHIFT_PORT: String(port), ARCSHIFT_STORAGE_BACKEND: "sqlite", ARCSHIFT_DB_PATH: path.join(temporary, "test.sqlite3"), PYTHONDONTWRITEBYTECODE: "1" };
    child = spawn(python, ["-m", "arcshift_v1"], { cwd: root, env, stdio: "ignore" });
    const exit = new Promise((resolve) => child.once("exit", resolve));
    const deadline = Date.now() + 15000;
    while (true) {
      if (child.exitCode !== null) throw new Error("Local test server exited");
      try { if ((await fetch(base + "/readyz")).ok) break; } catch {}
      if (Date.now() > deadline) throw new Error("Readiness timed out");
      await delay(100);
    }
    browser = await chromium.launch({ headless: true, ...(process.env.ARCSHIFT_PLAYWRIGHT_CHANNEL ? { channel: process.env.ARCSHIFT_PLAYWRIGHT_CHANNEL } : {}) });
    context = await browser.newContext({ viewport: { width: 1440, height: 980 }, acceptDownloads: true });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error" && !message.text().includes("401")) errors.push(message.text()); });
    page.on("request", (request) => { if (!request.url().startsWith(base)) external.push(request.url()); });
    await page.goto(base);
    await page.locator(".scenario-row").first().waitFor();
    assert.equal(await page.locator(".scenario-row").count(), 6);
    assert.ok(await page.locator("svg").count() >= 10);
    assert.equal(await page.locator("#scenario-detail .signal-number").textContent(), "0.35");
    if (evidence) await page.screenshot({ path: path.join(evidence, "desktop-monitor.png"), fullPage: true });

    await page.locator('[data-view="history"]').click();
    await page.locator("#history-rows tr").first().waitFor();
    assert.equal(await page.locator("#history-series option").count(), 7);
    assert.equal(await page.locator("#history-rows tr").count(), 3);
    assert.ok((await page.locator("#history-rows").textContent()).includes("Неизвестно"));
    await page.locator("#history-revisions").check();
    await page.waitForFunction(() => document.querySelectorAll("#history-rows tr").length === 4);
    assert.equal(await page.locator("#history-rows tr.superseded").count(), 1);
    await page.locator("#history-start").fill("2026-11-05");
    await page.locator("#history-start").dispatchEvent("change");
    await page.waitForFunction(() => document.querySelectorAll("#history-rows tr").length === 2);
    if (evidence) await page.screenshot({ path: path.join(evidence, "desktop-history.png"), fullPage: true });
    await page.locator("#history-start").fill(""); await page.locator("#history-start").dispatchEvent("change");
    await page.locator('[data-view="monitor"]').click();

    await page.locator('[data-view="model"]').click();
    await page.locator(".model-input-row").first().waitFor();
    assert.equal(await page.locator(".model-input-row").count(), 5);
    assert.equal(await page.locator("#current-signal-state").textContent(), "Недоступен");
    assert.equal(await page.locator("#model-blockers li").count(), 5);
    await page.locator("#model-horizon").selectOption("90");
    await page.waitForFunction(() => document.querySelectorAll(".model-input-row").length === 5);
    assert.equal(await page.locator("#current-signal-state").textContent(), "Недоступен");
    if (evidence) await page.screenshot({ path: path.join(evidence, "desktop-model.png"), fullPage: true });
    await page.locator('[data-view="monitor"]').click();

    await page.locator("#login-button").click();
    await page.locator('[data-auth="register"]').click();
    await page.locator("#email-input").fill("browser@example.test");
    await page.locator("#password-input").fill("Synthetic-only-browser-password");
    await page.locator("#auth-submit").click();
    await page.locator("#token-field:not([hidden])").waitFor();
    const outbox = spawnSync(python, ["-m", "arcshift_v1.dev_outbox", "--email", "browser@example.test"], { cwd: root, env, encoding: "utf8" });
    if (outbox.status !== 0) throw new Error("Local outbox CLI failed");
    const token = JSON.parse(outbox.stdout).messages[0].token;
    await page.locator("#token-input").fill(token);
    await page.locator("#auth-submit").click();
    await page.locator('[data-auth="login"][aria-selected="true"]').waitFor();
    await page.locator("#password-input").fill("Synthetic-only-browser-password");
    await page.locator("#auth-submit").click();
    await page.locator("#auth-dialog").waitFor({ state: "hidden" });
    assert.equal(await page.locator("#account-email").textContent(), "browser@example.test");
    await page.getByRole("button", { name: "Наблюдать", exact: true }).click();
    await page.waitForFunction(() => document.getElementById("watch-count").textContent === "1");
    await page.getByRole("button", { name: "Начать разбор", exact: true }).click();
    await page.locator("#review-note").waitFor();
    const note = 'Тестовый вывод <img src=x onerror="window.injected=true">';
    await page.locator("#review-note").fill(note);
    await page.locator("#review-status").selectOption("in_review");
    await page.getByRole("button", { name: "Сохранить вывод", exact: true }).click();
    await page.waitForFunction(() => document.getElementById("notice").textContent.includes("Версия 2"));
    assert.equal(await page.evaluate(() => window.injected), undefined);

    await page.reload();
    await page.waitForFunction(() => document.getElementById("watch-count").textContent === "1");
    await page.locator('[data-view="reviews"]').click();
    await page.locator("#review-note").waitFor();
    assert.equal(await page.locator("#review-note").inputValue(), note);
    await page.locator("#review-status").selectOption("closed");
    await page.getByRole("button", { name: "Сохранить вывод", exact: true }).click();
    await page.waitForFunction(() => document.getElementById("notice").textContent.includes("Версия 3"));
    const saved = await page.request.get(base + "/api/v1/workspace/reviews");
    const review = (await saved.json()).reviews[0];
    for (const extension of ["JSON", "CSV"]) {
      const downloading = page.waitForEvent("download");
      await page.getByRole("button", { name: "Скачать " + extension, exact: true }).click();
      const download = await downloading;
      await download.saveAs(path.join(temporary, "report." + extension.toLowerCase()));
    }
    const report = JSON.parse(fs.readFileSync(path.join(temporary, "report.json"), "utf8"));
    assert.equal(report.review.note, note); assert.equal(report.review.status, "closed"); assert.equal(report.events.length, 3);
    await page.evaluate(() => { window.print = () => { window.printWasCalled = true; }; });
    await page.getByRole("button", { name: "Печать отчёта", exact: true }).click();
    await page.waitForFunction(() => window.printWasCalled === true);
    assert.equal(await page.locator("#print-report img").count(), 0);
    if (evidence) {
      await page.screenshot({ path: path.join(evidence, "desktop-review.png"), fullPage: true });
      await page.pdf({ path: path.join(evidence, "synthetic-review.pdf"), format: "A4", printBackground: true });
    }

    await page.getByRole("button", { name: "Сохранить отчёт", exact: true }).click();
    await page.locator("#report-detail .saved-report-note").waitFor();
    assert.equal(await page.locator("#report-detail .saved-report-note").textContent(), note);
    const savedReports = await (await page.request.get(base + "/api/v1/workspace/reports")).json();
    const savedReportId = savedReports.reports[0].report_id;
    for (const extension of ["PDF", "CSV", "JSON"]) {
      const downloading = page.waitForEvent("download");
      await page.getByRole("button", { name: "Скачать " + extension, exact: true }).click();
      const download = await downloading;
      await download.saveAs(path.join(temporary, "saved-report." + extension.toLowerCase()));
    }
    const captured = JSON.parse(fs.readFileSync(path.join(temporary, "saved-report.json"), "utf8"));
    assert.equal(captured.review.review.note, note); assert.equal(captured.observations.length, 12);
    assert.ok(fs.readFileSync(path.join(temporary, "saved-report.pdf")).subarray(0, 4).toString() === "%PDF");
    if (evidence) { await page.screenshot({ path: path.join(evidence, "desktop-saved-report.png"), fullPage: true }); fs.copyFileSync(path.join(temporary, "saved-report.pdf"), path.join(evidence, "saved-report.pdf")); }
    await page.locator('[data-view="reviews"]').click();
    await page.locator("#review-note").fill(note + " Дополнено после сохранения отчёта.");
    await page.getByRole("button", { name: "Сохранить вывод", exact: true }).click();
    await page.waitForFunction(() => document.getElementById("notice").textContent.includes("Версия 4"));
    const frozen = await (await page.request.get(base + "/api/v1/workspace/reports/" + savedReportId)).json();
    assert.equal(frozen.review.review.note, note); assert.equal(frozen.review.review.revision, 3);

    const second = await browser.newContext();
    const register = await second.request.post(base + "/api/v1/auth/register", { headers: { Origin: base }, data: { email: "other@example.test", password: "Synthetic-only-browser-password" } });
    assert.equal(register.status(), 202);
    const otherOutbox = spawnSync(python, ["-m", "arcshift_v1.dev_outbox", "--email", "other@example.test"], { cwd: root, env, encoding: "utf8" });
    assert.equal(otherOutbox.status, 0);
    await second.request.post(base + "/api/v1/auth/verify-email", { headers: { Origin: base }, data: { token: JSON.parse(otherOutbox.stdout).messages[0].token } });
    await second.request.post(base + "/api/v1/auth/login", { headers: { Origin: base }, data: { email: "other@example.test", password: "Synthetic-only-browser-password" } });
    for (const suffix of ["", "/report.json", "/report.csv"]) assert.equal((await second.request.get(base + "/api/v1/workspace/reviews/" + review.review_id + suffix)).status(), 404);
    for (const suffix of ["", "/export.pdf", "/export.csv", "/export.json"]) assert.equal((await second.request.get(base + "/api/v1/workspace/reports/" + savedReportId + suffix)).status(), 404);
    await second.close();

    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      for (const view of ["monitor", "history", "model", "watchlist", "reviews", "reports", "system"]) {
        await page.locator(`[data-view="${view}"]`).click();
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `Horizontal overflow: ${view} at ${width}`);
      }
      await page.locator('[data-view="reports"]').click();
      if (evidence) await page.screenshot({ path: path.join(evidence, `reports-mobile-${width}.png`), fullPage: true });
      await page.locator('[data-view="model"]').click();
      if (evidence) await page.screenshot({ path: path.join(evidence, `model-mobile-${width}.png`), fullPage: true });
      await page.locator('[data-view="history"]').click();
      if (evidence) await page.screenshot({ path: path.join(evidence, `history-mobile-${width}.png`), fullPage: true });
      await page.locator('[data-view="monitor"]').click();
      if (evidence) await page.screenshot({ path: path.join(evidence, `mobile-${width}.png`), fullPage: true });
    }
    await page.setViewportSize({ width: 1440, height: 980 });
    await page.locator('[data-view="reviews"]').click();
    const tab = await context.newPage(); await tab.goto(base);
    await tab.locator("#logout-button:not([hidden])").waitFor();
    await tab.locator('[data-view="reviews"]').click();
    await tab.locator("#review-note").waitFor();
    await tab.locator('[data-view="reports"]').click();
    await tab.locator("#report-detail .saved-report-note").waitFor();
    await page.locator("#logout-button").click();
    await tab.locator("#review-note").waitFor({ state: "detached" });
    await tab.locator("#report-detail .saved-report-note").waitFor({ state: "detached" });
    assert.equal((await page.request.get(base + "/api/v1/workspace/reviews/" + review.review_id + "/report.json")).status(), 401);
    assert.equal(await page.locator("#print-report").textContent(), "");
    assert.equal(await page.locator("#report-detail").textContent(), "");
    assert.equal((await page.request.get(base + "/api/v1/workspace/reports/" + savedReportId + "/export.pdf")).status(), 401);
    await tab.close();
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    await browser.close(); browser = null;
    child.kill("SIGTERM"); await exit; stopped = true;
    return { status: "ok", viewports: [1440, 390, 320], immutable_saved_report_and_private_PDF_verified: true, model_gate_and_no_current_score_verified: true, parser_history_and_revisions_verified: true, full_account_flow: true, watchlist_and_review_persisted: true, report_json_csv_and_print_verified: true, foreign_report_access_blocked: true, cross_tab_logout_cleared_private_state: true, script_injection_blocked: true, external_requests: 0, browser_errors: 0, server_stopped_after_check: true, production_ready: false };
  } finally {
    if (browser) await browser.close();
    if (child && !stopped && child.exitCode === null) {
      child.kill("SIGTERM");
      await Promise.race([new Promise((resolve) => child.once("exit", resolve)), delay(3000)]);
      if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
    }
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

main().then((result) => console.log(JSON.stringify(result, null, 2))).catch((error) => { console.error(error.message); process.exitCode = 1; });
