"use strict";

const $ = (id) => document.getElementById(id);
const state = { view: "monitor", scenarios: [], selected: "historical_demo", user: null, watchlist: [], reviews: [], review: null, health: null, authMode: "login", generation: 0, moreReviews: false };
Object.assign(state, { market: null, history: null, historyGeneration: 0, historyLoading: false });
const seriesLabels = { "ru.fx.cbr.usd_rub.official": "USD/RUB · условный курс", "ru.fx.cbr.eur_rub.official": "EUR/RUB · условный курс", "ru.prices.rosstat.cpi_yoy": "Инфляция · условный CPI YoY", "ru.curve.cbr.zero_coupon.1y": "Кривая ОФЗ · условные 1 год", "ru.curve.cbr.zero_coupon.2y": "Кривая ОФЗ · условные 2 года", "ru.curve.cbr.zero_coupon.5y": "Кривая ОФЗ · условные 5 лет", "ru.curve.cbr.zero_coupon.10y": "Кривая ОФЗ · условные 10 лет" };
const unitLabels = { RUB_per_USD: "₽ / USD", RUB_per_EUR: "₽ / EUR", percent_per_annum: "% годовых", percent_YoY: "% г/г" };
const labels = { historical_demo: "Исторический пример", loading: "Получение данных", empty: "История отсутствует", stale: "Данные устарели", unsupported: "Не поддерживается", error: "Источник недоступен" };
const icons = { historical_demo: "chart-no-axes-combined", loading: "loader-circle", empty: "inbox", stale: "clock-3", unsupported: "circle-slash", error: "unplug" };
const statusLabels = { acknowledged: "Принят", in_review: "В разборе", closed: "Закрыт", dismissed: "Отклонён" };
const transitions = { acknowledged: ["acknowledged", "in_review", "dismissed"], in_review: ["in_review", "closed", "dismissed"], closed: ["closed"], dismissed: ["dismissed"] };
const accountChannel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("arcshift-local-account");
const messages = { invalid_credentials: "Не удалось войти: проверьте данные и подтверждение почты.", invalid_verification: "Токен недействителен или истёк.", auth_rate_limited: "Слишком много попыток. Повторите через минуту.", invalid_request: "Проверьте поля. Почта должна оканчиваться на .test, пароль — от 15 до 128 символов.", authentication_required: "Сессия истекла. Требуется вход.", review_revision_conflict: "Запись уже изменена. Обновите журнал; ваш текст остался в поле.", invalid_review_transition: "Этот переход статуса недоступен.", csrf_failed: "Сессия изменилась. Войдите повторно.", local_auth_unavailable: "Локальная авторизация недоступна.", local_storage_unavailable: "Хранилище недоступно. Изменения не сохранены.", fixture_store_unavailable: "Данные недоступны. Текущий прогноз не рассчитан." };

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
function canLeaveReview() {
  const note = $("review-note"), status = $("review-status");
  const dirty = state.view === "reviews" && state.review && note && (note.value !== state.review.note || status.value !== state.review.status);
  return !dirty || window.confirm("Сбросить несохранённые изменения разбора?");
}
function clearPersonal() {
  state.generation += 1;
  state.user = null; state.watchlist = []; state.reviews = []; state.review = null; state.moreReviews = false;
  $("print-report").replaceChildren(); $("review-detail").replaceChildren(); $("review-rows").replaceChildren();
  $("password-input").value = ""; $("token-input").value = "";
}
async function api(path, { method = "GET", data, blob = false } = {}) {
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
    if (response.status === 401 && state.user) { clearPersonal(); render(); }
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
  const titles = { monitor: "Мониторинг", history: "История рядов", watchlist: "Наблюдение", reviews: "Разборы", system: "Состояние системы" };
  $("page-title").textContent = titles[state.view]; document.title = "ArcShift | " + titles[state.view];
  $("data-summary-value").textContent = state.view === "history" && state.market ? state.market.series.length + " рядов" : "6 состояний";
  $("data-summary-caption").textContent = state.view === "history" ? "Синтетические parser fixtures" : "Фиксированный synthetic snapshot";
  document.querySelectorAll("[data-view]").forEach((item) => {
    const active = item.dataset.view === state.view; item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
  $("account-email").textContent = state.user?.email || "";
  $("login-button").hidden = Boolean(state.user); $("logout-button").hidden = !state.user;
  $("watch-count").textContent = String(state.watchlist.length); $("review-count").textContent = state.reviews.length + (state.moreReviews ? "+" : "");
  $("monitor-view").hidden = !["monitor", "watchlist"].includes(state.view);
  $("reviews-view").hidden = state.view !== "reviews"; $("system-view").hidden = state.view !== "system";
  $("history-view").hidden = state.view !== "history";
  if (["monitor", "watchlist"].includes(state.view)) renderMonitor();
  if (state.view === "reviews") renderReviews();
  if (state.view === "system") renderSystem();
  if (state.view === "history") renderHistory();
  updateIcons();
}
function renderMonitor() {
  $("list-title").textContent = state.view === "watchlist" ? "Личный список" : "Состояния данных";
  const search = $("scenario-search").value.toLocaleLowerCase("ru");
  const rows = state.scenarios.filter((row) => (state.view !== "watchlist" || state.watchlist.includes(row.id)) && (labels[row.id] + row.id).toLocaleLowerCase("ru").includes(search));
  const selected = rows.find((row) => row.id === state.selected) || rows[0];
  if (selected) state.selected = selected.id;
  const container = $("scenario-rows"); container.replaceChildren();
  $("list-empty").hidden = rows.length > 0;
  if (state.view === "watchlist" && !state.user) {
    $("list-empty").hidden = true; container.append(empty("Личный список", true)); $("scenario-detail").replaceChildren(); return updateIcons();
  }
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
  const saved = state.watchlist.includes(row.id);
  heading.append(title, button(saved ? "Убрать из наблюдения" : "Наблюдать", saved ? "bookmark-check" : "bookmark", async () => {
    if (!state.user) return openAuth();
    const generation = state.generation;
    const selected = new Set(state.watchlist); if (selected.has(row.id)) selected.delete(row.id); else selected.add(row.id);
    const result = await api("/api/v1/workspace/watchlist", { method: "PUT", data: { scenario_ids: [...selected] } });
    if (generation !== state.generation) return;
    state.watchlist = result.scenario_ids;
    render();
  }, "icon-button" + (saved ? " saved" : ""))); panel.append(heading);
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
function renderReviews() {
  const rows = $("review-rows"); rows.replaceChildren();
  $("more-reviews").hidden = !state.moreReviews;
  if (!state.user) { rows.append(empty("Личный журнал", true)); $("review-detail").replaceChildren(); return; }
  if (!state.reviews.length) rows.append(empty("Разборов пока нет"));
  if (!state.review && state.reviews.length) state.review = state.reviews[0];
  for (const review of state.reviews) {
    const item = node("button", "review-row" + (state.review?.review_id === review.review_id ? " selected" : ""));
    item.type = "button";
    const name = node("span"); name.append(node("strong", "", labels[review.scenario.id]), node("small", "", new Date(review.updated_at * 1000).toLocaleString("ru-RU") + " · Версия " + review.revision));
    item.append(name, node("span", "state-label", statusLabels[review.status]));
    item.addEventListener("click", () => { if (!canLeaveReview()) return; state.review = review; renderReviews(); updateIcons(); }); rows.append(item);
  }
  renderReview();
}
function renderReview() {
  const panel = $("review-detail"), review = state.review; panel.replaceChildren();
  if (!review) return;
  const heading = node("div", "detail-heading"), title = node("div"); title.append(node("h2", "", labels[review.scenario.id]), node("p", "detail-subtitle", "Зафиксированный synthetic snapshot")); heading.append(title); panel.append(heading);
  const evidence = node("dl", "evidence-list"); evidence.append(detailRow("Разбор", review.review_id, true), detailRow("Snapshot", review.snapshot_id, true), detailRow("Score", review.scenario.signal ? review.scenario.signal.score.toFixed(2) + " · не калиброван" : "Недоступен")); panel.append(evidence);
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
    state.review = updated; await loadPrivate(); render(); notice("Вывод сохранён. Версия " + updated.revision + ".");
  }, save); }); panel.append(form);
  const exports = node("div", "detail-actions");
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
  const details = node("dl"); details.append(detailRow("Разбор", review.review_id), detailRow("Snapshot", review.snapshot_id), detailRow("Состояние", labels[review.scenario.id]), detailRow("Статус", statusLabels[review.status]), detailRow("Версия", review.revision), detailRow("Обновлено", new Date(review.updated_at * 1000).toLocaleString("ru-RU")), detailRow("Score", review.scenario.signal?.score ?? "Недоступен"), detailRow("Допуск источников", "Не подтверждён"));
  container.append(details, node("h2", "", "Вывод аналитика"), node("p", "", review.note || "Не указан"), node("h2", "", "Журнал изменений"));
  for (const event of report.events) container.append(node("p", "", "v" + event.revision + " · " + statusLabels[event.status] + " · " + new Date(event.occurred_at * 1000).toLocaleString("ru-RU")));
  container.append(node("p", "", "Отчёт фиксирует тестовый рабочий процесс, а не валидацию модели или оценку текущего кризисного риска."));
}
function renderSystem() {
  const details = $("system-details"); details.replaceChildren();
  details.append(detailRow("API", state.health?.status === "ok" ? "Доступен" : "Недоступен"), detailRow("Контракт данных", "v1-fixture.1"), detailRow("Контракт аккаунтов", "v1-local-auth.1"), detailRow("Контракт разбора", "v1-local-workspace.1"), detailRow("Контур", "Локальная synthetic-сборка"), detailRow("Источник данных", "Синтетические fixtures"), detailRow("Live-обновление", "Не подключено"), detailRow("Модель", "Не допущена"), detailRow("Публичный запуск", "Не допущен"));
}
function renderHistory() {
  const select = $("history-series");
  if (select.options.length !== (state.market?.series.length || 0)) {
    const selected = select.value; select.replaceChildren();
    for (const series of state.market?.series || []) { const option = node("option", "", seriesLabels[series.series_id] || series.series_id); option.value = series.series_id; select.append(option); }
    if ([...select.options].some((option) => option.value === selected)) select.value = selected;
    else if ([...select.options].some((option) => option.value === "ru.fx.cbr.usd_rub.official")) select.value = "ru.fx.cbr.usd_rub.official";
  }
  const metadata = $("history-metadata"), rows = $("history-rows"); metadata.replaceChildren(); rows.replaceChildren();
  const selected = state.market?.series.find((series) => series.series_id === select.value);
  if (selected) metadata.append(detailRow("Источник кандидата", selected.source_id), detailRow("Ресурс", selected.resource_id, true), detailRow("Версия данных", state.market.data_snapshot_id, true), detailRow("Допуск", "Не подтверждён · только synthetic"));
  $("history-status").textContent = state.historyLoading ? "Получение сохранённого снимка" : state.history ? "Записей: " + state.history.total + (state.history.total > state.history.observations.length ? " · показаны первые " + state.history.observations.length : "") : "История недоступна";
  if (!state.historyLoading && state.history) for (const revision of state.history.observations) {
    const observation = revision.observation, tr = node("tr", revision.is_latest ? "" : "superseded");
    const period = observation.reference_start === observation.reference_end ? observation.reference_start : observation.reference_start + " — " + observation.reference_end;
    const values = [period, observation.value.toLocaleString("ru-RU"), unitLabels[observation.units] || observation.units, observation.published_at ? new Date(observation.published_at).toLocaleString("ru-RU") : "Неизвестно", new Date(observation.received_at).toLocaleString("ru-RU"), "r" + revision.revision_number + (revision.is_latest ? " · текущая" : " · заменена")];
    for (const value of values) tr.append(node("td", "", value)); rows.append(tr);
  }
}
async function loadMarket() {
  state.market = await api("/api/v1/market/series"); renderHistory(); await loadHistory();
}
async function loadHistory() {
  const series = $("history-series").value;
  if (!series) return;
  const generation = ++state.historyGeneration;
  const params = new URLSearchParams({ limit: "500", include_revisions: String($("history-revisions").checked) });
  if ($("history-start").value) params.set("start", $("history-start").value);
  if ($("history-end").value) params.set("end", $("history-end").value);
  state.historyLoading = true; state.history = null; renderHistory();
  try {
    const result = await api("/api/v1/market/series/" + encodeURIComponent(series) + "/history?" + params);
    if (generation === state.historyGeneration) state.history = result;
  } finally { if (generation === state.historyGeneration) { state.historyLoading = false; renderHistory(); } }
}
async function loadPrivate(append = false) {
  if (!state.user) return;
  const generation = state.generation;
  const [watchlist, reviews] = await Promise.all([api("/api/v1/workspace/watchlist"), api("/api/v1/workspace/reviews?limit=50&offset=" + (append ? state.reviews.length : 0))]);
  if (generation !== state.generation || !state.user) return;
  state.watchlist = watchlist.scenario_ids; state.reviews = append ? [...state.reviews, ...reviews.reviews] : reviews.reviews;
  state.moreReviews = reviews.reviews.length === 50;
  if (state.review) state.review = state.reviews.find((item) => item.review_id === state.review.review_id) || state.review;
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
for (const id of ["history-series", "history-start", "history-end", "history-revisions"]) $(id).addEventListener("change", () => run(loadHistory));
$("logout-button").addEventListener("click", () => run(async () => { if (!canLeaveReview()) return; await api("/api/v1/auth/logout", { method: "POST" }); clearPersonal(); accountChannel?.postMessage("changed"); state.view = "monitor"; render(); notice("Вы вышли из аккаунта."); }, $("logout-button")));
$("more-reviews").addEventListener("click", () => run(async () => { await loadPrivate(true); render(); }, $("more-reviews")));
$("refresh-button").addEventListener("click", () => run(async () => {
  if (!canLeaveReview()) return;
  await checkConnection(); state.scenarios = (await api("/api/v1/demo/scenarios")).scenarios; await loadPrivate(); await loadMarket(); render(); notice("");
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
      else { clearPersonal(); state.user = await api("/api/v1/auth/me"); await loadPrivate(); accountChannel?.postMessage("changed"); $("auth-dialog").close(); render(); notice(""); }
    } catch (error) { $("auth-status").textContent = error.message; }
    finally { submit.disabled = false; }
  })();
});
async function start() {
  updateIcons();
  try {
    state.scenarios = (await api("/api/v1/demo/scenarios")).scenarios;
    await checkConnection();
    await loadMarket();
    try { state.user = await api("/api/v1/auth/me"); await loadPrivate(); } catch (error) { if (error.status !== 401) notice(error.message); }
  } catch (error) { notice(error.message); }
  render();
}
async function syncIdentity() {
  try {
    const user = await api("/api/v1/auth/me");
    if (user.user_id !== state.user?.user_id) { clearPersonal(); state.user = user; await loadPrivate(); render(); }
  } catch (error) { if (error.status !== 401) throw error; }
}
if (accountChannel) accountChannel.addEventListener("message", () => { clearPersonal(); render(); run(syncIdentity); });
setInterval(() => { if (!document.hidden) run(async () => { await checkConnection(); await syncIdentity(); }); }, 30000);
window.addEventListener("focus", () => run(syncIdentity));
window.addEventListener("beforeunload", (event) => {
  const note = $("review-note"), status = $("review-status");
  if (state.view === "reviews" && state.review && note && (note.value !== state.review.note || status.value !== state.review.status)) { event.preventDefault(); event.returnValue = ""; }
});
start();
