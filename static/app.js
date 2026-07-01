const state = {
  query: "",
  loading: false,
  view: "today",
  language: window.localStorage.getItem("newser.language") === "en" ? "en" : "es",
  sourcePreferences: {},
  appliedSourcePreferences: {},
};

const I18N = {
  es: {
    "brand.tagline": "Analizador de tendencias IT",
    "sidebar.collapse": "Contraer barra lateral",
    "sidebar.expand": "Expandir barra lateral",
    "nav.main": "Navegación principal",
    "nav.workspace": "Espacio de trabajo",
    "nav.today": "Actualizaciones de hoy",
    "nav.todayShort": "Actualizaciones",
    "nav.briefs": "Briefs diarios",
    "nav.favorites": "Favoritos",
    "nav.sources": "Fuentes",
    "nav.more": "Más",
    "filters.title": "Controles del feed",
    "filters.date": "Fecha",
    "filters.today": "Hoy",
    "filters.allDates": "Todas las fechas",
    "filters.allSources": "Todas las fuentes",
    "filters.allAreas": "Todas las áreas",
    "filters.selectAll": "Seleccionar todo",
    "filters.order": "Orden",
    "filters.score": "Puntaje",
    "filters.recent": "Más reciente",
    "filters.sources": "fuentes",
    "filters.areas": "áreas",
    "prefs.title": "Preferencias",
    "prefs.language": "Idioma",
    "prefs.appearance": "Apariencia",
    "theme.toLight": "Cambiar a modo claro",
    "theme.toDark": "Cambiar a modo oscuro",
    "theme.light": "Claro",
    "theme.dark": "Oscuro",
    "mobile.openFilters": "Abrir filtros y ajustes",
    "mobile.navigation": "Navegación móvil",
    "mobile.updates": "Actualizaciones",
    "mobile.briefs": "Briefs",
    "mobile.saved": "Guardados",
    "mobile.more": "Más",
    "search.placeholder": "Buscar",
    "search.clear": "Limpiar búsqueda",
    "search.results": "Resultados de búsqueda",
    "status.loadingSearch": "Cargando resultados de búsqueda...",
    "status.loadingDashboard": "Cargando panel...",
    "status.loadingBriefs": "Cargando briefs diarios...",
    "status.loadingFavorites": "Cargando favoritos...",
    "status.loadingSources": "Cargando preferencias de fuentes...",
    "status.sourcesApplied": "Preferencias aplicadas a los filtros.",
    "status.sourcesReset": "Preferencias de fuentes restablecidas.",
    "status.generatingSummary": "Generando resumen...",
    "status.summaryCached": "El resumen ya existe.",
    "status.summaryGenerated": "Resumen generado.",
    "error.requestFailed": "La solicitud falló.",
    "date.today": "Hoy",
    "date.all": "Todas las fechas",
    "brief.executive": "Resumen ejecutivo",
    "brief.loading": "Cargando brief...",
    "brief.archive": "Archivo",
    "brief.previous": "Briefs diarios anteriores",
    "brief.generating": "El brief de hoy se está generando. Actualizá esta sección en un momento.",
    "brief.missing": "Todavía no hay brief diario disponible para esta fecha.",
    "brief.noPreviousTitle": "No se encontraron briefs diarios anteriores",
    "brief.noPreviousBody": "Newser solo muestra aquí briefs guardados de los últimos 7 días. Los días faltantes se omiten.",
    "brief.why": "Por qué importa:",
    "brief.trend": "Lectura de tendencias",
    "brief.articles": "artículos",
    "topics.hot": "Temas activos",
    "topics.empty": "Todavía no hay temas multi-fuente para esta fecha.",
    "topics.sourceSingular": "fuente",
    "topics.sourcePlural": "fuentes",
    "topics.items": "items",
    "topics.theme": "Tema",
    "topics.related": "Items relacionados",
    "topics.sources": "Fuentes",
    "topics.supporting": "Artículos de soporte",
    "topics.noSupporting": "No hay artículos de soporte disponibles.",
    "feed.trends": "Tendencias",
    "feed.publications": "publicaciones",
    "feed.empty": "Ninguna publicación coincide con los filtros activos.",
    "article.untitled": "Sin título",
    "article.media": "Media del artículo",
    "article.openImage": "Abrir vista previa de imagen",
    "article.openVideo": "Abrir fuente del video",
    "article.preview": "Vista previa de imagen del artículo",
    "article.generate": "Generar resumen",
    "article.addFavorite": "Agregar a favoritos",
    "article.removeFavorite": "Quitar de favoritos",
    "article.starsToday": "estrellas hoy",
    "article.points": "puntos",
    "article.comments": "comentarios",
    "article.ranking": "Ranking",
    "article.trending": "Tendencia",
    "article.readOriginal": "Leer original",
    "favorites.emptyTitle": "Todavía no hay favoritos",
    "favorites.emptyBody": "Usá el botón de corazón en cualquier artículo para guardarlo acá.",
    "favorites.loadError": "No se pudieron cargar los favoritos:",
    "source.fallback": "Fuente",
    "sources.title": "Fuentes",
    "sources.apply": "Aplicar",
    "sources.applied": "Aplicado",
    "sources.reset": "Restablecer",
    "sources.prioritized": "Prioritaria",
    "sources.normal": "Normal",
    "sources.hidden": "Oculta",
    "sources.badgePrioritized": "Prioritaria",
    "sources.role.GitHubTrending": "Repositorios y proyectos open source en tendencia.",
    "sources.role.HackerNews": "Discusión técnica y señales tempranas de comunidad.",
    "sources.role.Reuters": "Cobertura amplia de noticias tecnológicas.",
    "sources.role.GitHubBlog": "Actualizaciones oficiales de la plataforma GitHub.",
    "sources.role.OpenAIBlog": "Actualizaciones oficiales de OpenAI e IA.",
    "stats.corpus": "Corpus",
    "stats.last24h": "Últimas 24h",
    "stats.aiCoverage": "Cobertura IA",
    "stats.globalItems": "Items globales",
    "media.preview": "Vista previa de imagen",
    "media.close": "Cerrar vista previa",
    "area.ai_agents": "IA y agentes",
    "area.developer_tools": "Herramientas dev",
    "area.cybersecurity": "Ciberseguridad",
    "area.infrastructure_cloud": "Infraestructura y cloud",
    "area.chips_hardware": "Chips y hardware",
  },
  en: {
    "brand.tagline": "IT News Trend Analyzer",
    "sidebar.collapse": "Collapse sidebar",
    "sidebar.expand": "Expand sidebar",
    "nav.main": "Main navigation",
    "nav.workspace": "Workspace",
    "nav.today": "Today's Updates",
    "nav.todayShort": "Updates",
    "nav.briefs": "Daily Briefs",
    "nav.favorites": "Favorites",
    "nav.sources": "Sources",
    "nav.more": "More",
    "filters.title": "Feed controls",
    "filters.date": "Date",
    "filters.today": "Today",
    "filters.allDates": "All dates",
    "filters.allSources": "All sources",
    "filters.allAreas": "All areas",
    "filters.selectAll": "Select all",
    "filters.order": "Order",
    "filters.score": "Score",
    "filters.recent": "Most recent",
    "filters.sources": "sources",
    "filters.areas": "areas",
    "prefs.title": "Preferences",
    "prefs.language": "Language",
    "prefs.appearance": "Appearance",
    "theme.toLight": "Switch to light mode",
    "theme.toDark": "Switch to dark mode",
    "theme.light": "Light",
    "theme.dark": "Dark",
    "mobile.openFilters": "Open filters and settings",
    "mobile.navigation": "Mobile navigation",
    "mobile.updates": "Updates",
    "mobile.briefs": "Briefs",
    "mobile.saved": "Saved",
    "mobile.more": "More",
    "search.placeholder": "Search",
    "search.clear": "Clear search",
    "search.results": "Search results",
    "status.loadingSearch": "Loading search results...",
    "status.loadingDashboard": "Loading dashboard...",
    "status.loadingBriefs": "Loading daily briefs...",
    "status.loadingFavorites": "Loading favorites...",
    "status.loadingSources": "Loading source preferences...",
    "status.sourcesApplied": "Source preferences applied to filters.",
    "status.sourcesReset": "Source preferences reset.",
    "status.generatingSummary": "Generating summary...",
    "status.summaryCached": "Summary already exists.",
    "status.summaryGenerated": "Summary generated.",
    "error.requestFailed": "Request failed.",
    "date.today": "Today",
    "date.all": "All dates",
    "brief.executive": "Executive summary",
    "brief.loading": "Loading brief...",
    "brief.archive": "Archive",
    "brief.previous": "Previous daily briefs",
    "brief.generating": "Today's brief is being generated. Refresh this section in a moment.",
    "brief.missing": "No daily brief is available for this date yet.",
    "brief.noPreviousTitle": "No previous daily briefs found",
    "brief.noPreviousBody": "Newser only shows stored briefs from the previous 7 days here. Missing days are omitted.",
    "brief.why": "Why it matters:",
    "brief.trend": "Trend reading",
    "brief.articles": "articles",
    "topics.hot": "Hot topics",
    "topics.empty": "No multi-source hot topics for this date yet.",
    "topics.sourceSingular": "source",
    "topics.sourcePlural": "sources",
    "topics.items": "items",
    "topics.theme": "Theme",
    "topics.related": "Related items",
    "topics.sources": "Sources",
    "topics.supporting": "Supporting articles",
    "topics.noSupporting": "No supporting articles available.",
    "feed.trends": "Trends",
    "feed.publications": "publications",
    "feed.empty": "No publications match the active filters.",
    "article.untitled": "Untitled",
    "article.media": "Article media",
    "article.openImage": "Open image preview",
    "article.openVideo": "Open video source",
    "article.preview": "Article image preview",
    "article.generate": "Generate summary",
    "article.addFavorite": "Add to favorites",
    "article.removeFavorite": "Remove from favorites",
    "article.starsToday": "stars today",
    "article.points": "points",
    "article.comments": "comments",
    "article.ranking": "Ranking",
    "article.trending": "Trending",
    "article.readOriginal": "Read original",
    "favorites.emptyTitle": "No favorites yet",
    "favorites.emptyBody": "Use the heart button on any article to save it here for follow-up.",
    "favorites.loadError": "Favorites could not be loaded:",
    "source.fallback": "Source",
    "sources.title": "Sources",
    "sources.apply": "Apply",
    "sources.applied": "Applied",
    "sources.reset": "Reset sources",
    "sources.prioritized": "Prioritized",
    "sources.normal": "Normal",
    "sources.hidden": "Hidden",
    "sources.badgePrioritized": "Prioritized",
    "sources.role.GitHubTrending": "Trending open-source repositories and projects.",
    "sources.role.HackerNews": "Technical discussion and early community signals.",
    "sources.role.Reuters": "Broad technology news coverage.",
    "sources.role.GitHubBlog": "Official GitHub platform updates.",
    "sources.role.OpenAIBlog": "Official OpenAI and AI updates.",
    "stats.corpus": "Corpus",
    "stats.last24h": "Last 24h",
    "stats.aiCoverage": "AI coverage",
    "stats.globalItems": "Global items",
    "media.preview": "Image preview",
    "media.close": "Close image preview",
    "area.ai_agents": "AI & Agents",
    "area.developer_tools": "Developer Tools",
    "area.cybersecurity": "Cybersecurity",
    "area.infrastructure_cloud": "Infrastructure & Cloud",
    "area.chips_hardware": "Chips & Hardware",
  },
};

const filters = document.querySelector("#filters");
const sidebarToggle = document.querySelector("#sidebar-toggle");
const themeToggles = document.querySelectorAll("#desktop-theme-toggle, [data-mobile-theme-action]");
const themeStateLabels = document.querySelectorAll("[data-theme-state]");
const languageButtons = document.querySelectorAll("[data-language-option]");
const mobileMenuToggle = document.querySelector("#mobile-menu-toggle");
const mobileDrawerBackdrop = document.querySelector("#mobile-drawer-backdrop");
const mobileViewLabel = document.querySelector("#mobile-view-label");
const mobileMore = document.querySelector("#mobile-more");
const navButtons = document.querySelectorAll("[data-view-target]");
const feed = document.querySelector("#feed");
const feedTitle = document.querySelector("#feed-title");
const feedMeta = document.querySelector("#feed-meta");
const topbarTitle = document.querySelector(".topbar h2");
const topbarTitleMain = document.querySelector("#topbar-title-main");
const topbarDate = document.querySelector("#topbar-date");
const allDatesToggle = document.querySelector("[data-all-dates]");
const dateModeLabel = document.querySelector("[data-date-mode-label]");
const stats = document.querySelector("#stats");
const brief = document.querySelector("#brief");
const hotTopics = document.querySelector("#hot-topics");
const statusLine = document.querySelector("#status");
const search = document.querySelector("#search");
const suggestions = document.querySelector("#suggestions");
const clearSearch = document.querySelector("#clear-search");
const overviewSections = document.querySelectorAll(".overview-only");
const dailyBriefs = document.querySelector("#daily-briefs");
const dailyBriefsList = document.querySelector("#daily-briefs-list");
const favorites = document.querySelector("#favorites");
const favoritesFeed = document.querySelector("#favorites-feed");
const sourcePreferencesPanel = document.querySelector("#source-preferences");
const sourcePreferenceButtons = document.querySelectorAll("[data-source-preference]");
const sourceActionButtons = document.querySelectorAll("[data-source-action]");
const mediaModal = document.querySelector("#media-modal");
const mediaModalImage = document.querySelector("#media-modal-image");
const mediaModalClose = document.querySelector("#media-modal-close");
const SOURCE_PREFERENCE_STORAGE_KEY = "newser.sourcePreferences";
const SOURCE_PREFERENCE_VALUES = new Set(["prioritized", "normal", "hidden"]);

function i18n(key) {
  return I18N[state.language]?.[key] || I18N.es[key] || key;
}

function locale() {
  return state.language === "en" ? "en-US" : "es-AR";
}

function withLanguage(url) {
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}lang=${encodeURIComponent(state.language)}`;
}

function applyTranslations() {
  document.documentElement.lang = state.language;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = i18n(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
    node.setAttribute("aria-label", i18n(node.dataset.i18nAriaLabel));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((node) => {
    node.setAttribute("title", i18n(node.dataset.i18nTitle));
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", i18n(node.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-area-label]").forEach((node) => {
    node.textContent = i18n(`area.${node.dataset.areaLabel}`);
  });
  languageButtons.forEach((button) => {
    const active = button.dataset.languageOption === state.language;
    button.setAttribute("aria-pressed", String(active));
  });
  setTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
  syncDateMode();
  updateMultiSelectLabels();
  updateTopbarTitle();
}

function setLanguage(language) {
  const nextLanguage = language === "en" ? "en" : "es";
  if (state.language === nextLanguage) return;
  state.language = nextLanguage;
  window.localStorage.setItem("newser.language", nextLanguage);
  applyTranslations();
  loadAll();
}

function setStatus(message, isError = false) {
  statusLine.textContent = message || "";
  statusLine.classList.toggle("error", isError);
}

function sourceInputs() {
  return Array.from(filters.querySelectorAll('input[name="fuentes"]'));
}

function sourceNames() {
  return sourceInputs().map((input) => input.value).filter(Boolean);
}

function defaultSourcePreferences() {
  return Object.fromEntries(sourceNames().map((source) => [source, "normal"]));
}

function loadSourcePreferences() {
  const defaults = defaultSourcePreferences();
  try {
    const saved = JSON.parse(window.localStorage.getItem(SOURCE_PREFERENCE_STORAGE_KEY) || "{}");
    Object.keys(defaults).forEach((source) => {
      if (SOURCE_PREFERENCE_VALUES.has(saved[source])) {
        defaults[source] = saved[source];
      }
    });
  } catch {
    // Keep defaults when localStorage contains invalid JSON.
  }
  return defaults;
}

function saveSourcePreferences() {
  window.localStorage.setItem(SOURCE_PREFERENCE_STORAGE_KEY, JSON.stringify(state.sourcePreferences));
}

function renderSourcePreferenceControls() {
  sourcePreferenceButtons.forEach((button) => {
    const value = state.sourcePreferences[button.dataset.sourcePreference] || "normal";
    button.setAttribute("aria-pressed", String(button.dataset.sourceValue === value));
  });
}

function visibleMultiSelectOptions(root) {
  return Array.from(root.querySelectorAll('input[name="fuentes"], input[name="areas"]'))
    .filter((input) => !input.disabled && !input.closest("[hidden]"));
}

function sourceFilterRoot() {
  return sourceInputs()[0]?.closest("[data-multiselect]") || null;
}

function syncSourceFilterVisibility() {
  sourceInputs().forEach((input) => {
    const hidden = state.appliedSourcePreferences[input.value] === "hidden";
    const wasHidden = input.disabled;
    input.disabled = hidden;
    if (hidden) {
      input.checked = false;
    } else if (wasHidden) {
      input.checked = true;
    }
    const row = input.closest("label");
    if (row) row.hidden = hidden;
  });
  const root = sourceFilterRoot();
  if (root) syncSelectAll(root);
}

function applySourcePreferencesToFilters() {
  state.appliedSourcePreferences = { ...state.sourcePreferences };
  saveSourcePreferences();
  syncSourceFilterVisibility();
  sourceInputs().forEach((input) => {
    if (!input.disabled) input.checked = true;
  });
  const root = sourceFilterRoot();
  if (root) syncSelectAll(root);
}

function resetSourcePreferences() {
  state.sourcePreferences = defaultSourcePreferences();
  state.appliedSourcePreferences = { ...state.sourcePreferences };
  saveSourcePreferences();
  renderSourcePreferenceControls();
  syncSourceFilterVisibility();
}

function showSourceApplyFeedback(button) {
  const label = button.querySelector("[data-source-apply-label]");
  window.clearTimeout(button._sourceApplyTimer);
  button.classList.add("is-confirmed");
  button.setAttribute("aria-label", i18n("sources.applied"));
  if (label) label.textContent = i18n("sources.applied");
  button._sourceApplyTimer = window.setTimeout(() => {
    button.classList.remove("is-confirmed");
    button.setAttribute("aria-label", i18n("sources.apply"));
    if (label) label.textContent = i18n("sources.apply");
  }, 1200);
}

function checkedPrioritizedSources() {
  return sourceInputs()
    .filter((input) => !input.disabled && input.checked && state.appliedSourcePreferences[input.value] === "prioritized")
    .map((input) => input.value);
}

function initSourcePreferences() {
  state.sourcePreferences = loadSourcePreferences();
  state.appliedSourcePreferences = { ...state.sourcePreferences };
  renderSourcePreferenceControls();
  syncSourceFilterVisibility();
  sourcePreferenceButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const source = button.dataset.sourcePreference || "";
      const value = button.dataset.sourceValue || "normal";
      if (!source || !SOURCE_PREFERENCE_VALUES.has(value)) return;
      state.sourcePreferences[source] = value;
      renderSourcePreferenceControls();
    });
  });
  sourceActionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.sourceAction === "reset") {
        resetSourcePreferences();
        setStatus(i18n("status.sourcesReset"));
        loadAll();
        loadSuggestions();
      } else {
        applySourcePreferencesToFilters();
        setStatus(i18n("status.sourcesApplied"));
        showSourceApplyFeedback(button);
        loadAll();
        loadSuggestions();
      }
    });
  });
}

function formParams() {
  const data = new FormData(filters);
  const params = new URLSearchParams();
  const fecha = data.get("fecha");
  const orden = data.get("orden") || "Puntaje";
  if (allDatesToggle?.checked) {
    params.set("fecha", "all");
  } else if (fecha) {
    params.set("fecha", fecha);
  }
  params.set("orden", orden);
  params.set("lang", state.language);
  for (const source of data.getAll("fuentes")) params.append("fuentes", source);
  for (const source of checkedPrioritizedSources()) params.append("prioritized_fuentes", source);
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
  return date.toLocaleString(locale(), {
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
  return date.toLocaleDateString(locale(), {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function updateTopbarTitle() {
  const briefsActive = state.view === "briefs";
  const favoritesActive = state.view === "favorites";
  const sourcesActive = state.view === "sources";
  const moreActive = state.view === "more";
  const title = briefsActive
    ? i18n("nav.briefs")
    : favoritesActive
      ? i18n("nav.favorites")
      : sourcesActive
        ? i18n("nav.sources")
        : moreActive
          ? i18n("nav.more")
          : i18n("nav.today");

  if (topbarTitleMain) {
    topbarTitleMain.textContent = title;
  } else {
    topbarTitle.textContent = title;
  }

  if (!topbarDate) return;
  const dateInput = filters.querySelector('input[name="fecha"]');
  const allDates = Boolean(allDatesToggle?.checked);
  const selectedDate = dateInput?.value || "";
  const latestDate = dateInput?.max || "";
  const showDate = state.view === "today" && (allDates || (selectedDate && latestDate && selectedDate !== latestDate));
  topbarDate.hidden = !showDate;
  topbarDate.textContent = allDates ? i18n("date.all") : (showDate ? formatFeedDate(selectedDate) : "");
  if (mobileViewLabel) {
    mobileViewLabel.textContent = allDates ? i18n("date.all") : (showDate ? formatFeedDate(selectedDate) : (state.view === "today" ? i18n("nav.todayShort") : title));
  }
}

function syncDateMode() {
  const dateInput = filters.querySelector('input[name="fecha"]');
  const allDates = Boolean(allDatesToggle?.checked);
  if (dateInput) dateInput.disabled = allDates;
  if (dateModeLabel) dateModeLabel.textContent = allDates ? i18n("date.all") : i18n("date.today");
  updateTopbarTitle();
}

function hasSummary(item) {
  const value = (item.resumen_ia || "").trim();
  return value && value !== "Resumen no disponible";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.reason || data.detail || i18n("error.requestFailed"));
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
  if (state.view === "sources") {
    setViewMode("sources");
    setStatus("");
    return;
  }
  if (state.view === "more") {
    updateTopbarTitle();
    return;
  }
  if (state.loading) return;
  updateTopbarTitle();
  state.loading = true;
  document.body.classList.add("is-loading");
  const searchActive = Boolean(state.query);
  setSearchMode(searchActive);
  setStatus(searchActive ? i18n("status.loadingSearch") : i18n("status.loadingDashboard"));
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
  setStatus(i18n("status.loadingBriefs"));
  try {
    const [briefData, archiveData] = await Promise.all([
      fetchJson(withLanguage("/api/brief")),
      fetchJson(withLanguage("/api/daily-briefs")),
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
  setStatus(i18n("status.loadingFavorites"));
  try {
    const data = await fetchJson(withLanguage("/api/favorites"));
    renderFavorites(data);
    setStatus("");
  } catch (error) {
    favoritesFeed.innerHTML = `<div class="empty panel">${i18n("favorites.loadError")} ${escapeHtml(error.message)}</div>`;
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
  const sourcesActive = view === "sources";
  const moreActive = view === "more";
  const todayActive = view === "today";
  document.body.classList.toggle("view-briefs", briefsActive);
  document.body.classList.toggle("view-favorites", favoritesActive);
  document.body.classList.toggle("view-sources", sourcesActive);
  document.body.classList.toggle("view-more", moreActive);
  dailyBriefs.hidden = !briefsActive;
  favorites.hidden = !favoritesActive;
  if (sourcePreferencesPanel) sourcePreferencesPanel.hidden = !sourcesActive;
  if (mobileMore) mobileMore.hidden = !moreActive;
  if (mobileMenuToggle) mobileMenuToggle.hidden = !todayActive;
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
  closeMobileDrawer();
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
  sidebarToggle.setAttribute("aria-label", collapsed ? i18n("sidebar.expand") : i18n("sidebar.collapse"));
}

function setTheme(theme) {
  const selectedTheme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = selectedTheme;
  window.localStorage.setItem("newser.theme", selectedTheme);
  const isLight = selectedTheme === "light";
  themeToggles.forEach((button) => {
    button.setAttribute("aria-pressed", String(isLight));
    button.setAttribute("aria-label", isLight ? i18n("theme.toDark") : i18n("theme.toLight"));
    button.setAttribute("title", isLight ? i18n("theme.toDark") : i18n("theme.toLight"));
  });
  themeStateLabels.forEach((label) => {
    label.textContent = isLight ? i18n("theme.light") : i18n("theme.dark");
  });
}

function initTheme() {
  const savedTheme = window.localStorage.getItem("newser.theme") || "dark";
  setTheme(savedTheme);
  themeToggles.forEach((button) => button.addEventListener("click", () => {
    const currentTheme = document.documentElement.dataset.theme === "light" ? "light" : "dark";
    setTheme(currentTheme === "light" ? "dark" : "light");
  }));
}

function initLanguage() {
  applyTranslations();
  languageButtons.forEach((button) => {
    button.addEventListener("click", () => setLanguage(button.dataset.languageOption || "es"));
  });
}

function isPhoneViewport() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function openMobileDrawer() {
  if (!isPhoneViewport()) return;
  document.body.classList.add("mobile-drawer-open");
  if (mobileDrawerBackdrop) mobileDrawerBackdrop.hidden = false;
  mobileMenuToggle?.setAttribute("aria-expanded", "true");
}

function closeMobileDrawer() {
  document.body.classList.remove("mobile-drawer-open");
  if (mobileDrawerBackdrop) mobileDrawerBackdrop.hidden = true;
  mobileMenuToggle?.setAttribute("aria-expanded", "false");
}

function initMobileShell() {
  mobileMenuToggle?.addEventListener("click", () => {
    if (document.body.classList.contains("mobile-drawer-open")) {
      closeMobileDrawer();
    } else {
      openMobileDrawer();
    }
  });
  mobileDrawerBackdrop?.addEventListener("click", closeMobileDrawer);
  window.addEventListener("resize", () => {
    if (!isPhoneViewport()) closeMobileDrawer();
  });
}

function initSidebar() {
  if (!sidebarToggle) return;
  const isMobile = window.matchMedia("(max-width: 900px)").matches;
  const storageKey = isMobile ? "newser.sidebarCollapsed.mobile" : "newser.sidebarCollapsed.desktop";
  const saved = window.localStorage.getItem(storageKey);
  const shouldCollapse = saved === null ? isMobile : saved === "true";
  setSidebarCollapsed(shouldCollapse);

  sidebarToggle.addEventListener("click", () => {
    if (isPhoneViewport()) {
      closeMobileDrawer();
      return;
    }
    const collapsed = !document.body.classList.contains("sidebar-collapsed");
    setSidebarCollapsed(collapsed);
    window.localStorage.setItem(storageKey, String(collapsed));
  });
}

function renderBrief(data) {
  if (!data.available) {
    const missingMessage = data.catchup_started || data.catchup_running
      ? i18n("brief.generating")
      : i18n("brief.missing");
    brief.innerHTML = renderCurrentBriefShell(
      `<div class="empty">${escapeHtml(missingMessage)}</div>`,
      "",
    );
    bindCurrentBriefToggle();
    return;
  }
  const json = data.brief_json;
  let body = "";
  if (json && Array.isArray(json.items)) {
    if (json.intro) body += `<p>${escapeHtml(json.intro)}</p>`;
    body += json.items
      .map((item, index) => `
        <article class="brief-item">
          <h4>${index + 1}. ${escapeHtml(item.title || i18n("article.untitled"))}</h4>
          <p>${escapeHtml(item.summary || "")}</p>
          ${item.why_it_matters ? `<p><strong>${i18n("brief.why")}</strong> ${escapeHtml(item.why_it_matters)}</p>` : ""}
        </article>
      `)
      .join("");
    if (json.trend_reading) {
      body += `<article class="brief-item"><h4>${i18n("brief.trend")}</h4><p>${escapeHtml(json.trend_reading)}</p></article>`;
    }
  } else {
    body = `<p>${escapeHtml(data.texto || "")}</p>`;
  }
  const meta = `${escapeHtml(data.n_noticias)} ${i18n("brief.articles")} - ${escapeHtml(data.modelo)} - ${escapeHtml(formatDate(data.fecha_generacion))}`;
  brief.innerHTML = renderCurrentBriefShell(body, meta);
  bindCurrentBriefToggle();
}

function renderCurrentBriefShell(body, meta) {
  return `
    <button class="daily-brief-toggle current-brief-toggle" type="button" data-current-brief-toggle aria-expanded="true" aria-controls="today-brief-body">
      <span>
        <small>${i18n("date.today")}</small>
        <strong>${i18n("brief.executive")}</strong>
        ${meta ? `<small>${meta}</small>` : ""}
      </span>
      <span class="daily-brief-chevron" aria-hidden="true"></span>
    </button>
    <div id="today-brief-body" class="daily-brief-body current-brief-body">${body}</div>
  `;
}

function bindCurrentBriefToggle() {
  const button = brief.querySelector("[data-current-brief-toggle]");
  if (button) {
    button.addEventListener("click", () => toggleDailyBrief(button));
  }
}

function renderBriefBody(data) {
  const json = data.brief_json;
  if (json && Array.isArray(json.items)) {
    let body = json.intro ? `<p>${escapeHtml(json.intro)}</p>` : "";
    body += json.items
      .map((item, index) => `
        <article class="brief-item">
          <h4>${index + 1}. ${escapeHtml(item.title || i18n("article.untitled"))}</h4>
          <p>${escapeHtml(item.summary || "")}</p>
          ${item.why_it_matters ? `<p><strong>${i18n("brief.why")}</strong> ${escapeHtml(item.why_it_matters)}</p>` : ""}
        </article>
      `)
      .join("");
    if (json.trend_reading) {
      body += `<article class="brief-item"><h4>${i18n("brief.trend")}</h4><p>${escapeHtml(json.trend_reading)}</p></article>`;
    }
    return body;
  }
  return `<p>${escapeHtml(data.texto || "")}</p>`;
}

function renderDailyBriefs(items) {
  if (!items.length) {
    dailyBriefsList.innerHTML = `
      <div class="empty panel archive-empty">
        <strong>${i18n("brief.noPreviousTitle")}</strong>
        <span>${i18n("brief.noPreviousBody")}</span>
      </div>
    `;
    return;
  }
  dailyBriefsList.innerHTML = items
    .map((item, index) => {
      const detailId = `daily-brief-${index}`;
      const expanded = index === 0;
      return `
      <article class="daily-brief-card">
        <button class="daily-brief-toggle" type="button" data-daily-brief-toggle aria-expanded="${expanded}" aria-controls="${detailId}">
          <span>
            <strong>${escapeHtml(item.fecha)}</strong>
            <small>${escapeHtml(item.n_noticias)} ${i18n("brief.articles")} - ${escapeHtml(item.modelo)} - ${escapeHtml(formatDate(item.fecha_generacion))}</small>
          </span>
          <span class="daily-brief-chevron" aria-hidden="true"></span>
        </button>
        <div id="${detailId}" class="daily-brief-body" ${expanded ? "" : "hidden"}>${renderBriefBody(item)}</div>
      </article>
    `;
    })
    .join("");
  dailyBriefsList.querySelectorAll("[data-daily-brief-toggle]").forEach((button) => {
    button.addEventListener("click", () => toggleDailyBrief(button));
  });
}

function toggleDailyBrief(button) {
  const detail = document.getElementById(button.getAttribute("aria-controls"));
  if (!detail) return;
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  detail.hidden = expanded;
}

function renderFavorites(data) {
  const count = data.count || 0;
  if (!count) {
    favoritesFeed.innerHTML = `
      <div class="empty panel archive-empty">
        <strong>${i18n("favorites.emptyTitle")}</strong>
        <span>${i18n("favorites.emptyBody")}</span>
      </div>
    `;
    return;
  }
  favoritesFeed.innerHTML = data.items.map(renderArticle).join("");
  bindArticleActions(favoritesFeed);
}

function renderHotTopics(items) {
  if (!items.length) {
    hotTopics.innerHTML = `<div class="empty">${i18n("topics.empty")}</div>`;
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
  const sourceLabel = Number(topic.source_count) === 1 ? i18n("topics.sourceSingular") : i18n("topics.sourcePlural");
  const sources = (topic.sources || [])
    .map((source) => `<span class="topic-source-chip">${escapeHtml(source)}</span>`)
    .join("");
  const supportingItems = (topic.supporting_items || [])
    .map((item) => `
      <a class="topic-support-item" href="${escapeHtml(item.url || "#")}" target="_blank" rel="noopener">
        <span>${escapeHtml(item.source || i18n("source.fallback"))}</span>
        <strong>${escapeHtml(item.title || i18n("article.untitled"))}</strong>
        <em>${escapeHtml(Math.round(Number(item.score || 0)))} ${i18n("filters.score").toLowerCase()}</em>
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
          <span>${escapeHtml(topic.topic)} - ${escapeHtml(topic.items)} ${i18n("topics.items")}</span>
        </div>
        <span class="topic-source-count">${escapeHtml(topic.source_count)} ${sourceLabel}</span>
      </button>
      <div id="${detailId}" class="topic-detail" hidden>
        <div class="topic-detail-stat">
          <span>${i18n("topics.theme")}</span>
          <strong>${escapeHtml(topic.topic)}</strong>
        </div>
        <div class="topic-detail-stat">
          <span>${i18n("topics.related")}</span>
          <strong>${escapeHtml(topic.items)}</strong>
        </div>
        <div class="topic-detail-stat">
          <span>${i18n("topics.sources")}</span>
          <strong>${escapeHtml(topic.source_count)}</strong>
        </div>
        <div class="topic-sources" aria-label="${i18n("topics.supporting")}">${sources}</div>
        <div class="topic-support-list">
          <span>${i18n("topics.supporting")}</span>
          ${supportingItems || `<p>${i18n("topics.noSupporting")}</p>`}
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
  feedTitle.textContent = state.query ? i18n("search.results") : i18n("feed.trends");
  feedMeta.textContent = `${count} ${i18n("feed.publications")} - ${data.orden === "Mas reciente" ? i18n("filters.recent") : i18n("filters.score")}`;
  if (!count) {
    feed.innerHTML = `<div class="empty panel">${i18n("feed.empty")}</div>`;
    return;
  }
  feed.innerHTML = data.items.map(renderArticle).join("");
  bindArticleActions(feed);
}

function bindArticleActions(root) {
  root.querySelectorAll("[data-summary]").forEach((button) => {
    button.addEventListener("click", () => generateSummary(button.dataset.summary, button));
  });
  root.querySelectorAll("[data-favorite]").forEach((button) => {
    button.addEventListener("click", () => toggleFavorite(button.dataset.favorite, button));
  });
  root.querySelectorAll("[data-media-image]").forEach((button) => {
    button.addEventListener("click", () => openMediaModal(button.dataset.mediaImage, button.dataset.mediaTitle || ""));
  });
}

function renderMediaPreview(item) {
  if (!item.media_url) return "";
  const title = item.label || item.titulo || i18n("article.media");
  const mediaUrl = escapeHtml(item.media_url);
  const sourceUrl = escapeHtml(item.media_source_url || item.url || "");
  const safeTitle = escapeHtml(title);
  const image = `<img src="${mediaUrl}" alt="${safeTitle}" loading="lazy" onerror="this.closest('.article-media')?.remove()">`;
  if (item.media_type === "video") {
    return `
      <a class="article-media article-media-video" href="${sourceUrl}" target="_blank" rel="noreferrer" aria-label="${i18n("article.openVideo")}">
        ${image}
        <span class="media-play" aria-hidden="true"></span>
      </a>
    `;
  }
  return `
    <button class="article-media article-media-image" type="button" data-media-image="${mediaUrl}" data-media-title="${safeTitle}" aria-label="${i18n("article.openImage")}">
      ${image}
    </button>
  `;
}

function renderArticle(item) {
  const titleParts = splitStarTitle(item.label || item.titulo);
  const isRepository = item.fuente === "GitHub Trending";
  const summary = isRepository ? item.descripcion : (hasSummary(item) ? item.resumen_ia : item.descripcion);
  const time = formatDate(item.fuente === "GitHub Trending" ? item.fecha_ingesta : item.fecha_publicacion);
  const tags = (item.tags || []).slice(0, 4).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
  const metric = item.fuente === "GitHub Trending"
    ? `${Number(item.metric || 0).toLocaleString(locale())} ${i18n("article.starsToday")}`
    : item.fuente === "Hacker News"
      ? `${Number(item.metric || item.comments || 0).toLocaleString(locale())} ${i18n("article.points")}`
      : "";
  const discussion = item.discussion_url
    ? `<a href="${escapeHtml(item.discussion_url)}" target="_blank" rel="noreferrer">${escapeHtml(item.comments)} ${i18n("article.comments")}</a>`
    : "";
  const sourcePreferenceBadge = item.source_preference === "prioritized"
    ? `<span class="badge source-preference-badge">${i18n("sources.badgePrioritized")}</span>`
    : "";
  const summaryAction = hasSummary(item) || isRepository
    ? ""
    : `
      <button type="button" class="summary-button" data-summary="${escapeHtml(item.id)}">
        <span class="summary-button-label">${i18n("article.generate")}</span>
        <span class="summary-spinner" aria-hidden="true"></span>
      </button>
    `;
  const favoriteLabel = item.is_favorite ? i18n("article.removeFavorite") : i18n("article.addFavorite");
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
  const starMetric = titleParts.stars ? `<div class="article-star-metric">${renderStarCount(titleParts.stars)}</div>` : "";
  const mediaPreview = renderMediaPreview(item);
  const visualRail = starMetric || mediaPreview
    ? `<aside class="article-visual" aria-label="${i18n("article.media")}">${starMetric}${mediaPreview}</aside>`
    : "";

  return `
    <article class="article${visualRail ? " has-visual" : ""}${item.media_url ? " has-media" : ""}" id="article-${escapeHtml(item.id)}">
      <div class="article-top">
        <div class="article-meta-stack">
          <div class="article-meta">${escapeHtml(item.fuente)}${time ? ` - ${escapeHtml(time)}` : ""}</div>
          <div class="badge-row"><span class="badge">${escapeHtml(item.area_label)}</span>${sourcePreferenceBadge}</div>
        </div>
        <div class="article-controls">
          <div class="score">${Number(item.selected_score || 0).toFixed(0)}</div>
          ${favoriteButton}
        </div>
      </div>
      <div class="article-main">
        <div class="article-content">
          <h4 class="article-heading">${escapeHtml(titleParts.title)}</h4>
          ${summary ? `<p class="article-summary">${escapeHtml(summary)}</p>` : ""}
          ${tags ? `<div class="tag-row">${tags}</div>` : ""}
          ${item.selection_reason ? `<p class="article-reason">${escapeHtml(item.selection_reason)}</p>` : ""}
        </div>
        ${visualRail}
      </div>
      <div class="article-foot">
        <span>${escapeHtml(metric || (item.ranking ? `${i18n("article.ranking")} #${item.ranking}` : i18n("article.trending")))}</span>
        <div class="article-actions">
          ${discussion}
          ${summaryAction}
          ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${i18n("article.readOriginal")}</a>` : ""}
        </div>
      </div>
    </article>
  `;
}

async function generateSummary(articleId, button) {
  if (button) {
    button.disabled = true;
    button.classList.add("is-generating");
    button.setAttribute("aria-busy", "true");
  }
  setStatus(i18n("status.generatingSummary"));
  try {
    const result = await fetchJson(withLanguage(`/api/articles/${encodeURIComponent(articleId)}/summary`), { method: "POST" });
    setStatus(result.cached ? i18n("status.summaryCached") : i18n("status.summaryGenerated"));
    if (result.summary) {
      applyGeneratedSummary(articleId, result.summary, button);
    }
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    if (button && button.isConnected) {
      button.disabled = false;
      button.classList.remove("is-generating");
      button.removeAttribute("aria-busy");
    }
  }
}

function applyGeneratedSummary(articleId, summary, button) {
  const article = document.getElementById(`article-${articleId}`);
  if (!article) return;
  const existingSummary = article.querySelector(".article-summary");
  const cleanSummary = String(summary || "");
  if (existingSummary) {
    existingSummary.textContent = cleanSummary;
  } else {
    const heading = article.querySelector(".article-heading");
    if (heading) {
      heading.insertAdjacentHTML("afterend", `<p class="article-summary">${escapeHtml(cleanSummary)}</p>`);
    }
  }
  button?.remove();
}

async function toggleFavorite(articleId, button) {
  const wasFavorite = button.getAttribute("aria-pressed") === "true";
  button.disabled = true;
  try {
    const result = await fetchJson(withLanguage(`/api/articles/${encodeURIComponent(articleId)}/favorite`), {
      method: wasFavorite ? "DELETE" : "POST",
    });
    if (state.view === "favorites" && !result.is_favorite) {
      await loadFavorites();
      return;
    }
    updateFavoriteButtons(articleId, Boolean(result.is_favorite));
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
    button.setAttribute("title", isFavorite ? i18n("article.removeFavorite") : i18n("article.addFavorite"));
    button.setAttribute("aria-label", isFavorite ? i18n("article.removeFavorite") : i18n("article.addFavorite"));
  });
}

function openMediaModal(src, title) {
  if (!mediaModal || !mediaModalImage || !src) return;
  mediaModalImage.src = src;
  mediaModalImage.alt = title || i18n("article.preview");
  mediaModal.hidden = false;
  mediaModalClose?.focus();
}

function closeMediaModal() {
  if (!mediaModal || !mediaModalImage) return;
  mediaModal.hidden = true;
  mediaModalImage.removeAttribute("src");
  mediaModalImage.alt = "";
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
          <small>${escapeHtml(item.source)} - ${i18n("filters.score").toLowerCase()} ${escapeHtml(item.score)}</small>
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
  const allOptions = Array.from(root.querySelectorAll('input[name="fuentes"], input[name="areas"]'));
  const options = visibleMultiSelectOptions(root);
  const selected = options.filter((input) => input.checked);
  const isSources = allOptions[0]?.name === "fuentes";
  const type = isSources ? i18n("filters.sources") : i18n("filters.areas");
  if (!label) return;
  if (!options.length) {
    label.textContent = `0 ${type}`;
  } else if (selected.length === options.length) {
    label.textContent = isSources ? i18n("filters.allSources") : i18n("filters.allAreas");
  } else if (selected.length === 1) {
    label.textContent = selected[0].nextElementSibling?.textContent || `1 ${type}`;
  } else {
    label.textContent = `${selected.length} ${type}`;
  }
}

function updateMultiSelectLabels() {
  document.querySelectorAll("[data-multiselect]").forEach(updateMultiSelectLabel);
}

function syncSelectAll(root) {
  const selectAll = root.querySelector("[data-select-all]");
  const options = visibleMultiSelectOptions(root);
  if (!selectAll) return;
  if (!options.length) {
    selectAll.checked = false;
    selectAll.indeterminate = false;
    updateMultiSelectLabel(root);
    return;
  }
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
      visibleMultiSelectOptions(root).forEach((input) => {
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
  syncDateMode();
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
    } else if (target === "sources") {
      setViewMode("sources");
      setStatus("");
    } else if (target === "more") {
      setViewMode("more");
    } else {
      setViewMode("today");
      loadAll();
    }
  });
});
search.addEventListener("input", () => {
  if (state.view !== "today") return;
  const draftQuery = search.value.trim();
  window.clearTimeout(search._timer);
  if (!draftQuery && state.query) {
    state.query = "";
    suggestions.hidden = true;
    suggestions.innerHTML = "";
    loadAll();
    return;
  }
  search._timer = window.setTimeout(() => {
    loadSuggestions();
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
mediaModalClose?.addEventListener("click", closeMediaModal);
mediaModal?.addEventListener("click", (event) => {
  if (event.target === mediaModal) closeMediaModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && mediaModal && !mediaModal.hidden) {
    closeMediaModal();
  }
  if (event.key === "Escape" && document.body.classList.contains("mobile-drawer-open")) {
    closeMobileDrawer();
  }
});

initTheme();
initSidebar();
initMobileShell();
initMultiSelects();
initSourcePreferences();
initLanguage();
syncDateMode();
loadAll();
window.setInterval(loadAll, 300000);
