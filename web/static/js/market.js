let marketCards = [];

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const pct = (v) => `${(v * 100).toFixed(1)}%`;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function formatDate(iso) {
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "long" });
}

function formatDateShort(iso) {
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function showToast(msg) {
  const toast = $("#bet-toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 2600);
}

function formatEvPct(v) {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v}%`;
}

function marketTag(market) {
  const tags = {
    "1x2": "1X2",
    total: "Тотал",
    oz: "ОЗ",
    handicap: "Фора",
  };
  return tags[market] || market;
}

function evClass(ev) {
  if (ev >= 0.08) return "ev-high";
  if (ev >= 0) return "ev-mid";
  return "ev-low";
}

function getMarketQuery() {
  const qs = new URLSearchParams();
  const date = $("#market-date-select")?.value || "";
  const includeFinished = $("#market-include-finished")?.value || "0";
  if (date) qs.set("date", date);
  qs.set("include_finished", includeFinished);
  return qs;
}

async function loadMarketForecasts() {
  try {
    const data = await api(`/market/data/forecasts?${getMarketQuery()}`);
    renderMarketForecasts(data);
  } catch (err) {
    if (window.MARKET_BOOT?.cards) {
      renderMarketForecasts(window.MARKET_BOOT);
      showToast("Показан стартовый снимок market-модели");
      return;
    }
    renderMarketError(err.message || "Ошибка загрузки");
  }
}

async function loadMarketRetro() {
  try {
    renderMarketRetro(await api("/market/data/retrospective"));
  } catch (_) {
    if (window.MARKET_RETRO) renderMarketRetro(window.MARKET_RETRO);
  }
}

function renderMarketStats(s) {
  $("#market-stats-row").innerHTML = [
    ["Прогнозов", s.total],
    ["Матчей", s.matches],
    ["Средний EV", formatEvPct(s.avg_ev_pct)],
    ["Макс. EV", formatEvPct(s.top_ev_pct)],
  ]
    .map(
      ([label, value]) => `
      <div class="stat-card"><div class="val">${value}</div><div class="lbl">${label}</div></div>`
    )
    .join("");
}

function renderMarketForecasts(data) {
  marketCards = data.cards || [];
  renderMarketStats(data.stats || {});
  const badge = $("#market-badge");
  if (badge) badge.textContent = data.stats?.total || 0;

  const grid = $("#market-cards");
  const empty = $("#market-empty");
  const emptyText = $("#market-empty-text");
  if (!marketCards.length) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    if (emptyText && data.stats?.finished_hidden) {
      emptyText.textContent = "Все матчи выбранной даты уже сыграны. Включите показ сыгранных или откройте вкладку «Сыгранные».";
    }
    return;
  }

  empty.classList.add("hidden");
  grid.innerHTML = marketCards
    .map((card) => {
      const top = card.top_pick;
      const sign = top.ev_pct >= 0 ? "+" : "";
      const cls = evClass(top.ev);
      const finished = card.is_finished ? '<span class="archive-featured">сыгран</span>' : "";
      return `
        <button type="button" class="archive-match-card market-match-card ${cls}" data-market-match="${card.match_id}">
          <span class="archive-card-date">${formatDateShort(card.match_date)} · группа ${card.group}</span>
          <span class="archive-card-teams">${card.home_name} — ${card.away_name}</span>
          <span class="archive-card-meta">
            <strong>${sign}${top.ev_pct}% EV</strong> · ${top.selection_label} · ${top.odds.toFixed(2)}
          </span>
          <span class="archive-card-meta">xG ${card.model.lambda_home.toFixed(2)}:${card.model.lambda_away.toFixed(2)} · тотал ${card.model.expected_total.toFixed(2)} ${finished}</span>
        </button>`;
    })
    .join("");

  grid.querySelectorAll("[data-market-match]").forEach((btn) => {
    btn.addEventListener("click", () => openMarketModal(parseInt(btn.dataset.marketMatch, 10)));
  });
}

function renderMarketError(message) {
  $("#market-stats-row").innerHTML = "";
  $("#market-cards").innerHTML = "";
  $("#market-empty")?.classList.remove("hidden");
  const text = $("#market-empty-text");
  if (text) text.textContent = message;
}

function probabilityRows(card) {
  const o = card.outcome_1x2;
  const t = card.totals;
  const oz = card.oz;
  const h = card.handicaps;
  return `
    <div class="market-detail-grid">
      <div>
        <h3>1X2</h3>
        <div class="total-item"><span>П1</span><strong>${pct(o.home)}</strong></div>
        <div class="total-item"><span>X</span><strong>${pct(o.draw)}</strong></div>
        <div class="total-item"><span>П2</span><strong>${pct(o.away)}</strong></div>
      </div>
      <div>
        <h3>Тоталы</h3>
        <div class="total-item"><span>Больше 2.5</span><strong>${pct(t.over_2_5)}</strong></div>
        <div class="total-item"><span>Меньше 2.5</span><strong>${pct(t.under_2_5)}</strong></div>
        <div class="total-item"><span>Больше 3.5</span><strong>${pct(t.over_3_5)}</strong></div>
      </div>
      <div>
        <h3>ОЗ</h3>
        <div class="total-item"><span>Да</span><strong>${pct(oz.yes)}</strong></div>
        <div class="total-item"><span>Нет</span><strong>${pct(oz.no)}</strong></div>
      </div>
      <div>
        <h3>Форы</h3>
        <div class="total-item"><span>Ф1 (-1.5)</span><strong>${pct(h.home_minus_1_5)}</strong></div>
        <div class="total-item"><span>Ф1 (-0.5)</span><strong>${pct(h.home_minus_0_5)}</strong></div>
        <div class="total-item"><span>Ф1 (+0.5)</span><strong>${pct(h.home_plus_0_5)}</strong></div>
        <div class="total-item"><span>Ф1 (+1.5)</span><strong>${pct(h.home_plus_1_5)}</strong></div>
        <div class="total-item"><span>Ф2 (-1.5)</span><strong>${pct(h.away_minus_1_5)}</strong></div>
        <div class="total-item"><span>Ф2 (-0.5)</span><strong>${pct(h.away_minus_0_5)}</strong></div>
        <div class="total-item"><span>Ф2 (+0.5)</span><strong>${pct(h.away_plus_0_5)}</strong></div>
        <div class="total-item"><span>Ф2 (+1.5)</span><strong>${pct(h.away_plus_1_5)}</strong></div>
      </div>
    </div>`;
}

function openMarketModal(matchId) {
  const card = marketCards.find((item) => item.match_id === matchId);
  if (!card) return;
  const top = card.top_pick;
  const sign = top.ev_pct >= 0 ? "+" : "";

  $("#market-modal-title").textContent = `${card.home_name} — ${card.away_name}`;
  $("#market-modal-meta").textContent = `${formatDate(card.match_date)} · ${card.venue} · ${card.source}`;
  $("#market-modal-body").innerHTML = `
    <div class="archive-pick-row risky-pick-row ${evClass(top.ev)}">
      <div class="archive-pick-main">
        <span class="market-tag">${marketTag(top.market)}</span>
        ${top.selection_label}
      </div>
      <div class="archive-pick-stats">
        <span>${pct(top.prob)}</span>
        <strong>${top.odds.toFixed(2)}</strong>
        <span class="ev-tag">${sign}${top.ev_pct}% EV</span>
      </div>
      <div class="archive-pick-note">Ожидаемый тотал ${card.model.expected_total.toFixed(2)} · форы считаются по голевой матрице market-модели</div>
    </div>
    ${probabilityRows(card)}`;

  const modal = $("#market-modal");
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
}

function closeMarketModal() {
  const modal = $("#market-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

function retroOutcomeLabel(outcome) {
  return outcome === "won"
    ? '<span class="retro-won">✓ выигрыш</span>'
    : '<span class="retro-lost">✗ проигрыш</span>';
}

function renderMarketRetro(data) {
  const groups = data?.groups || [];
  const stats = data?.stats || {};
  const badge = $("#market-retro-badge");
  if (badge) badge.textContent = stats.matches || 0;

  $("#market-retro-stats-row").innerHTML = [
    ["Матчей", stats.matches || 0],
    ["Зашло", stats.wins || 0],
    ["Не зашло", stats.losses || 0],
    ["Hit rate", stats.hit_rate != null ? `${stats.hit_rate}%` : "—"],
    ["Средний EV", formatEvPct(stats.avg_ev_pct)],
  ]
    .map(
      ([label, value]) => `
      <div class="stat-card"><div class="val">${value}</div><div class="lbl">${label}</div></div>`
    )
    .join("");

  const grid = $("#market-retro-cards");
  const empty = $("#market-retro-empty");
  if (!groups.length) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  grid.innerHTML = groups
    .map((group) => {
      const top = group.top_pick;
      const sign = top.ev_pct >= 0 ? "+" : "";
      return `
        <div class="risky-retro-match">
          <div class="risky-retro-header">
            <strong>${group.home_name} — ${group.away_name}</strong>
            <span>${formatDateShort(group.match_date)} · итог ${group.result_score}</span>
          </div>
          <div class="risky-retro-pick ${top.outcome}">
            <span class="retro-pick-label">${top.selection_label}</span>
            <span class="retro-pick-meta">kef ${top.odds.toFixed(2)} · ${pct(top.prob)} · ${sign}${top.ev_pct}% EV</span>
            ${retroOutcomeLabel(top.outcome)}
          </div>
        </div>`;
    })
    .join("");
}

function bindEvents() {
  $$("[data-market-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("[data-market-view]").forEach((item) => item.classList.remove("active"));
      $$(".panel").forEach((panel) => panel.classList.remove("active"));
      btn.classList.add("active");
      $(`#market-view-${btn.dataset.marketView}`).classList.add("active");
      if (btn.dataset.marketView === "forecasts") loadMarketForecasts();
      if (btn.dataset.marketView === "retro") loadMarketRetro();
    });
  });

  $("#btn-market-refresh")?.addEventListener("click", () => loadMarketForecasts());
  $("#market-date-select")?.addEventListener("change", () => loadMarketForecasts());
  $("#market-include-finished")?.addEventListener("change", () => loadMarketForecasts());
  $("#market-modal-close")?.addEventListener("click", closeMarketModal);
  $("#market-modal-backdrop")?.addEventListener("click", closeMarketModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMarketModal();
  });
}

function init() {
  if (window.MARKET_BOOT) renderMarketForecasts(window.MARKET_BOOT);
  if (window.MARKET_RETRO) renderMarketRetro(window.MARKET_RETRO);
  bindEvents();
}

document.addEventListener("DOMContentLoaded", init);
