let longshotCards = [];

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

function marketTag(market) {
  const tags = {
    "1x2": "1X2",
    total: "Тотал",
    handicap: "Фора",
  };
  return tags[market] || market;
}

function formatScore(v) {
  return v == null ? "—" : v.toFixed(2);
}

function getLongshotQuery() {
  const qs = new URLSearchParams();
  const date = $("#longshot-date-select")?.value || "";
  const includeFinished = $("#longshot-include-finished")?.value || "0";
  if (date) qs.set("date", date);
  qs.set("include_finished", includeFinished);
  return qs;
}

async function loadLongshotForecasts() {
  try {
    renderLongshotForecasts(await api(`/longshot/data/forecasts?${getLongshotQuery()}`));
  } catch (_) {
    if (window.LONGSHOT_BOOT) renderLongshotForecasts(window.LONGSHOT_BOOT);
  }
}

async function loadLongshotRetro() {
  try {
    renderLongshotRetro(await api("/longshot/data/retrospective"));
  } catch (_) {
    if (window.LONGSHOT_RETRO) renderLongshotRetro(window.LONGSHOT_RETRO);
  }
}

function renderLongshotStats(s) {
  $("#longshot-stats-row").innerHTML = [
    ["Ставок", s.total || 0],
    ["Матчей", s.matches || 0],
    ["Средний кеф", s.avg_odds != null ? s.avg_odds.toFixed(2) : "—"],
    ["Средний score", formatScore(s.avg_score)],
  ]
    .map(
      ([label, value]) => `
      <div class="stat-card"><div class="val">${value}</div><div class="lbl">${label}</div></div>`
    )
    .join("");
}

function renderLongshotForecasts(data) {
  longshotCards = data.cards || [];
  renderLongshotStats(data.stats || {});
  const badge = $("#longshot-badge");
  if (badge) badge.textContent = data.stats?.total || 0;

  const grid = $("#longshot-cards");
  const empty = $("#longshot-empty");
  const emptyText = $("#longshot-empty-text");
  if (!longshotCards.length) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    if (emptyText && data.stats?.finished_hidden) {
      emptyText.textContent = "Все матчи выбранной даты уже сыграны. Включите показ сыгранных или откройте вкладку «Сыгранные».";
    }
    return;
  }

  empty.classList.add("hidden");
  grid.innerHTML = longshotCards
    .map((card) => {
      const top = card.top_pick;
      const finished = card.is_finished ? '<span class="archive-featured">сыгран</span>' : "";
      return `
        <button type="button" class="archive-match-card longshot-match-card" data-longshot-match="${card.match_id}">
          <span class="archive-card-date">${formatDateShort(card.match_date)} · группа ${card.group}</span>
          <span class="archive-card-teams">${card.home_name} — ${card.away_name}</span>
          <span class="archive-card-meta">
            <strong>${top.odds.toFixed(2)}</strong> · ${top.selection_label} · ${pct(top.model_prob)}
          </span>
          <span class="archive-card-meta">score ${top.score.toFixed(2)} · quality ${top.scenario_quality.toFixed(2)} · ${card.picks.length} исход ${finished}</span>
        </button>`;
    })
    .join("");

  grid.querySelectorAll("[data-longshot-match]").forEach((btn) => {
    btn.addEventListener("click", () => openLongshotModal(parseInt(btn.dataset.longshotMatch, 10)));
  });
}

function renderPickRow(p) {
  const sign = p.edge >= 0 ? "+" : "";
  const reasons = (p.reasons || []).join(" · ");
  return `
    <div class="archive-pick-row risky-pick-row">
      <div class="archive-pick-main">
        <span class="market-tag">${marketTag(p.market)}</span>
        ${p.selection_label}
      </div>
      <div class="archive-pick-stats">
        <span>${pct(p.model_prob)}</span>
        <strong>${p.odds.toFixed(2)}</strong>
        <span class="ev-tag">${sign}${(p.edge * 100).toFixed(1)} п.п.</span>
      </div>
      <div class="archive-pick-note">quality ${p.scenario_quality.toFixed(2)} · ${reasons}</div>
    </div>`;
}

function openLongshotModal(matchId) {
  const card = longshotCards.find((item) => item.match_id === matchId);
  if (!card) return;
  $("#longshot-modal-title").textContent = `${card.home_name} — ${card.away_name}`;
  $("#longshot-modal-meta").textContent = `${formatDate(card.match_date)} · ${card.venue} · ${card.source}`;
  $("#longshot-modal-body").innerHTML = `
    ${card.picks.map(renderPickRow).join("")}
    <div class="hint-card longshot-modal-note">
      <p>Схема: берём только реальные кефы ≥ 4.0, требуем probability ≥ 13.5% и достаточный scenario quality; если фильтр не пройден, матч пропускается.</p>
    </div>`;
  const modal = $("#longshot-modal");
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
}

function closeLongshotModal() {
  const modal = $("#longshot-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

function retroOutcomeLabel(outcome) {
  return outcome === "won"
    ? '<span class="retro-won">✓ выигрыш</span>'
    : '<span class="retro-lost">✗ проигрыш</span>';
}

function renderLongshotRetro(data) {
  const groups = data?.groups || [];
  const stats = data?.stats || {};
  const badge = $("#longshot-retro-badge");
  if (badge) badge.textContent = stats.picks || 0;

  $("#longshot-retro-stats-row").innerHTML = [
    ["Матчей", stats.matches || 0],
    ["Пропуск", stats.skipped_matches || 0],
    ["Ставок", stats.picks || 0],
    ["Зашло", stats.wins || 0],
    ["Не зашло", stats.losses || 0],
    ["Hit rate", stats.hit_rate != null ? `${stats.hit_rate}%` : "—"],
  ]
    .map(
      ([label, value]) => `
      <div class="stat-card"><div class="val">${value}</div><div class="lbl">${label}</div></div>`
    )
    .join("");

  const grid = $("#longshot-retro-cards");
  const empty = $("#longshot-retro-empty");
  if (!groups.length) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  grid.innerHTML = groups
    .map((group) => {
      const rows = group.picks
        .map(
          (pick) => `
          <div class="risky-retro-pick ${pick.outcome}">
            <span class="retro-pick-label">${pick.selection_label}</span>
            <span class="retro-pick-meta">kef ${pick.odds.toFixed(2)} · ${pct(pick.model_prob)} · score ${pick.score.toFixed(2)} · quality ${pick.scenario_quality.toFixed(2)}</span>
            ${retroOutcomeLabel(pick.outcome)}
          </div>`
        )
        .join("");
      return `
        <div class="risky-retro-match">
          <div class="risky-retro-header">
            <strong>${group.home_name} — ${group.away_name}</strong>
            <span>${formatDateShort(group.match_date)} · итог ${group.result_score}</span>
          </div>
          ${rows}
        </div>`;
    })
    .join("");
}

function bindEvents() {
  $$("[data-longshot-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("[data-longshot-view]").forEach((item) => item.classList.remove("active"));
      $$(".panel").forEach((panel) => panel.classList.remove("active"));
      btn.classList.add("active");
      $(`#longshot-view-${btn.dataset.longshotView}`).classList.add("active");
      if (btn.dataset.longshotView === "forecasts") loadLongshotForecasts();
      if (btn.dataset.longshotView === "retro") loadLongshotRetro();
    });
  });

  $("#btn-longshot-refresh")?.addEventListener("click", () => loadLongshotForecasts());
  $("#longshot-date-select")?.addEventListener("change", () => loadLongshotForecasts());
  $("#longshot-include-finished")?.addEventListener("change", () => loadLongshotForecasts());
  $("#longshot-modal-close")?.addEventListener("click", closeLongshotModal);
  $("#longshot-modal-backdrop")?.addEventListener("click", closeLongshotModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLongshotModal();
  });
}

function init() {
  if (window.LONGSHOT_BOOT) renderLongshotForecasts(window.LONGSHOT_BOOT);
  if (window.LONGSHOT_RETRO) renderLongshotRetro(window.LONGSHOT_RETRO);
  bindEvents();
}

document.addEventListener("DOMContentLoaded", init);
