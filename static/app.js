const state = {
  query: "",
  loading: false,
  view: "today",
};

const filters = document.querySelector("#filters");
const sidebarToggle = document.querySelector("#sidebar-toggle");
const navButtons = document.querySelectorAll("[data-view-target]");
const feed = document.querySelector("#feed");
const feedTitle = document.querySelector("#feed-title");
const feedMeta = document.querySelector("#feed-meta");
const topbarTitle = document.querySelector(".topbar h2");
const topbarTitleMain = document.querySelector("#topbar-title-main");
const topbarDate = document.querySelector("#topbar-date");
const stats = document.querySelector("#stats");
const brief = document.querySelector("#brief");
const hotTopics = document.querySelector("#hot-topics");
const statusLine = document.querySelector("#status");
const search = document.querySelector("#search");
const suggestions = document.querySelector("#suggestions");
const clearSearch = document.querySelector("#clear-search");
const refreshStatus = document.querySelector("#refresh-status");
const overviewSections = document.querySelectorAll(".overview-only");
const dailyBriefs = document.querySelector("#daily-briefs");
const dailyBriefsList = document.querySelector("#daily-briefs-list");
const favorites = document.querySelector("#favorites");
const favoritesFeed = document.querySelector("#favorites-feed");
const systemStatus = document.querySelector("#system-status");
const systemHealthBadge = document.querySelector("#system-health-badge");
const systemHealth = document.querySelector("#system-health");
const systemMetrics = document.querySelector("#system-metrics");
const sourceBreakdown = document.querySelector("#source-breakdown");

function setStatus(message, isError = false) {
  statusLine.textContent = message || "";
  statusLine.classList.toggle("error", isError);
}

function formParams() {
  const data = new FormData(filters);
  const params = new URLSearchParams();
  const fecha = data.get("fecha");
  const orden = data.get("orden") || "Puntaje";
  if (fecha) params.set("fecha", fecha);
  params.set("orden", orden);
  for (const source of data.getAll("fuentes")) params.append("fuentes", source);
  for (const area of data.getAll("areas")) params.append("areas", area);
  if (state.query) params.set("q", state.query);
  return params;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function splitStarTitle(value) {
  const text = String(value ?? "");
  const match = text.match(/^(.*?)(?:\s*⭐\s*([\d,]+))$/);
  if (!match) return { title: text, stars: "" };
  return { title: match[1].trim(), stars: match[2] };
}

function renderStarCount(stars) {
  if (!stars) return "";
  return `
    <span class="github-star-count" aria-label="${escapeHtml(stars)} GitHub stars">
      <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.969.719 4.193a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"></path>
      </svg>
      <span>${escapeHtml(stars)}</span>
    </span>
  `;
}

function renderTitleLabel(value) {
  const parts = splitStarTitle(value);
  return `${escapeHtml(parts.title)}${parts.stars ? ` ${renderStarCount(parts.stars)}` : ""}`;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatFeedDate(value) {
  if (!value) return "";
  const parts = value.split("-").map((part) => Number.parseInt(part, 10));
  if (parts.length !== 3 || parts.some(Number.isNaN)) return "";
  const date = new Date(parts[0], parts[1] - 1, parts[2]);
  return date.toLocaleDateString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function updateTopbarTitle() {
  const briefsActive = state.view === "briefs";
  const favoritesActive = state.view === "favorites";
  const systemActive = state.view === "system";
  const title = briefsActive
    ? "Daily Briefs"
    : favoritesActive
      ? "Favorites"
      : systemActive
        ? "System Status"
        : "Today\u2019s Updates";

  if (topbarTitleMain) {
    topbarTitleMain.textContent = title;
  } else {
    topbarTitle.textContent = title;
  }

  if (!topbarDate) return;
  const dateInput = filters.querySelector('input[name="fecha"]');
  const selectedDate = dateInput?.value || "";
  const latestDate = dateInput?.max || "";
  const showDate = state.view === "today" && selectedDate && latestDate && selectedDate !== latestDate;
  topbarDate.hidden = !showDate;
  topbarDate.textContent = showDate ? formatFeedDate(selectedDate) : "";
}

function hasSummary(item) {
  const value = (item.resumen_ia || "").trim();
  return value && value !== "Resumen no disponible";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.reason || data.detail || "Request failed.");
  }
  return data;
}

async function loadAll() {
  if (state.view === "briefs") {
    await loadDailyBriefs();
    return;
  }
  if (state.view === "favorites") {
    await loadFavorites();
    return;
  }
  if (state.view === "system") {
    await loadSystemStatus();
    return;
  }
  if (state.loading) return;
  updateTopbarTitle();
  state.loading = true;
  document.body.classList.add("is-loading");
  const searchActive = Boolean(state.query);
  setSearchMode(searchActive);
  setStatus(searchActive ? "Loading search results..." : "Loading dashboard...");
  try {
    const params = formParams();
    const feedData = await fetchJson(`/api/feed?${params}`);
    if (!searchActive) {
      renderHotTopics(feedData.hot_topics || []);
    }
    renderFeed(feedData);
    setStatus("");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    state.loading = false;
    document.body.classList.remove("is-loading");
  }
}

async function loadDailyBriefs() {
  if (state.loading) return;
  state.loading = true;
  document.body.classList.add("is-loading");
  setViewMode("briefs");
  setStatus("Loading daily briefs...");
  try {
    const [briefData, archiveData] = await Promise.all([
      fetchJson("/api/brief"),
      fetchJson("/api/daily-briefs"),
    ]);
    renderBrief(briefData);
    renderDailyBriefs(archiveData.items || []);
    setStatus("");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    state.loading = false;
    document.body.classList.remove("is-loading");
  }
}

async function loadFavorites() {
  if (state.loading) return;
  state.loading = true;
  document.body.classList.add("is-loading");
  setViewMode("favorites");
  setStatus("Loading favorites...");
  try {
    const data = await fetchJson("/api/favorites");
    renderFavorites(data);
    setStatus("");
  } catch (error) {
    favoritesFeed.innerHTML = `<div class="empty panel">Favorites could not be loaded: ${escapeHtml(error.message)}</div>`;
    setStatus(error.message, true);
  } finally {
    state.loading = false;
    document.body.classList.remove("is-loading");
  }
}

async function loadSystemStatus() {
  if (state.loading) return;
  state.loading = true;
  document.body.classList.add("is-loading");
  setViewMode("system");
  setStatus("Loading system status...");
  try {
    const [statsData, refreshData] = await Promise.all([
      fetchJson("/api/stats"),
      fetchJson("/api/refresh-status"),
    ]);
    renderSystemStatus(statsData, refreshData);
    setStatus("");
  } catch (error) {
    renderSystemError(error.message);
    setStatus(error.message, true);
  } finally {
    state.loading = false;
    document.body.classList.remove("is-loading");
  }
}

function setViewMode(view) {
  state.view = view;
  const briefsActive = view === "briefs";
  const favoritesActive = view === "favorites";
  const systemActive = view === "system";
  const todayActive = view === "today";
  document.body.classList.toggle("view-briefs", briefsActive);
  document.body.classList.toggle("view-favorites", favoritesActive);
  document.body.classList.toggle("view-system", systemActive);
  dailyBriefs.hidden = !briefsActive;
  favorites.hidden = !favoritesActive;
  systemStatus.hidden = !systemActive;
  updateTopbarTitle();
  navButtons.forEach((button) => {
    const active = button.dataset.viewTarget === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  if (!todayActive) {
    state.query = "";
    search.value = "";
    setSearchMode(false);
    suggestions.hidden = true;
    suggestions.innerHTML = "";
  }
}

function setSearchMode(active) {
  document.body.classList.toggle("is-searching", active);
  overviewSections.forEach((section) => {
    section.hidden = active;
  });
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
  sidebarToggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
}

function initSidebar() {
  if (!sidebarToggle) return;
  const isMobile = window.matchMedia("(max-width: 900px)").matches;
  const storageKey = isMobile ? "newser.sidebarCollapsed.mobile" : "newser.sidebarCollapsed.desktop";
  const saved = window.localStorage.getItem(storageKey);
  const shouldCollapse = saved === null ? isMobile : saved === "true";
  setSidebarCollapsed(shouldCollapse);

  sidebarToggle.addEventListener("click", () => {
    const collapsed = !document.body.classList.contains("sidebar-collapsed");
    setSidebarCollapsed(collapsed);
    window.localStorage.setItem(storageKey, String(collapsed));
  });
}

async function loadRefreshStatus() {
  if (!refreshStatus) return;
  try {
    const data = await fetchJson("/api/refresh-status");
    refreshStatus.classList.toggle("is-updating", Boolean(data.updating));
    if (data.updating) {
      refreshStatus.textContent = "Updating sources...";
      return;
    }
    const latest = formatDate(data.latest_ingested_at);
    const next = formatDate(data.next_check_at);
    if (latest && next) {
      refreshStatus.textContent = `Last update ${latest}. Next check ${next}.`;
    } else if (latest) {
      refreshStatus.textContent = `Last update ${latest}. Automatic updates enabled.`;
    } else {
      refreshStatus.textContent = "Waiting for first automatic update.";
    }
  } catch (error) {
    refreshStatus.classList.add("is-updating");
    refreshStatus.textContent = "Automatic update status unavailable.";
  }
}

function renderStats(data) {
  return [
    ["Corpus", data.total_corpus],
    ["Last 24h", data.noticias_24h],
    ["AI coverage", `${data.ai_coverage_pct}%`],
    ["Global items", data.global_news_count],
  ]
    .map(([label, value]) => `<div class="stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`)
    .join("");
}

function renderSystemStatus(statsData, refreshData) {
  const statusLabel = refreshData.updating
    ? "Updating"
    : refreshData.last_error
      ? "Needs attention"
      : refreshData.stale
        ? "Stale"
        : "Healthy";
  systemHealthBadge.textContent = statusLabel;
  systemHealthBadge.classList.toggle("is-warning", Boolean(refreshData.stale || refreshData.last_error));
  systemHealthBadge.classList.toggle("is-updating", Boolean(refreshData.updating));

  systemHealth.innerHTML = [
    ["Update state", refreshData.updating ? "Updating sources" : "Idle"],
    ["Freshness", refreshData.stale ? "Stale" : "Fresh"],
    ["Last update", formatDate(refreshData.latest_ingested_at) || "No update yet"],
    ["Next check", formatDate(refreshData.next_check_at) || "Not scheduled"],
    ["Interval", `${escapeHtml(refreshData.interval_minutes || 0)} minutes`],
    ["Last error", refreshData.last_error || "None"],
  ]
    .map(([label, value]) => `
      <article class="system-health-item">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </article>
    `)
    .join("");

  systemMetrics.innerHTML = renderStats(statsData);
  renderSourceBreakdown(statsData.source_counts || {});
}

function renderSourceBreakdown(sourceCounts) {
  const entries = Object.entries(sourceCounts).sort((a, b) => Number(b[1]) - Number(a[1]));
  if (!entries.length) {
    sourceBreakdown.innerHTML = `<div class="empty">No source data is available yet.</div>`;
    return;
  }
  const max = Math.max(...entries.map(([, count]) => Number(count) || 0), 1);
  sourceBreakdown.innerHTML = entries
    .map(([source, count]) => {
      const pct = Math.max(3, Math.round((Number(count) || 0) / max * 100));
      return `
        <article class="source-row">
          <div>
            <strong>${escapeHtml(source)}</strong>
            <span>${escapeHtml(count)} items</span>
          </div>
          <div class="source-bar" aria-hidden="true"><span style="width: ${pct}%"></span></div>
        </article>
      `;
    })
    .join("");
}

function renderSystemError(message) {
  systemHealthBadge.textContent = "Unavailable";
  systemHealthBadge.classList.add("is-warning");
  systemHealth.innerHTML = `<div class="empty">System status could not be loaded: ${escapeHtml(message)}</div>`;
  systemMetrics.innerHTML = "";
  sourceBreakdown.innerHTML = "";
}

function renderBrief(data) {
  const title = brief.querySelector(".section-title").outerHTML;
  if (!data.available) {
    brief.innerHTML = `${title}<div class="empty">No daily brief is available for this date yet.</div>`;
    return;
  }
  const json = data.brief_json;
  let body = "";
  if (json && Array.isArray(json.items)) {
    if (json.intro) body += `<p>${escapeHtml(json.intro)}</p>`;
    body += json.items
      .map((item, index) => `
        <article class="brief-item">
          <h4>${index + 1}. ${escapeHtml(item.title || "Untitled")}</h4>
          <p>${escapeHtml(item.summary || "")}</p>
          ${item.why_it_matters ? `<p><strong>Why it matters:</strong> ${escapeHtml(item.why_it_matters)}</p>` : ""}
        </article>
      `)
      .join("");
    if (json.trend_reading) {
      body += `<article class="brief-item"><h4>Trend reading</h4><p>${escapeHtml(json.trend_reading)}</p></article>`;
    }
  } else {
    body = `<p>${escapeHtml(data.texto || "")}</p>`;
  }
  brief.innerHTML = `
    ${title}
    ${body}
    <p class="brief-meta">${escapeHtml(data.n_noticias)} articles - ${escapeHtml(data.modelo)} - ${escapeHtml(formatDate(data.fecha_generacion))}</p>
  `;
}

function renderBriefBody(data) {
  const json = data.brief_json;
  if (json && Array.isArray(json.items)) {
    let body = json.intro ? `<p>${escapeHtml(json.intro)}</p>` : "";
    body += json.items
      .map((item, index) => `
        <article class="brief-item">
          <h4>${index + 1}. ${escapeHtml(item.title || "Untitled")}</h4>
          <p>${escapeHtml(item.summary || "")}</p>
          ${item.why_it_matters ? `<p><strong>Why it matters:</strong> ${escapeHtml(item.why_it_matters)}</p>` : ""}
        </article>
      `)
      .join("");
    if (json.trend_reading) {
      body += `<article class="brief-item"><h4>Trend reading</h4><p>${escapeHtml(json.trend_reading)}</p></article>`;
    }
    return body;
  }
  return `<p>${escapeHtml(data.texto || "")}</p>`;
}

function renderDailyBriefs(items) {
  if (!items.length) {
    dailyBriefsList.innerHTML = `
      <div class="empty panel archive-empty">
        <strong>No previous daily briefs found</strong>
        <span>Newser only shows stored briefs from the previous 7 days here. Missing days are omitted.</span>
      </div>
    `;
    return;
  }
  dailyBriefsList.innerHTML = items
    .map((item) => `
      <article class="daily-brief-card">
        <h4>${escapeHtml(item.fecha)}</h4>
        <p class="daily-brief-meta">${escapeHtml(item.n_noticias)} articles - ${escapeHtml(item.modelo)} - ${escapeHtml(formatDate(item.fecha_generacion))}</p>
        <div class="daily-brief-body">${renderBriefBody(item)}</div>
      </article>
    `)
    .join("");
}

function renderFavorites(data) {
  const count = data.count || 0;
  if (!count) {
    favoritesFeed.innerHTML = `
      <div class="empty panel archive-empty">
        <strong>No favorites yet</strong>
        <span>Use the heart button on any article to save it here for follow-up.</span>
      </div>
    `;
    return;
  }
  favoritesFeed.innerHTML = data.items.map(renderArticle).join("");
  bindArticleActions(favoritesFeed);
}

function renderHotTopics(items) {
  if (!items.length) {
    hotTopics.innerHTML = `<div class="empty">No multi-source hot topics for this date yet.</div>`;
    return;
  }
  hotTopics.innerHTML = items.map(renderTopic).join("");
  hotTopics.querySelectorAll("[data-topic-toggle]").forEach((button) => {
    button.addEventListener("click", () => toggleTopicDetails(button));
  });
}

function renderTopic(topic, index) {
  const titleParts = splitStarTitle(topic.title);
  const detailId = `topic-detail-${index}`;
  const sourceLabel = Number(topic.source_count) === 1 ? "source" : "sources";
  const sources = (topic.sources || [])
    .map((source) => `<span class="topic-source-chip">${escapeHtml(source)}</span>`)
    .join("");
  const supportingItems = (topic.supporting_items || [])
    .map((item) => `
      <a class="topic-support-item" href="${escapeHtml(item.url || "#")}" target="_blank" rel="noopener">
        <span>${escapeHtml(item.source || "Source")}</span>
        <strong>${escapeHtml(item.title || "Untitled")}</strong>
        <em>${escapeHtml(Math.round(Number(item.score || 0)))} score</em>
      </a>
    `)
    .join("");
  return `
    <article class="topic-card">
      <button class="topic" type="button" data-topic-toggle aria-expanded="false" aria-controls="${detailId}">
        <div class="topic-main">
          <div class="topic-title-row">
            <strong>${escapeHtml(titleParts.title)}</strong>
            ${titleParts.stars ? `<span class="topic-star-metric">${renderStarCount(titleParts.stars)}</span>` : ""}
          </div>
          <span>${escapeHtml(topic.topic)} - ${escapeHtml(topic.items)} items</span>
        </div>
        <span class="topic-source-count">${escapeHtml(topic.source_count)} ${sourceLabel}</span>
      </button>
      <div id="${detailId}" class="topic-detail" hidden>
        <div class="topic-detail-stat">
          <span>Theme</span>
          <strong>${escapeHtml(topic.topic)}</strong>
        </div>
        <div class="topic-detail-stat">
          <span>Related items</span>
          <strong>${escapeHtml(topic.items)}</strong>
        </div>
        <div class="topic-detail-stat">
          <span>Sources</span>
          <strong>${escapeHtml(topic.source_count)}</strong>
        </div>
        <div class="topic-sources" aria-label="Supporting sources">${sources}</div>
        <div class="topic-support-list">
          <span>Supporting articles</span>
          ${supportingItems || "<p>No supporting articles available.</p>"}
        </div>
      </div>
    </article>
  `;
}

function toggleTopicDetails(button) {
  const detail = document.getElementById(button.getAttribute("aria-controls"));
  if (!detail) return;
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  detail.hidden = expanded;
}

function renderFeed(data) {
  const count = data.count || 0;
  feedTitle.textContent = state.query ? "Search results" : "Trends";
  feedMeta.textContent = `${count} publications - ${data.orden}`;
  if (!count) {
    feed.innerHTML = `<div class="empty panel">No publications match the active filters.</div>`;
    return;
  }
  feed.innerHTML = data.items.map(renderArticle).join("");
  bindArticleActions(feed);
}

function bindArticleActions(root) {
  root.querySelectorAll("[data-summary]").forEach((button) => {
    button.addEventListener("click", () => generateSummary(button.dataset.summary));
  });
  root.querySelectorAll("[data-favorite]").forEach((button) => {
    button.addEventListener("click", () => toggleFavorite(button.dataset.favorite, button));
  });
}

function renderArticle(item) {
  const titleParts = splitStarTitle(item.label || item.titulo);
  const summary = hasSummary(item) ? item.resumen_ia : item.descripcion;
  const time = formatDate(item.fuente === "GitHub Trending" ? item.fecha_ingesta : item.fecha_publicacion);
  const tags = (item.tags || []).slice(0, 4).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
  const metric = item.fuente === "GitHub Trending"
    ? `${Number(item.metric || 0).toLocaleString()} stars today`
    : item.fuente === "Hacker News"
      ? `${Number(item.metric || item.comments || 0).toLocaleString()} points`
      : "";
  const discussion = item.discussion_url
    ? `<a href="${escapeHtml(item.discussion_url)}" target="_blank" rel="noreferrer">${escapeHtml(item.comments)} comments</a>`
    : "";
  const summaryAction = hasSummary(item)
    ? ""
    : `<button type="button" data-summary="${escapeHtml(item.id)}">Generate summary</button>`;
  const favoriteLabel = item.is_favorite ? "Remove from favorites" : "Add to favorites";
  const favoriteButton = `
    <button
      class="favorite-button${item.is_favorite ? " active" : ""}"
      type="button"
      data-favorite="${escapeHtml(item.id)}"
      aria-pressed="${item.is_favorite ? "true" : "false"}"
      title="${favoriteLabel}"
      aria-label="${favoriteLabel}"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <path d="M8 13.8 6.98 12.88C3.36 9.59 1 7.45 1 4.82 1 2.68 2.68 1 4.82 1c1.2 0 2.35.56 3.1 1.45h.16A4.04 4.04 0 0 1 11.18 1C13.32 1 15 2.68 15 4.82c0 2.63-2.36 4.77-5.98 8.06L8 13.8Z"></path>
      </svg>
    </button>
  `;

  return `
    <article class="article" id="article-${escapeHtml(item.id)}">
      <div class="article-top">
        <div>
          <div class="article-meta">${escapeHtml(item.fuente)}${time ? ` - ${escapeHtml(time)}` : ""}</div>
          <div class="badge-row"><span class="badge">${escapeHtml(item.area_label)}</span></div>
        </div>
        <div class="article-side">
          <div class="score">${Number(item.selected_score || 0).toFixed(0)}</div>
          ${favoriteButton}
        </div>
      </div>
      <div class="article-title-row">
        <h4>${escapeHtml(titleParts.title)}</h4>
        ${titleParts.stars ? `<div class="article-star-metric">${renderStarCount(titleParts.stars)}</div>` : ""}
      </div>
      ${summary ? `<p class="article-summary">${escapeHtml(summary).slice(0, 420)}</p>` : ""}
      ${tags ? `<div class="tag-row">${tags}</div>` : ""}
      ${item.selection_reason ? `<p class="article-reason">${escapeHtml(item.selection_reason)}</p>` : ""}
      <div class="article-foot">
        <span>${escapeHtml(metric || (item.ranking ? `Ranking #${item.ranking}` : "Trending"))}</span>
        <div class="article-actions">
          ${discussion}
          ${summaryAction}
          ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">Read original</a>` : ""}
        </div>
      </div>
    </article>
  `;
}

async function generateSummary(articleId) {
  setStatus("Generating summary...");
  try {
    const result = await fetchJson(`/api/articles/${encodeURIComponent(articleId)}/summary`, { method: "POST" });
    setStatus(result.cached ? "Summary already exists." : "Summary generated.");
    await loadAll();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function toggleFavorite(articleId, button) {
  const wasFavorite = button.getAttribute("aria-pressed") === "true";
  button.disabled = true;
  try {
    const result = await fetchJson(`/api/articles/${encodeURIComponent(articleId)}/favorite`, {
      method: wasFavorite ? "DELETE" : "POST",
    });
    if (state.view === "favorites" && !result.is_favorite) {
      await loadFavorites();
      setStatus("Removed from favorites.");
      return;
    }
    updateFavoriteButtons(articleId, Boolean(result.is_favorite));
    setStatus(result.is_favorite ? "Saved to favorites." : "Removed from favorites.");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function updateFavoriteButtons(articleId, isFavorite) {
  document.querySelectorAll("[data-favorite]").forEach((button) => {
    if (button.dataset.favorite !== articleId) return;
    button.classList.toggle("active", isFavorite);
    button.setAttribute("aria-pressed", String(isFavorite));
    button.setAttribute("title", isFavorite ? "Remove from favorites" : "Add to favorites");
    button.setAttribute("aria-label", isFavorite ? "Remove from favorites" : "Add to favorites");
  });
}

function submitSearch() {
  state.query = search.value.trim();
  window.clearTimeout(search._timer);
  suggestions.hidden = true;
  suggestions.innerHTML = "";
  loadAll();
}

async function loadSuggestions() {
  const q = search.value.trim();
  if (q.length < 2) {
    suggestions.hidden = true;
    suggestions.innerHTML = "";
    return;
  }
  try {
    const params = formParams();
    params.set("q", q);
    const data = await fetchJson(`/api/search/suggestions?${params}`);
    if (!data.suggestions.length) {
      suggestions.hidden = true;
      return;
    }
    suggestions.innerHTML = data.suggestions
      .map((item) => `
        <button type="button" data-title="${escapeHtml(item.title)}">
          ${escapeHtml(item.title)}
          <small>${escapeHtml(item.source)} - score ${escapeHtml(item.score)}</small>
        </button>
      `)
      .join("");
    suggestions.hidden = false;
    suggestions.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        search.value = button.dataset.title || "";
        state.query = search.value.trim();
        suggestions.hidden = true;
        loadAll();
      });
    });
  } catch {
    suggestions.hidden = true;
  }
}

function updateMultiSelectLabel(root) {
  const label = root.querySelector("[data-label]");
  const options = Array.from(root.querySelectorAll('input[name="fuentes"], input[name="areas"]'));
  const selected = options.filter((input) => input.checked);
  const type = options[0]?.name === "fuentes" ? "sources" : "areas";
  if (!label) return;
  if (selected.length === options.length) {
    label.textContent = `All ${type}`;
  } else if (selected.length === 1) {
    label.textContent = selected[0].nextElementSibling?.textContent || `1 ${type.slice(0, -1)}`;
  } else {
    label.textContent = `${selected.length} ${type}`;
  }
}

function syncSelectAll(root) {
  const selectAll = root.querySelector("[data-select-all]");
  const options = Array.from(root.querySelectorAll('input[name="fuentes"], input[name="areas"]'));
  if (!selectAll || !options.length) return;
  const checkedCount = options.filter((input) => input.checked).length;
  selectAll.checked = checkedCount === options.length;
  selectAll.indeterminate = checkedCount > 0 && checkedCount < options.length;
  updateMultiSelectLabel(root);
}

function initMultiSelects() {
  document.querySelectorAll("[data-multiselect]").forEach((root) => {
    const button = root.querySelector(".multi-select-button");
    const selectAll = root.querySelector("[data-select-all]");
    const options = Array.from(root.querySelectorAll('input[name="fuentes"], input[name="areas"]'));
    syncSelectAll(root);

    button.addEventListener("click", () => {
      const open = root.classList.toggle("open");
      button.setAttribute("aria-expanded", String(open));
    });

    selectAll.addEventListener("change", () => {
      options.forEach((input) => {
        input.checked = selectAll.checked;
      });
      syncSelectAll(root);
    });

    options.forEach((input) => {
      input.addEventListener("change", () => {
        syncSelectAll(root);
      });
    });
  });

  document.addEventListener("click", (event) => {
    document.querySelectorAll("[data-multiselect].open").forEach((root) => {
      if (root.contains(event.target)) return;
      root.classList.remove("open");
      root.querySelector(".multi-select-button")?.setAttribute("aria-expanded", "false");
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll("[data-multiselect].open").forEach((root) => {
      root.classList.remove("open");
      root.querySelector(".multi-select-button")?.setAttribute("aria-expanded", "false");
    });
  });
}

filters.addEventListener("change", () => {
  loadAll();
  loadSuggestions();
});
navButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const target = button.dataset.viewTarget || "today";
    if (target === state.view) return;
    if (target === "today") {
      setViewMode("today");
      loadAll();
    } else if (target === "briefs") {
      loadDailyBriefs();
    } else if (target === "favorites") {
      loadFavorites();
    } else {
      loadSystemStatus();
    }
  });
});
search.addEventListener("input", () => {
  if (state.view !== "today") return;
  state.query = search.value.trim();
  window.clearTimeout(search._timer);
  search._timer = window.setTimeout(() => {
    loadSuggestions();
    loadAll();
  }, 250);
});
search.addEventListener("keydown", (event) => {
  if (state.view !== "today") return;
  if (event.key !== "Enter") return;
  event.preventDefault();
  submitSearch();
});
clearSearch.addEventListener("click", () => {
  search.value = "";
  state.query = "";
  suggestions.hidden = true;
  loadAll();
});

initSidebar();
initMultiSelects();
loadAll();
loadRefreshStatus();
window.setInterval(loadRefreshStatus, 30000);
window.setInterval(loadAll, 300000);
