let riskyGroups = [];

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const pct = (v) => `${(v * 100).toFixed(1)}%`;

function getStake() {
  const v = parseFloat($("#stake-input")?.value);
  return v > 0 ? v : window.DEFAULT_STAKE || 500;
}

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
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "long" });
}

function formatDateShort(iso) {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function showToast(msg) {
  const toast = $("#bet-toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 2800);
}

function marketTag(market) {
  const tags = {
    "1x2": "1X2",
    total: "Тотал",
    oz: "ОЗ",
    cards: "ЖК",
    red_card: "КК",
    both_yellow: "Обе ЖК",
  };
  return tags[market] || market;
}

function getRiskyMinOdds() {
  const v = parseFloat($("#risky-min-odds")?.value);
  return Number.isFinite(v) && v >= 1.65 ? v : 1.65;
}

function getRiskyMinEv() {
  const v = parseFloat($("#risky-min-ev")?.value);
  return Number.isFinite(v) && v >= 0 ? v / 100 : 0;
}

async function refreshRiskyBadge() {
  try {
    const { stats } = await api("/data/risky");
    const badge = $("#risky-badge");
    if (badge) badge.textContent = stats.total || 0;
  } catch (_) {
    if (window.RISKY_BOOT?.stats) {
      const badge = $("#risky-badge");
      if (badge) badge.textContent = window.RISKY_BOOT.stats.total || 0;
    }
  }
}

async function refreshBetsBadge() {
  try {
    const { stats } = await api("/data/bets");
    const badge = $("#bets-badge");
    if (badge) badge.textContent = stats.pending || stats.total || 0;
  } catch (_) {}
}

async function refreshDrawsBadge() {
  try {
    const { stats } = await api("/data/draws");
    const badge = $("#draws-badge");
    if (badge) badge.textContent = stats.matches || 0;
  } catch (_) {
    if (window.DRAWS_BOOT?.stats) {
      const badge = $("#draws-badge");
      if (badge) badge.textContent = window.DRAWS_BOOT.stats.matches || 0;
    }
  }
}

async function loadRisky() {
  const minOdds = getRiskyMinOdds();
  const minEv = getRiskyMinEv();
  const date = $("#risky-date-select")?.value || "";
  const qs = new URLSearchParams({ min_odds: String(minOdds), min_ev: String(minEv) });
  if (date) qs.set("date", date);

  try {
    const data = await api(`/data/risky?${qs}`);
    renderRiskyData(data, date);
    await loadRiskyRetro(minOdds, minEv);
  } catch (err) {
    const boot = window.RISKY_BOOT;
    if (boot?.picks && !date && minOdds <= 1.66 && minEv <= 0.001) {
      renderRiskyData(boot, date);
      renderRiskyRetroFromData(window.RISKY_RETRO);
      showToast("Перезапустите сервер: python web/app.py");
      return;
    }
    renderRiskyError(err.message || "Ошибка загрузки");
  }
}

function money(v) {
  if (v == null) return "—";
  const n = Number(v);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2).replace(".00", "")} ₽`;
}

async function loadDraws() {
  try {
    const data = await api("/data/draws");
    renderDrawsData(data);
  } catch (err) {
    if (window.DRAWS_BOOT) {
      renderDrawsData(window.DRAWS_BOOT);
      return;
    }
    $("#draws-stats-row").innerHTML = "";
    $("#draws-tbody").innerHTML = "";
    $("#draws-empty")?.classList.remove("hidden");
    showToast(err.message || "Ошибка загрузки ничьих");
  }
}

function renderDrawsData(data) {
  renderDrawStats(data.stats);
  renderDrawsTable(data.rows || []);
  const badge = $("#draws-badge");
  if (badge) badge.textContent = data.stats?.matches || 0;
}

function renderDrawStats(s) {
  const profitClass = s.profit >= 0 ? "profit-pos" : "profit-neg";
  $("#draws-stats-row").innerHTML = [
    ["Матчей", s.matches],
    ["Ничьих", s.draws],
    ["Ставка", `${s.stake} ₽`],
    ["Поставлено", `${s.total_staked} ₽`],
    ["Возврат", money(s.total_return).replace("+", "")],
    ["ROI", s.roi != null ? `${s.roi}%` : "—"],
    ["Банк", money(s.bank)],
  ]
    .map(
      ([lbl, val], i) => `
    <div class="stat-card ${i === 6 ? profitClass : ""}">
      <div class="val">${val}</div><div class="lbl">${lbl}</div>
    </div>`
    )
    .join("");
}

function renderDrawsTable(rows) {
  const tbody = $("#draws-tbody");
  const empty = $("#draws-empty");
  const table = $("#draws-table");

  if (!rows.length) {
    tbody.innerHTML = "";
    table.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }

  table.classList.remove("hidden");
  empty.classList.add("hidden");
  tbody.innerHTML = rows
    .map((row) => {
      const statusClass = row.status === "won" ? "won" : "lost";
      const plClass = row.profit >= 0 ? "profit-pos" : "profit-neg";
      const bankClass = row.bank >= 0 ? "profit-pos" : "profit-neg";
      return `
      <tr class="bet-row draw-row ${statusClass}">
        <td>${row.row_num}</td>
        <td>${formatDateShort(row.match_date)}</td>
        <td class="match-cell">${row.home_name}<br><span class="vs">vs</span> ${row.away_name}</td>
        <td><span class="result-score">${row.result_score}</span></td>
        <td><strong>${row.odds.toFixed(2)}</strong></td>
        <td>${row.stake} ₽</td>
        <td>${row.payout ? money(row.payout).replace("+", "") : "—"}</td>
        <td class="${plClass}"><strong>${money(row.profit)}</strong></td>
        <td class="${bankClass}"><strong>${money(row.bank)}</strong></td>
      </tr>`;
    })
    .join("");
}

function renderRiskyData(data, dateFilter) {
  renderRiskyStats(data.stats);
  renderRiskyCards(data.picks, dateFilter, data.stats);
  const badge = $("#risky-badge");
  if (badge) badge.textContent = data.stats?.total || 0;
}

function renderRiskyError(message) {
  $("#risky-stats-row").innerHTML = "";
  $("#risky-cards").innerHTML = "";
  const empty = $("#risky-empty");
  const text = $("#risky-empty-text");
  empty?.classList.remove("hidden");
  if (text) text.textContent = message;
}

function riskyEmptyMessage(dateFilter, count, stats) {
  if (count > 0) return "";
  if (stats?.scheduled_matches > 0 && stats.finished_matches === stats.scheduled_matches) {
    return `На ${dateFilter || "эту дату"} все матчи сыграны. Выберите «Все даты» или будущую дату.`;
  }
  if (dateFilter) {
    return `На ${dateFilter} нет риск-исходов при коэф ≥ 1.65. Попробуйте «Все даты» или снизьте фильтры.`;
  }
  return "Нет риск-ставок при заданных фильтрах.";
}

function formatEvPct(v) {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v}%`;
}

function renderRiskyStats(s) {
  $("#risky-stats-row").innerHTML = [
    ["Ставок", s.total],
    ["Матчей", s.matches],
    ["Средний EV", formatEvPct(s.avg_ev_pct)],
    ["Макс. EV", formatEvPct(s.top_ev_pct)],
  ]
    .map(
      ([lbl, val]) => `
    <div class="stat-card"><div class="val">${val}</div><div class="lbl">${lbl}</div></div>`
    )
    .join("");
}

function groupRiskyByMatch(picks) {
  const map = new Map();
  for (const p of picks) {
    if (!map.has(p.match_id)) {
      map.set(p.match_id, {
        match_id: p.match_id,
        match_date: p.match_date,
        home_name: p.home_name,
        away_name: p.away_name,
        picks: [],
        top_ev: 0,
      });
    }
    const group = map.get(p.match_id);
    group.picks.push(p);
    if (p.ev > group.top_ev) group.top_ev = p.ev;
  }
  for (const group of map.values()) group.picks.sort((a, b) => b.ev - a.ev);
  return [...map.values()].sort((a, b) => b.top_ev - a.top_ev);
}

function evClass(ev) {
  if (ev >= 0.15) return "ev-high";
  if (ev >= 0.05) return "ev-mid";
  return "ev-low";
}

function renderRiskyPickRow(p, idx) {
  const sign = p.ev_pct >= 0 ? "+" : "";
  return `
    <div class="archive-pick-row risky-pick-row ${evClass(p.ev)}">
      <div class="archive-pick-main">
        <span class="market-tag">${marketTag(p.market)}</span>
        ${p.selection_label}
      </div>
      <div class="archive-pick-stats">
        <span>${pct(p.model_prob)}</span>
        <strong>${p.odds.toFixed(2)}</strong>
        <span class="ev-tag">${sign}${p.ev_pct}% EV</span>
      </div>
      <div class="archive-pick-note">${p.guess_note || ""}</div>
      <div class="archive-pick-actions">
        <button type="button" class="btn-add" data-add-bet-risky-idx="${idx}" title="Добавить в «Ставки»">+</button>
      </div>
    </div>`;
}

function renderRiskyCards(picks, dateFilter = "", stats = null) {
  const grid = $("#risky-cards");
  const empty = $("#risky-empty");
  const text = $("#risky-empty-text");
  riskyGroups = groupRiskyByMatch(picks);

  if (!riskyGroups.length) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    if (text) text.textContent = riskyEmptyMessage(dateFilter, 0, stats);
    return;
  }
  empty.classList.add("hidden");

  grid.innerHTML = riskyGroups
    .map((g) => {
      const top = g.picks[0];
      const cls = evClass(g.top_ev);
      const sign = top.ev_pct >= 0 ? "+" : "";
      return `
    <div class="archive-match-card risky-match-card ${cls}">
      <button type="button" class="btn-add risky-card-add" data-quick-risky="${g.match_id}" title="Добавить в «Ставки»">+</button>
      <button type="button" class="risky-card-body" data-risky-match="${g.match_id}">
        <span class="archive-card-date">${formatDateShort(g.match_date)}</span>
        <span class="archive-card-teams">${g.home_name} — ${g.away_name}</span>
        <span class="archive-card-meta">
          <strong>${sign}${top.ev_pct}% EV</strong> · ${top.selection_label} · ${top.odds.toFixed(2)}
          · ${g.picks.length} шт.
        </span>
      </button>
    </div>`;
    })
    .join("");

  grid.querySelectorAll("[data-quick-risky]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const group = riskyGroups.find((g) => g.match_id === parseInt(btn.dataset.quickRisky, 10));
      if (group?.picks[0]) addBetFromRisky(group.picks[0]);
    });
  });
  grid.querySelectorAll(".risky-card-body").forEach((btn) => {
    btn.addEventListener("click", () => openRiskyModal(parseInt(btn.dataset.riskyMatch, 10)));
  });
}

function openRiskyModal(matchId) {
  const group = riskyGroups.find((g) => g.match_id === matchId);
  if (!group) return;

  $("#risky-modal-title").textContent = `${group.home_name} — ${group.away_name}`;
  $("#risky-modal-meta").textContent =
    `${formatDate(group.match_date)} · ${group.picks.length} риск-исход(ов)`;

  const body = $("#risky-modal-body");
  body.innerHTML = group.picks.map((p, idx) => renderRiskyPickRow(p, idx)).join("");

  body.querySelectorAll("[data-add-bet-risky-idx]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const pick = group.picks[parseInt(btn.dataset.addBetRiskyIdx, 10)];
      if (pick) await addBetFromRisky(pick);
    });
  });

  const modal = $("#risky-modal");
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
}

function closeRiskyModal() {
  const modal = $("#risky-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

function retroOutcomeLabel(outcome) {
  return outcome === "won"
    ? '<span class="retro-won">✓ выигрыш</span>'
    : '<span class="retro-lost">✗ проигрыш</span>';
}

function renderRetroPickRow(p) {
  const sign = p.ev_pct >= 0 ? "+" : "";
  return `
    <div class="risky-retro-pick ${p.outcome}">
      <span class="retro-pick-label">${p.selection_label}</span>
      <span class="retro-pick-meta">kef ${p.odds.toFixed(2)} · ${pct(p.model_prob)} · ${sign}${p.ev_pct}% EV</span>
      ${retroOutcomeLabel(p.outcome)}
    </div>`;
}

function renderRetroBoldRow(p) {
  const sign = p.ev_pct >= 0 ? "+" : "";
  return `
    <div class="risky-retro-pick bold-alt ${p.outcome}">
      <span class="retro-pick-label">Риск ≈ коэф: ${p.selection_label}</span>
      <span class="retro-pick-meta">kef ${p.odds.toFixed(2)} · ${pct(p.model_prob)} · ${sign}${p.ev_pct}% EV</span>
      ${retroOutcomeLabel(p.outcome)}
    </div>`;
}

function renderRiskyRetroFromData(data) {
  const grid = $("#risky-retro-cards");
  const empty = $("#risky-retro-empty");
  const groups = data?.groups || [];
  if (!groups.length) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  grid.innerHTML = groups
    .map((g) => {
      const extras = g.result_extras ? ` · ${g.result_extras}` : "";
      const evRows = (g.ev_picks || []).map(renderRetroPickRow).join("");
      const boldRow = g.bold_pick ? renderRetroBoldRow(g.bold_pick) : "";
      const noEv = !evRows ? '<p class="retro-none">Нет +EV — лучший риск-исход на матч:</p>' : "";
      return `
      <div class="risky-retro-match">
        <div class="risky-retro-header">
          <strong>${g.home_name} — ${g.away_name}</strong>
          <span>${formatDateShort(g.match_date)} · итог ${g.result_score}${extras}</span>
        </div>
        ${noEv}${evRows}${boldRow}
      </div>`;
    })
    .join("");
}

async function loadRiskyRetro(minOdds, minEv) {
  try {
    const qs = new URLSearchParams({
      min_odds: String(minOdds ?? getRiskyMinOdds()),
      min_ev: String(minEv ?? getRiskyMinEv()),
    });
    renderRiskyRetroFromData(await api(`/data/risky/retrospective?${qs}`));
  } catch (_) {
    if (window.RISKY_RETRO) renderRiskyRetroFromData(window.RISKY_RETRO);
  }
}

async function createBet(body) {
  await api("/data/bets", { method: "POST", body: JSON.stringify(body) });
  showToast(`→ Ставки: ${body.selection_label} · кеф ${body.odds.toFixed(2)} · ${body.stake} ₽`);
  refreshBetsBadge();
  if ($("#tab-bets")?.classList.contains("active")) loadBets();
}

async function addBetFromRisky(pick) {
  const market = pick.market === "btts" ? "oz" : pick.market;
  const body = {
    match_id: pick.match_id,
    market,
    selection: pick.selection,
    selection_label: pick.selection_label,
    model_prob: pick.model_prob ?? pick.prob,
    odds: pick.odds,
    stake: getStake(),
  };
  const nicheMarkets = ["cards", "red_card", "both_yellow"];
  const note = pick.guess_note;
  if (note && /^\d+:\d+$/.test(note)) {
    const [gh, ga] = note.split(":").map((n) => parseInt(n, 10));
    body.guess_home = gh;
    body.guess_away = ga;
  } else if (note) {
    body.guess_note = note;
  }
  try {
    await createBet(body);
  } catch (err) {
    alert(err.message);
  }
}

function betEvPct(b) {
  return Math.round((b.model_prob * b.odds - 1) * 1000) / 10;
}

function formatPL(profit, status) {
  if (status === "pending") return "—";
  const sign = profit >= 0 ? "+" : "";
  return `${sign}${profit} ₽`;
}

function formatActual(b) {
  if (b.status !== "pending" && b.actual_home != null) {
    const icon = b.status === "won" ? "✓" : "✗";
    let text = `${b.actual_home}:${b.actual_away} ${icon}`;
    if (["cards", "red_card", "both_yellow"].includes(b.market) && b.file_result?.yellows != null) {
      text += ` · ${b.file_result.yellows} ЖК`;
    }
    return `<span class="result-score">${text}</span>`;
  }
  if (b.file_result) {
    const fr = b.file_result;
    let text = `${fr.home}:${fr.away}`;
    if (fr.yellows != null) text += ` · ${fr.yellows} ЖК`;
    return `<span class="result-pending" title="Нажмите «Обновить таблицу»">${text} ↻</span>`;
  }
  return "—";
}

async function loadBets(sync = false) {
  const data = sync ? await api("/data/bets/sync", { method: "POST" }) : await api("/data/bets");
  renderBetStats(data.stats);
  renderBetsTable(data.bets);
  const badge = $("#bets-badge");
  if (badge) badge.textContent = data.stats.pending || 0;

  if (sync) {
    const parts = [];
    if (data.results_fetched > 0) parts.push(`Загружено итогов: ${data.results_fetched}`);
    if (data.synced > 0) parts.push(`Рассчитано: ${data.synced}`);
    if (parts.length) showToast(parts.join(" · "));
    else if (data.errors?.length) showToast("Не удалось загрузить итоги");
    else showToast("Новых итогов нет");
  }
}

function renderBetStats(s) {
  const profitClass = s.total_profit >= 0 ? "profit-pos" : "profit-neg";
  const profitSign = s.total_profit >= 0 ? "+" : "";
  $("#stats-row").innerHTML = [
    ["Всего", s.total],
    ["Ожидают", s.pending],
    ["Выигрыш", s.wins],
    ["Проигрыш", s.losses],
    ["ROI", s.roi != null ? `${s.roi}%` : "—"],
    ["P/L", s.resolved ? `${profitSign}${s.total_profit} ₽` : "—"],
  ]
    .map(
      ([lbl, val], i) => `
    <div class="stat-card ${i === 5 && s.resolved ? profitClass : ""}">
      <div class="val">${val}</div><div class="lbl">${lbl}</div>
    </div>`
    )
    .join("");
}

function renderBetsTable(bets) {
  const tbody = $("#bets-tbody");
  const empty = $("#bets-empty");
  const table = $("#bets-table");

  if (!bets.length) {
    tbody.innerHTML = "";
    table.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }
  table.classList.remove("hidden");
  empty.classList.add("hidden");

  tbody.innerHTML = bets
    .map((b) => {
      const ev = betEvPct(b);
      const evSign = ev >= 0 ? "+" : "";
      const statusClass = b.status === "won" ? "won" : b.status === "lost" ? "lost" : "pending";
      const plClass = b.profit == null ? "" : b.profit >= 0 ? "profit-pos" : "profit-neg";
      return `
      <tr class="bet-row ${statusClass}">
        <td>${b.row_num ?? b.id}</td>
        <td>${formatDateShort(b.match_date)}</td>
        <td class="match-cell">${b.home_name}<br><span class="vs">vs</span> ${b.away_name}</td>
        <td><span class="pick-label">${b.selection_label}</span></td>
        <td class="ev-tag">${evSign}${ev}%</td>
        <td><strong>${b.odds.toFixed(2)}</strong></td>
        <td>${b.stake} ₽</td>
        <td>${formatActual(b)}</td>
        <td class="${plClass}"><strong>${formatPL(b.profit, b.status)}</strong></td>
        <td><button class="btn danger small" data-delete-bet="${b.id}">×</button></td>
      </tr>`;
    })
    .join("");

  tbody.querySelectorAll("[data-delete-bet]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Удалить ставку?")) return;
      await api(`/data/bets/${btn.dataset.deleteBet}`, { method: "DELETE" });
      loadBets();
    });
  });
}

function bindEvents() {
  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".tab").forEach((t) => t.classList.remove("active"));
      $$(".panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`#tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "bets") loadBets();
      if (btn.dataset.tab === "draws") loadDraws();
      if (btn.dataset.tab === "risky") loadRisky();
    });
  });

  $("#btn-risky-refresh")?.addEventListener("click", () => loadRisky());
  $("#risky-date-select")?.addEventListener("change", () => loadRisky());
  $("#risky-min-odds")?.addEventListener("change", () => loadRisky());
  $("#risky-min-ev")?.addEventListener("change", () => loadRisky());
  $("#btn-refresh-draws")?.addEventListener("click", () => loadDraws());
  $("#btn-refresh-bets")?.addEventListener("click", () => loadBets(true));
  $("#risky-modal-close")?.addEventListener("click", closeRiskyModal);
  $("#risky-modal-backdrop")?.addEventListener("click", closeRiskyModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeRiskyModal();
  });
}

function init() {
  if (window.RISKY_BOOT) {
    renderRiskyData(window.RISKY_BOOT, window.WC2026_DEFAULT_DATE || "");
  }
  if (window.RISKY_RETRO) renderRiskyRetroFromData(window.RISKY_RETRO);
  if (window.DRAWS_BOOT) renderDrawsData(window.DRAWS_BOOT);
  refreshRiskyBadge().catch(() => {});
  refreshDrawsBadge().catch(() => {});
  refreshBetsBadge().catch(() => {});
  bindEvents();
}

document.addEventListener("DOMContentLoaded", init);
