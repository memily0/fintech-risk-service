"use strict";

const $ = (id) => document.getElementById(id);
const workspacePath = "/api/v1/workspace";
const workspaceLists = { warnings: ["/warnings", "warnings"], seriesWatchlist: ["/series-watchlist", "series_ids"] };
const workspaceList = () => ({ phase: "idle", items: [], request: 0, pending: false });
const state = { view: "monitor", scenarios: [], selected: "historical_demo", user: null, reviews: [], review: null, health: null, authMode: "login", generation: 0, moreReviews: false };
Object.assign(state, { warnings: workspaceList(), seriesWatchlist: workspaceList() });
Object.assign(state, { market: null, marketPhase: "loading", marketGeneration: 0, history: null, historySeriesId: "ru.fx.cbr.usd_rub.official", historyGeneration: 0, historyPhase: "idle" });
Object.assign(state, { model: null, signal: null, modelGeneration: 0, modelLoading: false });
Object.assign(state, { reports: [], report: null, reportId: null, reportLoading: false, moreReports: false });
const blockerLabels = { measurement_not_validated: "Индекс не проверен на реальных данных", sources_not_admitted: "Источники не допущены для модели", source_calendars_not_verified: "Календари источников не подтверждены", mandatory_stress_inputs_incomplete: "Обязательные входы отсутствуют", evaluation_not_run: "Оценка качества модели не выполнена", accepted_artifact_missing: "Принятый артефакт модели отсутствует" };
const componentLabels = { fx: "Валюта: волатильность USD/RUB", equity: "Акции: волатильность и просадка IMOEX", rates: "Ставки: рост доходности ОФЗ 10Y" };
const seriesLabels = { "ru.fx.cbr.usd_rub.official": "USD/RUB · условный курс", "ru.fx.cbr.eur_rub.official": "EUR/RUB · условный курс", "ru.prices.rosstat.cpi_yoy": "Инфляция · условный CPI YoY", "ru.curve.cbr.zero_coupon.1y": "Кривая ОФЗ · условные 1 год", "ru.curve.cbr.zero_coupon.2y": "Кривая ОФЗ · условные 2 года", "ru.curve.cbr.zero_coupon.5y": "Кривая ОФЗ · условные 5 лет", "ru.curve.cbr.zero_coupon.10y": "Кривая ОФЗ · условные 10 лет" };
const unitLabels = { RUB_per_USD: "₽ / USD", RUB_per_EUR: "₽ / EUR", percent_per_annum: "% годовых", percent_YoY: "% г/г" };
const labels = { historical_demo: "Исторический пример", loading: "Получение данных", empty: "История отсутствует", stale: "Данные устарели", unsupported: "Не поддерживается", error: "Источник недоступен" };
const icons = { historical_demo: "chart-no-axes-combined", loading: "loader-circle", empty: "inbox", stale: "clock-3", unsupported: "circle-slash", error: "unplug" };
const statusLabels = { new: "Новое", acknowledged: "Принято", in_review: "В разборе", closed: "Закрыто", dismissed: "Отклонено" };
const moscowTime = new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Moscow" });
const transitions = { acknowledged: ["acknowledged", "in_review", "dismissed"], in_review: ["in_review", "closed", "dismissed"], closed: ["closed"], dismissed: ["dismissed"] };
const accountChannel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("arcshift-local-account");
const messages = { invalid_credentials: "Не удалось войти: проверьте данные и подтверждение почты.", invalid_verification: "Токен недействителен или истёк.", auth_rate_limited: "Слишком много попыток. Повторите через минуту.", invalid_request: "Проверьте поля. Почта должна оканчиваться на .test, пароль — от 15 до 128 символов.", authentication_required: "Сессия истекла. Требуется вход.", review_revision_conflict: "Запись уже изменена. Обновите журнал; ваш текст остался в поле.", invalid_review_transition: "Этот переход статуса недоступен.", csrf_failed: "Сессия изменилась. Войдите повторно.", local_auth_unavailable: "Локальная авторизация недоступна.", local_storage_unavailable: "Хранилище недоступно. Изменения не сохранены.", fixture_store_unavailable: "Данные недоступны. Текущий прогноз не рассчитан." };
Object.assign(messages, { report_snapshot_conflict: "Снимок данных изменился. Обновите данные перед сохранением отчёта.", report_render_unavailable: "Не удалось сформировать PDF. Отчёт сохранён; доступны JSON и CSV.", report_series_not_supported: "Выбранный ряд недоступен для этого отчёта." });

function node(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
}
function icon(name) { const result = node("i"); result.dataset.lucide = name; result.setAttribute("aria-hidden", "true"); return result; }
function updateIcons() { if (window.lucide) window.lucide.createIcons(); }
function button(label, iconName, action, className = "button secondary") {
  const result = node("button", className);
  result.type = "button";
  result.append(icon(iconName));
  if (!className.includes("icon-button")) result.append(node("span", "", label));
  result.title = label; result.setAttribute("aria-label", label);
  result.addEventListener("click", () => run(action, result));
  return result;
}
function notice(text) { $("notice").textContent = text; $("notice").hidden = !text; }
function hasReviewDraft() {
  const note = $("review-note"), status = $("review-status");
  return state.view === "reviews" && state.review && note && status && (note.value !== state.review.note || status.value !== state.review.status);
}
function canLeaveReview() {
  return !hasReviewDraft() || window.confirm("Сбросить несохранённые изменения разбора?");
}
function clearPersonal() {
  state.generation += 1;
  state.user = null; state.warnings = workspaceList(); state.seriesWatchlist = workspaceList(); state.reviews = []; state.review = null; state.moreReviews = false;
  $("warning-queue").replaceChildren(); $("series-watchlist").replaceChildren(); $("watchlist-add").hidden = true;
  $("watchlist-series").replaceChildren(); $("history-watch-action").replaceChildren();
  $("print-report").replaceChildren(); $("review-detail").replaceChildren(); $("review-rows").replaceChildren();
  $("password-input").value = ""; $("token-input").value = "";
  state.reports = []; state.report = null; state.reportId = null; state.reportLoading = false; state.moreReports = false;
  $("report-rows").replaceChildren(); $("report-detail").replaceChildren();
}
async function api(path, { method = "GET", data, blob = false } = {}) {
  const generation = state.generation;
  const headers = {};
  if (data !== undefined) headers["Content-Type"] = "application/json";
  if (!["GET", "HEAD"].includes(method)) {
    const csrf = document.cookie.split("; ").find((value) => value.startsWith("arcshift_dev_csrf="));
    if (csrf) headers["X-CSRF-Token"] = decodeURIComponent(csrf.split("=")[1]);
  }
  let response;
  try { response = await fetch(path, { method, headers, body: data === undefined ? undefined : JSON.stringify(data), credentials: "same-origin", cache: "no-store" }); }
  catch { throw new Error("Нет соединения с локальным сервисом."); }
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    if (response.status === 401 && state.user && generation === state.generation) { clearPersonal(); render(); }
    const code = detail.detail?.code;
    const message = code === "invalid_request" && !path.startsWith("/api/v1/auth/") ? "Проверьте параметры запроса и формат дат." : code === "invalid_date_range" ? "Начало периода должно быть не позже конца." : messages[code];
    const error = new Error(message || "Запрос не выполнен. Код: " + response.status);
    error.status = response.status; throw error;
  }
  if (response.status === 204) return null;
  return blob ? response.blob() : response.json();
}
async function run(action, control) {
  if (control) control.disabled = true;
  try { await action(); }
  catch (error) { notice(error.message); }
  finally { if (control) control.disabled = false; }
}
function detailRow(label, value, mono = false) {
  const row = node("div"); row.append(node("dt", "", label), node("dd", mono ? "mono" : "", String(value ?? "Неизвестно"))); return row;
}
function empty(title, signedOut = false) {
  const result = node("div", "empty-state"); result.append(icon("inbox"), node("h3", "", title));
  if (signedOut) result.append(button("Войти", "log-in", async () => openAuth()));
  return result;
}
function render() {
  const titles = { monitor: "Мониторинг", warnings: "Предупреждения", history: "История рядов", model: "Модель", watchlist: "Наблюдение", reviews: "Разборы", reports: "Отчёты", system: "Состояние системы" };
  $("page-title").textContent = titles[state.view]; document.title = "ArcShift | " + titles[state.view];
  renderWorkspaceSummary();
  document.querySelectorAll("[data-view]").forEach((item) => {
    const active = item.dataset.view === state.view; item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
  $("account-email").textContent = state.user?.email || "";
  $("login-button").hidden = Boolean(state.user); $("logout-button").hidden = !state.user;
  $("review-count").textContent = state.reviews.length + (state.moreReviews ? "+" : "");
  $("report-count").textContent = state.reports.length + (state.moreReports ? "+" : "");
  $("monitor-view").hidden = state.view !== "monitor";
  $("warnings-view").hidden = state.view !== "warnings";
  $("watchlist-view").hidden = state.view !== "watchlist";
  $("reviews-view").hidden = state.view !== "reviews"; $("system-view").hidden = state.view !== "system";
  $("history-view").hidden = state.view !== "history";
  $("model-view").hidden = state.view !== "model";
  $("reports-view").hidden = state.view !== "reports";
  if (state.view === "monitor") renderMonitor();
  if (state.view === "warnings") renderWarnings();
  if (state.view === "watchlist") renderSeriesWatchlist();
  if (state.view === "reviews") renderReviews();
  if (state.view === "system") renderSystem();
  if (state.view === "history") renderHistory();
  if (state.view === "model") renderModel();
  if (state.view === "reports") renderReports();
  updateIcons();
}
function renderMonitor() {
  const search = $("scenario-search").value.toLocaleLowerCase("ru");
  const rows = state.scenarios.filter((row) => (labels[row.id] + row.id).toLocaleLowerCase("ru").includes(search));
  const selected = rows.find((row) => row.id === state.selected) || rows[0];
  if (selected) state.selected = selected.id;
  const container = $("scenario-rows"); container.replaceChildren();
  $("list-empty").hidden = rows.length > 0;
  for (const row of rows) {
    const item = node("button", "scenario-row" + (state.selected === row.id ? " selected" : ""));
    item.type = "button"; item.setAttribute("aria-pressed", String(state.selected === row.id));
    const name = node("span", "scenario-name"), symbol = node("span", "state-icon"), text = node("span");
    symbol.append(icon(icons[row.id])); text.append(node("strong", "", labels[row.id]), node("small", "", row.id)); name.append(symbol, text);
    item.append(name, node("span", "score-cell", row.signal ? row.signal.score.toFixed(2) : "—"), node("span", "state-label", row.signal ? "Только пример" : "Нет сигнала"));
    item.addEventListener("click", () => { state.selected = row.id; renderMonitor(); }); container.append(item);
  }
  if (selected) { state.selected = selected.id; renderScenario(selected); } else $("scenario-detail").replaceChildren();
  updateIcons();
}
function renderScenario(row) {
  const panel = $("scenario-detail"); panel.replaceChildren();
  const heading = node("div", "detail-heading"), title = node("div");
  title.append(node("h2", "", labels[row.id]), node("p", "detail-subtitle", "Россия · synthetic / v1-handoff.1"));
  heading.append(title); panel.append(heading);
  const signal = node("div", "signal-area"), score = node("div");
  score.append(node("div", "signal-number" + (row.signal ? "" : " unavailable"), row.signal ? row.signal.score.toFixed(2) : "Недоступен"));
  score.append(node("p", "signal-caption", row.signal ? "Синтетический некалиброванный score" : "Текущий прогноз не рассчитан"));
  signal.append(score, node("span", "signal-tag", row.signal ? "Не вероятность кризиса" : "Нет допустимого сигнала")); panel.append(signal, node("p", "detail-message", row.message));
  const evidence = node("dl", "evidence-list");
  evidence.append(detailRow("Режим", "Синтетические данные"), detailRow("Допуск источников", "Не подтверждён"));
  if (row.signal) evidence.append(detailRow("Горизонт примера", "30 календарных дней"), detailRow("Данные на", new Date(row.signal.information_as_of).toLocaleString("ru-RU")), detailRow("Версия модели", row.signal.model_version, true), detailRow("Snapshot примера", row.signal.snapshot_id, true), detailRow("Валидация", "Не выполнена"), detailRow("Драйверы", "Отсутствуют"));
  panel.append(evidence);
  const actions = node("div", "detail-actions");
  actions.append(button("Начать разбор", "clipboard-plus", async () => {
    if (!state.user) return openAuth();
    const generation = state.generation;
    const review = await api("/api/v1/workspace/reviews", { method: "POST", data: { scenario_id: row.id, note: "" } });
    if (generation !== state.generation) return;
    state.review = review; state.view = "reviews"; await loadPrivate(); render();
  }, "button primary")); panel.append(actions);
}
function renderWorkspaceSummary() {
  const phaseLabels = { idle: "Загрузка", loading: "Загрузка", error: "Недоступно" };
  let value = "6 состояний", caption = "Фиксированный снимок";
  if (state.view === "warnings" || state.view === "watchlist") {
    const list = state.view === "warnings" ? state.warnings : state.seriesWatchlist;
    value = !state.user ? "Требуется вход" : list.phase === "ready" ? String(list.items.length) : phaseLabels[list.phase];
    caption = state.view === "warnings" ? "Тестовые предупреждения" : "Ряды в личном списке";
  } else if (state.view === "history") {
    value = state.market ? "Рядов: " + state.market.series.length : phaseLabels[state.marketPhase];
    caption = "Синтетический каталог";
  }
  $("data-summary-value").textContent = value;
  $("data-summary-caption").textContent = caption;
  const counts = [["warning-count", state.warnings, state.warnings.items.filter((item) => item.review_status === "new").length],
    ["watch-count", state.seriesWatchlist, state.seriesWatchlist.items.length]];
  for (const [id, list, count] of counts) {
    $(id).hidden = !state.user || list.phase !== "ready" || count === 0;
    $(id).textContent = $(id).hidden ? "" : String(count);
  }
}
function renderWorkspaceList(key) {
  renderWorkspaceSummary();
  if (key === "warnings" && state.view === "warnings") renderWarnings();
  if (key === "seriesWatchlist" && state.view === "watchlist") renderSeriesWatchlist();
  if (key === "seriesWatchlist" && state.view === "history") renderHistoryBookmark();
  updateIcons();
}
function workspaceListPlaceholder(key, title, emptyTitle) {
  const list = state[key];
  if (!state.user) return empty(title, true);
  if (list.phase === "idle" || list.phase === "loading") {
    const status = node("p", "detail-message", "Загрузка…"); status.setAttribute("role", "status"); return status;
  }
  if (list.phase === "error") {
    const status = empty("Не удалось загрузить список");
    status.append(button("Повторить", "refresh-cw", () => loadWorkspaceList(key)));
    return status;
  }
  return list.items.length ? null : empty(emptyTitle);
}
async function loadWorkspaceList(key) {
  if (!state.user) return;
  const list = state[key];
  if (list.pending) return;
  const request = ++list.request;
  const [path, field] = workspaceLists[key];
  list.phase = "loading"; renderWorkspaceList(key);
  try {
    const payload = await api(workspacePath + path);
    if (list === state[key] && request === list.request) {
      list.items = payload[field]; list.phase = "ready";
    }
  } catch {
    if (list === state[key] && request === list.request) list.phase = "error";
  } finally {
    if (list === state[key] && request === list.request) renderWorkspaceList(key);
  }
}
function renderWarnings() {
  const container = $("warning-queue"); container.replaceChildren();
  const placeholder = workspaceListPlaceholder("warnings", "Личная очередь предупреждений", "Предупреждений нет");
  if (placeholder) { container.append(placeholder); return; }
  const rows = node("ul", "workspace-rows");
  for (const warning of state.warnings.items) {
    const row = node("li", "workspace-row warning-row"), title = node("div");
    const label = "Эпизод " + warning.event_key.replace(/^episode-/, "");
    title.append(node("strong", "", label), node("small", "", moscowTime.format(new Date(warning.occurred_at)) + " МСК"));
    const actions = node("div", "workspace-row-actions"), status = node("span", "warning-status", statusLabels[warning.review_status]);
    status.dataset.status = warning.review_status;
    const action = warning.review_id ? "Открыть разбор" : "Начать разбор";
    const control = button(action, warning.review_id ? "arrow-right" : "clipboard-plus", () => openWarningReview(warning));
    control.setAttribute("aria-label", action + ": " + label);
    actions.append(status, control); row.append(title, actions); rows.append(row);
  }
  container.append(rows);
}
function reflectWarningReview(review) {
  if (!review.warning) return;
  const list = state.warnings;
  list.items = list.items.map((item) => item.warning_id === review.warning.warning_id ?
    { ...item, review_id: review.review_id, review_status: review.status } : item);
}
async function openWarningReview(warning) {
  const list = state.warnings;
  if (!state.user || list.phase !== "ready" || list.pending) return;
  list.pending = true;
  try {
    const review = warning.review_id ? await api(workspacePath + "/reviews/" + encodeURIComponent(warning.review_id)) :
      await api(workspacePath + "/warnings/" + encodeURIComponent(warning.warning_id) + "/review", { method: "PUT" });
    if (list !== state.warnings) return;
    reflectWarningReview(review);
    let listError;
    try { await loadPrivate(); } catch (error) { listError = error; }
    if (list !== state.warnings || state.view !== "warnings") return;
    state.review = review; state.view = "reviews"; render(); $("page-title").focus();
    if (listError) notice(listError.message);
  } finally {
    if (list === state.warnings) { list.pending = false; renderWorkspaceList("warnings"); }
  }
}
function renderSeriesWatchlist() {
  const container = $("series-watchlist"), list = state.seriesWatchlist;
  const picker = $("watchlist-series"), selected = picker.value;
  container.replaceChildren(); picker.replaceChildren();
  const available = state.market?.series.filter((series) => !list.items.includes(series.series_id)) || [];
  $("watchlist-add").hidden = !state.user || list.phase !== "ready" || available.length === 0;
  if (!$("watchlist-add").hidden) {
    for (const series of available) {
      const option = node("option", "", seriesLabels[series.series_id] || series.series_id);
      option.value = series.series_id; picker.append(option);
    }
    if (available.some((series) => series.series_id === selected)) picker.value = selected;
  }
  const placeholder = workspaceListPlaceholder("seriesWatchlist", "Личный список рядов", "Список наблюдения пуст");
  if (placeholder) container.append(placeholder);
  if (state.user && list.phase === "ready" && state.marketPhase !== "ready") {
    const message = state.marketPhase === "loading" ? "Загрузка каталога…" : "Каталог рядов недоступен";
    container.append(node("p", "detail-message", message));
  }
  if (placeholder) return;
  const rows = node("ul", "workspace-rows");
  for (const id of list.items) {
    const series = state.market?.series.find((item) => item.series_id === id);
    const label = seriesLabels[id] || id;
    const row = node("li", "workspace-row series-row"), title = node("div"), actions = node("div", "workspace-row-actions");
    title.append(node("strong", "", label), node("small", "mono", id));
    if (series) {
      title.append(node("small", "", "Последний период: " + series.latest_reference_end));
      const history = button("История", "table-2", () => openSeriesHistory(id));
      history.setAttribute("aria-label", "История: " + label); actions.append(history);
    } else if (state.marketPhase === "ready") title.append(node("small", "", "Нет в активном снимке"));
    actions.append(button("Убрать из наблюдения: " + label, "bookmark-minus", () => updateSeriesWatchlist(id, false), "icon-button"));
    row.append(title, actions); rows.append(row);
  }
  container.append(rows);
}
async function updateSeriesWatchlist(id, add) {
  const list = state.seriesWatchlist;
  if (!state.user || list.phase !== "ready" || list.pending || !id) return;
  const selected = new Set(list.items);
  if (selected.has(id) === add) return;
  if (add) selected.add(id); else selected.delete(id);
  list.pending = true;
  try {
    const result = await api(workspacePath + "/series-watchlist", { method: "PUT", data: { series_ids: [...selected] } });
    if (list !== state.seriesWatchlist) return;
    list.items = result.series_ids;
    renderWorkspaceList("seriesWatchlist");
    if (state.view === "watchlist") {
      const focus = !$("watchlist-add").hidden ? $("watchlist-series") : $("series-watchlist").querySelector("button") || $("page-title");
      focus.focus();
    } else if (state.view === "history") $("history-watch-action").querySelector("button")?.focus();
  } finally { list.pending = false; }
}
function renderReviews() {
  const rows = $("review-rows"); rows.replaceChildren();
  $("more-reviews").hidden = !state.moreReviews;
  if (!state.user) { rows.append(empty("Личный журнал", true)); $("review-detail").replaceChildren(); return; }
  if (!state.reviews.length) rows.append(empty("Разборов пока нет"));
  if (!state.review && state.reviews.length) state.review = state.reviews[0];
  for (const review of state.reviews) {
    const item = node("button", "review-row" + (state.review?.review_id === review.review_id ? " selected" : ""));
    item.type = "button";
    const name = node("span"); name.append(node("strong", "", reviewTitle(review)), node("small", "", new Date(review.updated_at * 1000).toLocaleString("ru-RU") + " · Версия " + review.revision));
    item.append(name, node("span", "state-label", statusLabels[review.status]));
    item.addEventListener("click", () => { if (!canLeaveReview()) return; state.review = review; renderReviews(); updateIcons(); }); rows.append(item);
  }
  renderReview();
}
function reviewTitle(review) {
  return review.warning ? "Тестовое предупреждение · " + review.warning.event_key : labels[review.scenario.id];
}
function renderReview() {
  const panel = $("review-detail"), review = state.review; panel.replaceChildren();
  if (!review) return;
  const heading = node("div", "detail-heading"), title = node("div"); title.append(node("h2", "", reviewTitle(review)), node("p", "detail-subtitle", "Зафиксированный synthetic snapshot")); heading.append(title); panel.append(heading);
  const evidence = node("dl", "evidence-list"); evidence.append(detailRow("Разбор", review.review_id, true), detailRow("Snapshot", review.snapshot_id, true));
  if (review.warning) evidence.append(detailRow("Снимок рынка", review.warning.data_snapshot_id, true));
  else evidence.append(detailRow("Score", review.scenario.signal ? review.scenario.signal.score.toFixed(2) + " · не калиброван" : "Недоступен"));
  panel.append(evidence);
  const form = node("form", "review-form"), statusLabel = node("label", "", "Статус"), select = node("select"), noteLabel = node("label", "", "Вывод аналитика"), textarea = node("textarea");
  select.name = "status"; select.id = "review-status";
  for (const value of transitions[review.status]) { const option = node("option", "", statusLabels[value]); option.value = value; option.selected = value === review.status; select.append(option); }
  statusLabel.append(select); textarea.value = review.note; textarea.maxLength = 4000; textarea.id = "review-note"; textarea.name = "note"; noteLabel.append(textarea);
  const save = node("button", "button primary"); save.type = "submit"; save.append(icon("save"), node("span", "", "Сохранить вывод"));
  form.append(statusLabel, noteLabel, save);
  form.addEventListener("submit", (event) => { event.preventDefault(); run(async () => {
    const generation = state.generation;
    const updated = await api("/api/v1/workspace/reviews/" + review.review_id, { method: "PATCH", data: { expected_revision: review.revision, status: select.value, note: textarea.value } });
    if (generation !== state.generation) return;
    reflectWarningReview(updated);
    if (updated.warning) void loadWorkspaceList("warnings");
    state.review = updated; await loadPrivate(); render(); notice("Вывод сохранён. Версия " + updated.revision + ".");
  }, save); }); panel.append(form);
  const exports = node("div", "detail-actions");
  exports.append(button("Сохранить отчёт", "file-plus-2", async () => {
    if (!canLeaveReview()) return;
    const snapshotId = review.warning?.data_snapshot_id ?? state.market?.data_snapshot_id;
    if (!snapshotId) throw new Error("Снимок данных недоступен.");
    const generation = state.generation;
    const saved = await api("/api/v1/workspace/reports", { method: "POST", data: { review_id: review.review_id, expected_revision: review.revision, expected_data_snapshot_id: snapshotId } });
    if (generation !== state.generation) return;
    state.report = saved; state.reportId = saved.report_id; await loadPrivate(); state.view = "reports"; render(); notice("Отчёт сохранён. Версия разбора " + saved.review.review.revision + ".");
  }, "button primary"));
  for (const extension of ["json", "csv"]) exports.append(button("Скачать " + extension.toUpperCase(), "download", async () => {
    const generation = state.generation;
    const content = await api("/api/v1/workspace/reviews/" + review.review_id + "/report." + extension, { blob: true });
    if (generation !== state.generation) return;
    const url = URL.createObjectURL(content), link = node("a"); link.href = url; link.download = "arcshift-review-" + review.review_id + "." + extension;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }));
  exports.append(button("Печать отчёта", "printer", async () => {
    const generation = state.generation;
    const report = await api("/api/v1/workspace/reviews/" + review.review_id + "/report.json");
    if (generation !== state.generation) return;
    buildPrint(report); window.print();
  }, "icon-button")); panel.append(exports, node("p", "review-meta", "Синтетический разбор. Закрытие не подтверждает точность модели."));
}
function buildPrint(report) {
  const container = $("print-report"), review = report.review; container.replaceChildren();
  container.append(node("h1", "", "ArcShift · Отчёт по разбору"), node("p", "", "СИНТЕТИЧЕСКИЕ ДАННЫЕ · НЕ ТЕКУЩИЙ ПРОГНОЗ"));
  const details = node("dl"); details.append(detailRow("Разбор", review.review_id), detailRow("Snapshot", review.snapshot_id), detailRow("Состояние", reviewTitle(review)), detailRow("Статус", statusLabels[review.status]), detailRow("Версия", review.revision), detailRow("Обновлено", new Date(review.updated_at * 1000).toLocaleString("ru-RU")), detailRow("Допуск источников", "Не подтверждён"));
  if (review.warning) details.append(detailRow("Снимок рынка", review.warning.data_snapshot_id));
  else details.append(detailRow("Score", review.scenario.signal?.score ?? "Недоступен"));
  container.append(details, node("h2", "", "Вывод аналитика"), node("p", "", review.note || "Не указан"), node("h2", "", "Журнал изменений"));
  for (const event of report.events) container.append(node("p", "", "v" + event.revision + " · " + statusLabels[event.status] + " · " + new Date(event.occurred_at * 1000).toLocaleString("ru-RU")));
  container.append(node("p", "", "Отчёт фиксирует тестовый рабочий процесс, а не валидацию модели или оценку текущего кризисного риска."));
}
function renderSystem() {
  const details = $("system-details"); details.replaceChildren();
  details.append(detailRow("API", state.health?.status === "ok" ? "Доступен" : "Недоступен"), detailRow("Контракт данных", "v1-fixture.1"), detailRow("Контракт аккаунтов", "v1-local-auth.1"), detailRow("Контракт разбора", "v1-local-workspace.1"), detailRow("Контур", "Локальная synthetic-сборка"), detailRow("Источник данных", "Синтетические fixtures"), detailRow("Live-обновление", "Не подключено"), detailRow("Модель", "Не допущена"), detailRow("Публичный запуск", "Не допущен"));
}
function renderHistory() {
  const select = $("history-series"), catalog = state.market?.series || [];
  if (catalog.length !== select.options.length || catalog.some((series, index) => select.options[index]?.value !== series.series_id)) {
    select.replaceChildren();
    for (const series of catalog) { const option = node("option", "", seriesLabels[series.series_id] || series.series_id); option.value = series.series_id; select.append(option); }
  }
  select.value = state.historySeriesId || ""; select.disabled = catalog.length === 0;
  const metadata = $("history-metadata"), rows = $("history-rows"); metadata.replaceChildren(); rows.replaceChildren();
  const selected = catalog.find((series) => series.series_id === state.historySeriesId);
  if (selected) metadata.append(detailRow("Источник кандидата", selected.source_id), detailRow("Ресурс", selected.resource_id, true), detailRow("Версия данных", state.market.data_snapshot_id, true), detailRow("Последний период", selected.latest_reference_end), detailRow("Допуск", "Не подтверждён · только синтетика"));
  const historyStatus = { idle: "Нет рядов в снимке", loading: "Получение сохранённого снимка", error: "История недоступна", changed: "Снимок изменился. Обновите данные." };
  $("history-status").textContent = state.marketPhase === "loading" ? "Загрузка каталога…" : state.marketPhase === "error" ? "Каталог рядов недоступен" :
    state.history ? "Записей: " + state.history.total + (state.history.total > state.history.observations.length ? " · показаны первые " + state.history.observations.length : "") : historyStatus[state.historyPhase];
  if (state.history) for (const revision of state.history.observations) {
    const observation = revision.observation, tr = node("tr", revision.is_latest ? "" : "superseded");
    const period = observation.reference_start === observation.reference_end ? observation.reference_start : observation.reference_start + " — " + observation.reference_end;
    const values = [period, observation.value.toLocaleString("ru-RU"), unitLabels[observation.units] || observation.units, observation.published_at ? new Date(observation.published_at).toLocaleString("ru-RU") : "Неизвестно", new Date(observation.received_at).toLocaleString("ru-RU"), "r" + revision.revision_number + (revision.is_latest ? " · текущая" : " · заменена")];
    for (const value of values) tr.append(node("td", "", value)); rows.append(tr);
  }
  renderHistoryBookmark(); updateIcons();
}
function renderHistoryBookmark() {
  const slot = $("history-watch-action"), list = state.seriesWatchlist, id = state.historySeriesId;
  slot.replaceChildren();
  if (!state.market?.series.some((series) => series.series_id === id) || (state.user && list.phase !== "ready")) return;
  const saved = list.items.includes(id);
  slot.append(button(saved ? "Убрать ряд из наблюдения" : "Наблюдать за рядом", saved ? "bookmark-check" : "bookmark",
    () => state.user ? updateSeriesWatchlist(id, !saved) : openAuth(), "icon-button" + (saved ? " saved" : "")));
}
async function openSeriesHistory(id) {
  state.historySeriesId = id; state.history = null; state.historyPhase = "loading";
  state.view = "history"; notice(""); render(); $("page-title").focus();
  await loadHistory();
}
async function loadMarket() {
  const generation = ++state.marketGeneration;
  ++state.historyGeneration;
  state.market = null; state.marketPhase = "loading"; state.history = null; state.historyPhase = "idle";
  if (state.view === "history") { renderWorkspaceSummary(); renderHistory(); }
  renderWorkspaceList("seriesWatchlist");
  try {
    const catalog = await api("/api/v1/market/series");
    if (generation !== state.marketGeneration) return;
    state.market = catalog; state.marketPhase = "ready";
    if (!catalog.series.some((series) => series.series_id === state.historySeriesId)) state.historySeriesId = catalog.series[0]?.series_id || null;
  } catch (error) {
    if (generation !== state.marketGeneration) return;
    state.marketPhase = "error";
    throw error;
  } finally {
    if (generation === state.marketGeneration) {
      renderWorkspaceList("seriesWatchlist");
      if (state.view === "history") renderHistory();
    }
  }
  await loadHistory();
}
async function loadHistory() {
  const series = state.historySeriesId, snapshot = state.market?.data_snapshot_id;
  if (!series || !snapshot) return;
  const generation = ++state.historyGeneration;
  const params = new URLSearchParams({ limit: "500", include_revisions: String($("history-revisions").checked) });
  if ($("history-start").value) params.set("start", $("history-start").value);
  if ($("history-end").value) params.set("end", $("history-end").value);
  state.historyPhase = "loading"; state.history = null;
  if (state.view === "history") renderHistory();
  try {
    const result = await api("/api/v1/market/series/" + encodeURIComponent(series) + "/history?" + params);
    if (generation !== state.historyGeneration) return;
    if (result.data_snapshot_id !== snapshot || result.series_id !== series) state.historyPhase = "changed";
    else { state.history = result; state.historyPhase = "ready"; }
  } catch (error) {
    if (generation !== state.historyGeneration) return;
    state.historyPhase = "error";
    throw error;
  } finally { if (generation === state.historyGeneration && state.view === "history") renderHistory(); }
}
function renderModel() {
  const metadata = $("model-metadata"), blockers = $("model-blockers"), inputs = $("model-inputs"); metadata.replaceChildren(); blockers.replaceChildren(); inputs.replaceChildren();
  $("current-signal-state").textContent = state.modelLoading ? "Проверка статуса" : "Недоступен";
  if (!state.model) return;
  const definition = state.model.measurement;
  const threshold = definition.segment_threshold.toLocaleString("ru-RU", { minimumFractionDigits: 2 });
  metadata.append(detailRow("Задача", "Новый эпизод рыночного стресса в России"), detailRow("Постановка задачи", "Утверждена; модель не допущена"), detailRow("Горизонт постановки", state.model.primary_horizon_days + " календарных дней"), detailRow("Условие прогноза", "Только при известном отсутствии стресса"), detailRow("Измерение цели", "Методика зафиксирована; не валидирована"), detailRow("Условие стресса", `${definition.required_segments} из ${definition.mandatory_segments.length} сегментов с рангом от ${threshold}`), detailRow("Отсечка данных", `${String(definition.cutoff_hour).padStart(2, "0")}:00 МСК; данные за предыдущие даты`), detailRow("Определение цели", state.model.target_definition_id, true), detailRow("Калибровка", "Не установлена"), detailRow("Снимок данных", state.model.data_snapshot_id, true), detailRow("Модельный контракт", state.model.model_contract_version, true));
  for (const reason of state.model.blockers) blockers.append(node("li", "", blockerLabels[reason] || reason));
  for (const item of state.model.input_coverage) {
    const row = node("div", "model-input-row"), name = node("div");
    name.append(node("strong", "", componentLabels[item.component] || item.component), node("small", "mono", item.required_series.join(" / ")));
    row.append(name, node("span", "", item.present_in_synthetic_snapshot ? "Есть только synthetic" : "Нет в снимке")); inputs.append(row);
  }
}
async function loadModel() {
  const generation = ++state.modelGeneration;
  state.modelLoading = true; state.model = null; state.signal = null; renderModel();
  try {
    const [profile, signal, measurement] = await Promise.all([api("/api/v1/models/status"), api("/api/v1/signals/current?horizon_days=" + $("model-horizon").value), api("/api/v1/models/measurement")]);
    if (profile.data_snapshot_id !== signal.data_snapshot_id) throw new Error("Версии данных статуса и сигнала различаются. Обновите проверку.");
    if (signal.signal !== null || profile.accepted_artifact_available !== false) throw new Error("Ответ не соответствует текущему недопущенному model contract.");
    if (profile.task_id !== signal.task_id || profile.measurement_sha256 !== measurement.measurement_sha256 || profile.target_definition_id !== measurement.definition.target_definition_id) throw new Error("Версии задачи и методики различаются. Обновите проверку.");
    if (generation === state.modelGeneration) { state.model = { ...profile, measurement: measurement.definition }; state.signal = signal; }
  } finally { if (generation === state.modelGeneration) { state.modelLoading = false; renderModel(); } }
}
async function loadPrivate(append = false) {
  if (!state.user) return;
  const generation = state.generation;
  const [reviews, reports] = await Promise.all([api("/api/v1/workspace/reviews?limit=50&offset=" + (append ? state.reviews.length : 0)), api("/api/v1/workspace/reports?limit=50")]);
  if (generation !== state.generation || !state.user) return;
  state.reviews = append ? [...state.reviews, ...reviews.reviews] : reviews.reviews;
  state.moreReviews = reviews.reviews.length === 50;
  state.reports = reports.reports; state.moreReports = reports.reports.length === 50;
  if (state.review && !hasReviewDraft()) state.review = state.reviews.find((item) => item.review_id === state.review.review_id) || state.review;
}
async function loadAccountWorkspace() {
  await Promise.all([loadPrivate(), loadWorkspaceList("warnings"), loadWorkspaceList("seriesWatchlist")]);
}
async function openSavedReport(id) {
  if (!state.user) return;
  const generation = state.generation;
  state.reportId = id; state.report = null; state.reportLoading = true; renderReports();
  try {
    const report = await api("/api/v1/workspace/reports/" + id);
    if (generation === state.generation && state.reportId === id) state.report = report;
  } finally { if (generation === state.generation && state.reportId === id) { state.reportLoading = false; renderReports(); updateIcons(); } }
}
function renderReports() {
  const rows = $("report-rows"), detail = $("report-detail"); rows.replaceChildren(); detail.replaceChildren();
  $("more-reports").hidden = !state.moreReports;
  if (!state.user) { rows.append(empty("Личные отчёты", true)); return; }
  if (!state.reports.length) { rows.append(empty("Сохранённых отчётов пока нет")); return; }
  if (!state.reportId && !state.reportLoading) { run(() => openSavedReport(state.reports[0].report_id)); return; }
  for (const summary of state.reports) {
    const row = node("button", "review-row" + (summary.report_id === state.reportId ? " selected" : "")), title = node("span");
    title.append(node("strong", "", "Отчёт " + summary.report_id.slice(0, 8)), node("small", "", new Date(summary.created_at * 1000).toLocaleString("ru-RU") + " · Разбор v" + summary.review_revision));
    row.append(title, node("span", "state-label", summary.observation_count + " наблюдений"));
    row.addEventListener("click", () => run(() => openSavedReport(summary.report_id))); rows.append(row);
  }
  if (state.reportLoading) { detail.append(node("p", "detail-message", "Получение сохранённого отчёта")); return; }
  const report = state.report;
  if (!report) return;
  detail.append(node("h2", "", "Зафиксированный разбор"), node("p", "detail-subtitle", "Синтетический отчёт · Не текущий прогноз"));
  const metadata = node("dl", "evidence-list"), review = report.review.review;
  metadata.append(detailRow("Отчёт", report.report_id, true), detailRow("Версия разбора", review.revision), detailRow("Статус", statusLabels[review.status]), detailRow("Снимок данных", report.data_snapshot_id, true), detailRow("Наблюдений / ревизий", report.observations.length), detailRow("Источники", "Не допущены · Только synthetic"));
  if (review.warning) metadata.append(detailRow("Тестовое предупреждение", review.warning.event_key));
  detail.append(metadata, node("p", "saved-report-note", review.note || "Вывод не указан"));
  const actions = node("div", "detail-actions");
  for (const extension of ["pdf", "csv", "json"]) actions.append(button("Скачать " + extension.toUpperCase(), "download", async () => {
    const generation = state.generation;
    const blob = await api("/api/v1/workspace/reports/" + report.report_id + "/export." + extension, { blob: true });
    if (generation !== state.generation) return;
    const url = URL.createObjectURL(blob), link = node("a"); link.href = url; link.download = "arcshift-report-" + report.report_id + "." + extension;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  })); detail.append(actions); updateIcons();
}
async function checkConnection() {
  try { state.health = await api("/readyz"); $("connection-state").textContent = "API доступен"; $("checked-at").textContent = "API: " + new Date().toLocaleTimeString("ru-RU"); }
  catch (error) { state.health = null; $("connection-state").textContent = "API недоступен"; throw error; }
}
function authTab(mode) {
  state.authMode = mode; const verify = mode === "verify-email";
  document.querySelectorAll("[data-auth]").forEach((item) => { item.classList.toggle("selected", item.dataset.auth === mode); item.setAttribute("aria-selected", String(item.dataset.auth === mode)); });
  $("credential-fields").hidden = verify; $("token-field").hidden = !verify;
  $("email-input").required = !verify; $("password-input").required = !verify; $("token-input").required = verify;
  $("password-input").autocomplete = mode === "register" ? "new-password" : "current-password";
  const text = mode === "login" ? "Войти" : mode === "register" ? "Зарегистрироваться" : "Подтвердить";
  $("auth-submit").replaceChildren(icon(mode === "login" ? "log-in" : "check"), node("span", "", text)); $("auth-status").textContent = ""; updateIcons();
}
function openAuth() { authTab("login"); $("auth-dialog").showModal(); }
document.querySelectorAll("[data-view]").forEach((item) => item.addEventListener("click", () => { if (!canLeaveReview()) return; state.view = item.dataset.view; notice(""); render(); }));
document.querySelectorAll("[data-auth]").forEach((item) => item.addEventListener("click", () => authTab(item.dataset.auth)));
$("login-button").addEventListener("click", openAuth);
$("close-auth").addEventListener("click", () => $("auth-dialog").close());
$("auth-dialog").addEventListener("close", () => { $("password-input").value = ""; $("token-input").value = ""; });
$("scenario-search").addEventListener("input", renderMonitor);
$("watchlist-add").addEventListener("submit", (event) => {
  event.preventDefault(); run(() => updateSeriesWatchlist($("watchlist-series").value, true), $("watchlist-submit"));
});
$("history-series").addEventListener("change", () => { state.historySeriesId = $("history-series").value; run(loadHistory); });
for (const id of ["history-start", "history-end", "history-revisions"]) $(id).addEventListener("change", () => run(loadHistory));
$("model-horizon").addEventListener("change", () => run(loadModel));
$("logout-button").addEventListener("click", () => run(async () => { if (!canLeaveReview()) return; await api("/api/v1/auth/logout", { method: "POST" }); clearPersonal(); accountChannel?.postMessage("changed"); state.view = "monitor"; render(); notice("Вы вышли из аккаунта."); }, $("logout-button")));
$("more-reviews").addEventListener("click", () => run(async () => { await loadPrivate(true); render(); }, $("more-reviews")));
$("more-reports").addEventListener("click", () => run(async () => {
  const generation = state.generation;
  const result = await api("/api/v1/workspace/reports?limit=50&offset=" + state.reports.length);
  if (generation !== state.generation) return;
  state.reports.push(...result.reports); state.moreReports = result.reports.length === 50; render();
}, $("more-reports")));
$("refresh-button").addEventListener("click", () => run(async () => {
  if (!canLeaveReview()) return;
  if (hasReviewDraft()) { renderReview(); updateIcons(); }
  await refreshWorkspace(loadAccountWorkspace);
}, $("refresh-button")));
$("auth-form").addEventListener("submit", (event) => {
  event.preventDefault(); const submit = $("auth-submit"); submit.disabled = true;
  (async () => {
    try {
      const mode = state.authMode;
      const data = mode === "verify-email" ? { token: $("token-input").value } : { email: $("email-input").value, password: $("password-input").value };
      await api("/api/v1/auth/" + mode, { method: "POST", data });
      $("password-input").value = ""; $("token-input").value = "";
      if (mode === "register") { authTab("verify-email"); $("auth-status").textContent = "Заявка принята. Доставка: локальный тестовый outbox."; }
      else if (mode === "verify-email") { authTab("login"); $("auth-status").textContent = "Тестовая почта подтверждена."; }
      else {
        clearPersonal(); const generation = state.generation;
        const user = await api("/api/v1/auth/me");
        if (generation !== state.generation) return;
        state.user = user; await loadAccountWorkspace();
        if (generation !== state.generation) return;
        accountChannel?.postMessage("changed"); $("auth-dialog").close(); render(); notice("");
      }
    } catch (error) { $("auth-status").textContent = error.message; }
    finally { submit.disabled = false; }
  })();
});
async function refreshWorkspace(accountTask) {
  const outcomes = await Promise.allSettled([
    (async () => { state.scenarios = (await api("/api/v1/demo/scenarios")).scenarios; })(),
    checkConnection(), loadMarket(), loadModel(), accountTask(),
  ]);
  const failed = outcomes.find((result) => result.status === "rejected");
  if (!hasReviewDraft()) render();
  notice(failed ? failed.reason.message : "");
}
async function syncIdentity() {
  const generation = state.generation;
  try {
    const user = await api("/api/v1/auth/me");
    if (generation === state.generation && user.user_id !== state.user?.user_id) {
      clearPersonal(); state.user = user; await loadAccountWorkspace(); render();
    }
  } catch (error) { if (error.status !== 401) throw error; }
}
if (accountChannel) accountChannel.addEventListener("message", () => { clearPersonal(); render(); run(syncIdentity); });
setInterval(() => { if (!document.hidden) run(async () => { await checkConnection(); await syncIdentity(); }); }, 30000);
window.addEventListener("focus", () => run(syncIdentity));
window.addEventListener("beforeunload", (event) => {
  if (hasReviewDraft()) { event.preventDefault(); event.returnValue = ""; }
});
updateIcons();
run(() => refreshWorkspace(syncIdentity));
