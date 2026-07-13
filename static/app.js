const state = {
  query: "",
  page: 1,
  pageSize: 24,
  loading: false,
  pendingLoad: false,
  view: "today",
  language: "es",
  sourcePreferences: {},
  appliedSourcePreferences: {},
  session: null,
  user: null,
};
const summaryRequests = new Map();
let dailyBriefRequestId = 0;
let feedRequestId = 0;
let feedAbortController = null;
let suggestionRequestId = 0;
let suggestionAbortController = null;
let authDialogReturnFocus = null;

const I18N = {
  es: {
    "brand.tagline": "Analizador de tendencias IT",
    "sidebar.collapse": "Contraer barra lateral",
    "sidebar.expand": "Expandir barra lateral",
    "nav.main": "Navegación principal",
    "nav.today": "Actualizaciones de hoy",
    "nav.briefs": "Briefs diarios",
    "nav.favorites": "Favoritos",
    "nav.sources": "Fuentes",
    "nav.more": "Más",
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
    "account.title": "Cuenta",
    "account.login": "Iniciar sesi\u00f3n",
    "account.google": "Continuar con Google",
    "account.github": "Continuar con GitHub",
    "account.logout": "Cerrar sesi\u00f3n",
    "account.logoutConfirmTitle": "Cerrar sesi\u00f3n",
    "account.logoutConfirmMessage": "Pod\u00e9s volver a iniciar sesi\u00f3n cuando quieras.",
    "account.logoutConfirmAction": "Cerrar sesi\u00f3n",
    "account.loading": "Redirigiendo...",
    "account.required": "Inici\u00e1 sesi\u00f3n para usar esta funci\u00f3n.",
    "account.unavailable": "El inicio de sesi\u00f3n no est\u00e1 configurado.",
    "account.error": "No se pudo iniciar sesi\u00f3n.",
    "account.noSession": "Google volvi\u00f3 sin una sesi\u00f3n activa. Volv\u00e9 a iniciar sesi\u00f3n.",
    "account.externalCodeError": "Google no pudo completar el inicio de sesi\u00f3n. Revis\u00e1 el redirect URI, client ID y client secret en Supabase.",
    "account.promptTitle": "Inici\u00e1 sesi\u00f3n para continuar",
    "account.promptAction": "Iniciar sesi\u00f3n",
    "account.cancel": "Cancelar",
    "theme.toLight": "Cambiar a modo claro",
    "theme.toDark": "Cambiar a modo oscuro",
    "theme.light": "Claro",
    "theme.dark": "Oscuro",
    "mobile.openFilters": "Abrir filtros y ajustes",
    "mobile.closeFilters": "Cerrar filtros y ajustes",
    "mobile.navigation": "Navegación móvil",
    "mobile.updates": "Actualizaciones",
    "mobile.briefs": "Briefs",
    "mobile.saved": "Favoritos",
    "mobile.more": "Más",
    "mobile.previousDays": "Días anteriores",
    "search.placeholder": "Buscar",
    "search.clear": "Limpiar búsqueda",
    "search.results": "Resultados de búsqueda",
    "status.loadingSearch": "Cargando resultados de búsqueda...",
    "status.loadingSources": "Cargando preferencias de fuentes...",
    "status.sourcesApplied": "Preferencias aplicadas a los filtros.",
    "status.sourcesReset": "Preferencias de fuentes restablecidas.",
    "error.requestFailed": "La solicitud falló.",
    "date.today": "Hoy",
    "date.all": "Todas las fechas",
    "brief.executive": "Resumen ejecutivo",
    "brief.daily": "Brief diario",
    "brief.schedule": "El brief diario se genera todos los días a las 8:00.",
    "brief.loading": "Cargando brief...",
    "brief.history": "Historial",
    "brief.previous": "Briefs diarios anteriores",
    "brief.generating": "El brief de hoy se está generando. Actualizá esta sección en un momento.",
    "brief.missing": "Todavía no hay brief diario disponible para esta fecha.",
    "brief.noPreviousTitle": "No se encontraron briefs diarios anteriores",
    "brief.noPreviousBody": "Newser solo muestra aquí briefs guardados de los últimos 30 días. Los días faltantes se omiten.",
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
    "pagination.feed": "Paginación de publicaciones",
    "pagination.previous": "Anterior",
    "pagination.next": "Siguiente",
    "pagination.page": "Página",
    "pagination.jump": "Ir",
    "pagination.jumpLabel": "Ir a página",
    "pagination.of": "de",
    "pagination.ellipsis": "Más páginas",
    "article.untitled": "Sin título",
    "article.media": "Media del artículo",
    "article.openImage": "Abrir vista previa de imagen",
    "article.openVideo": "Abrir fuente del video",
    "article.preview": "Vista previa de imagen del artículo",
    "article.generate": "Generar resumen",
    "article.generating": "Generando...",
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
    "common.close": "Cerrar",
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
    "nav.today": "Today's Updates",
    "nav.briefs": "Daily Briefs",
    "nav.favorites": "Favorites",
    "nav.sources": "Sources",
    "nav.more": "More",
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
    "account.title": "Account",
    "account.login": "Log in",
    "account.google": "Continue with Google",
    "account.github": "Continue with GitHub",
    "account.logout": "Log out",
    "account.logoutConfirmTitle": "Log out",
    "account.logoutConfirmMessage": "You can sign back in whenever you need.",
    "account.logoutConfirmAction": "Log out",
    "account.loading": "Redirecting...",
    "account.required": "Log in to use this feature.",
    "account.unavailable": "Login is not configured.",
    "account.error": "Login could not be completed.",
    "account.noSession": "Google returned without an active session. Please sign in again.",
    "account.externalCodeError": "Google sign-in could not be completed. Check the redirect URI, client ID, and client secret in Supabase.",
    "account.promptTitle": "Sign in to continue",
    "account.promptAction": "Sign in",
    "account.cancel": "Cancel",
    "theme.toLight": "Switch to light mode",
    "theme.toDark": "Switch to dark mode",
    "theme.light": "Light",
    "theme.dark": "Dark",
    "mobile.openFilters": "Open filters and settings",
    "mobile.closeFilters": "Close filters and settings",
    "mobile.navigation": "Mobile navigation",
    "mobile.updates": "Updates",
    "mobile.briefs": "Briefs",
    "mobile.saved": "Saved",
    "mobile.more": "More",
    "mobile.previousDays": "Previous Days",
    "search.placeholder": "Search",
    "search.clear": "Clear search",
    "search.results": "Search results",
    "status.loadingSearch": "Loading search results...",
    "status.loadingSources": "Loading source preferences...",
    "status.sourcesApplied": "Source preferences applied to filters.",
    "status.sourcesReset": "Source preferences reset.",
    "error.requestFailed": "Request failed.",
    "date.today": "Today",
    "date.all": "All dates",
    "brief.executive": "Executive summary",
    "brief.daily": "Daily brief",
    "brief.schedule": "The daily brief is generated every day at 8:00.",
    "brief.loading": "Loading brief...",
    "brief.history": "History",
    "brief.previous": "Previous daily briefs",
    "brief.generating": "Today's brief is being generated. Refresh this section in a moment.",
    "brief.missing": "No daily brief is available for this date yet.",
    "brief.noPreviousTitle": "No previous daily briefs found",
    "brief.noPreviousBody": "Newser only shows stored briefs from the previous 30 days here. Missing days are omitted.",
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
    "pagination.feed": "Publication pagination",
    "pagination.previous": "Previous",
    "pagination.next": "Next",
    "pagination.page": "Page",
    "pagination.jump": "Go",
    "pagination.jumpLabel": "Go to page",
    "pagination.of": "of",
    "pagination.ellipsis": "More pages",
    "article.untitled": "Untitled",
    "article.media": "Article media",
    "article.openImage": "Open image preview",
    "article.openVideo": "Open video source",
    "article.preview": "Article image preview",
    "article.generate": "Generate summary",
    "article.generating": "Generating...",
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
    "common.close": "Close",
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
const mobileMore = document.querySelector("#mobile-more");
const navButtons = document.querySelectorAll("[data-view-target]");
const feed = document.querySelector("#feed");
const feedPagination = document.querySelector("#feed-pagination");
const feedTitle = document.querySelector("#feed-title");
const feedMeta = document.querySelector("#feed-meta");
const topbarTitle = document.querySelector(".topbar h2");
const topbarTitleMain = document.querySelector("#topbar-title-main");
const topbarDate = document.querySelector("#topbar-date");
const dateInput = filters.querySelector('input[name="fecha"]');
const allDatesToggle = document.querySelector("[data-all-dates]");
const stats = document.querySelector("#stats");
const brief = document.querySelector("#brief");
const hotTopics = document.querySelector("#hot-topics");
const statusLine = document.querySelector("#status");
const search = document.querySelector("#search");
const suggestions = document.querySelector("#suggestions");
const clearSearch = document.querySelector("#clear-search");
const overviewSections = document.querySelectorAll(".overview-only");
const dailyBriefs = document.querySelector("#daily-briefs");
const briefMobileHistory = document.querySelector("#brief-mobile-history");
const dailyBriefsList = document.querySelector("#daily-briefs-list");
const dailyBriefArchiveCount = document.querySelector("#brief-archive-count");
const favorites = document.querySelector("#favorites");
const favoritesFeed = document.querySelector("#favorites-feed");
const sourcePreferencesPanel = document.querySelector("#source-preferences");
const sourcePreferenceButtons = document.querySelectorAll("[data-source-preference]");
const sourceActionButtons = document.querySelectorAll("[data-source-action]");
const mediaModal = document.querySelector("#media-modal");
const mediaModalImage = document.querySelector("#media-modal-image");
const mediaModalClose = document.querySelector("#media-modal-close");
const authRequiredDialog = document.querySelector("#auth-required-dialog");
const authRequiredClose = document.querySelector("#auth-required-close");
const authRequiredMessage = document.querySelector("#auth-required-message");
const logoutConfirmDialog = document.querySelector("#logout-confirm-dialog");
const logoutConfirmClose = document.querySelector("#logout-confirm-close");
const logoutConfirmAction = document.querySelector("#logout-confirm-action");
const logoutConfirmCancel = document.querySelector("#logout-confirm-cancel");
const accountPanels = document.querySelectorAll("[data-account-panel]");
const accountToggles = document.querySelectorAll("[data-account-toggle]");
const authProviderButtons = document.querySelectorAll("[data-auth-provider]");
const authLogoutButtons = document.querySelectorAll("[data-auth-logout]");
const authConfig = window.NEWSER_AUTH_CONFIG || {};
const authStorageKey = (() => {
  try {
    return `newser-auth-${new URL(authConfig.url || "").hostname.split(".")[0]}`;
  } catch (_error) {
    return "newser-auth";
  }
})();

function availableWebStorage(name) {
  try {
    const storage = window[name];
    if (!storage) return null;
    const key = `${authStorageKey}-test`;
    storage.setItem(key, "1");
    storage.removeItem(key);
    return storage;
  } catch (_error) {
    return null;
  }
}

function cookieMap() {
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .reduce((items, part) => {
      const separator = part.indexOf("=");
      if (separator < 0) return items;
      items[decodeURIComponent(part.slice(0, separator))] = decodeURIComponent(part.slice(separator + 1));
      return items;
    }, {});
}

function setCookie(name, value, maxAgeSeconds) {
  document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSeconds}; SameSite=Lax`;
}

function cookieStorage() {
  const chunkSize = 3000;
  return {
    getItem(key) {
      const cookies = cookieMap();
      const chunkCountKey = `${key}-chunks`;
      const chunks = Number(cookies[chunkCountKey] || "0");
      if (!chunks) return cookies[key] || null;
      let value = "";
      for (let index = 0; index < chunks; index += 1) {
        value += cookies[`${key}-${index}`] || "";
      }
      return value || null;
    },
    setItem(key, value) {
      this.removeItem(key);
      const chunkCountKey = `${key}-chunks`;
      const text = String(value || "");
      const chunks = Math.max(1, Math.ceil(text.length / chunkSize));
      setCookie(chunkCountKey, String(chunks), 60 * 60 * 24 * 30);
      for (let index = 0; index < chunks; index += 1) {
        setCookie(`${key}-${index}`, text.slice(index * chunkSize, (index + 1) * chunkSize), 60 * 60 * 24 * 30);
      }
    },
    removeItem(key) {
      const cookies = cookieMap();
      const chunkCountKey = `${key}-chunks`;
      const chunks = Math.max(Number(cookies[chunkCountKey] || "0"), 1);
      for (let index = 0; index < chunks; index += 1) {
        setCookie(`${key}-${index}`, "", 0);
      }
      setCookie(key, "", 0);
      setCookie(chunkCountKey, "", 0);
    },
  };
}

function authStorage() {
  const storage = availableWebStorage("localStorage") || availableWebStorage("sessionStorage");
  if (storage) return storage;
  return cookieStorage();
}

const authClient = authConfig.url && authConfig.publishableKey && window.supabase
  ? window.supabase.createClient(authConfig.url, authConfig.publishableKey, {
      auth: {
        autoRefreshToken: true,
        detectSessionInUrl: false,
        flowType: "pkce",
        persistSession: true,
        storage: authStorage(),
        storageKey: authStorageKey,
      },
    })
  : null;
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

function parseFilterDate(value) {
  const parts = String(value || "").split("-").map((part) => Number.parseInt(part, 10));
  if (parts.length !== 3 || parts.some(Number.isNaN)) return null;
  return new Date(parts[0], parts[1] - 1, parts[2]);
}

function formatMobileHistoryDate(value) {
  const date = parseFilterDate(value);
  if (!date) return "";
  return date.toLocaleDateString(locale(), { month: "numeric", day: "2-digit" });
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
  syncMobileMenuToggleState();
  renderAccount();
}

function setLanguage(language, persist = true) {
  const nextLanguage = language === "en" ? "en" : "es";
  if (state.language === nextLanguage) return;
  state.language = nextLanguage;
  resetFeedPage();
  applyTranslations();
  if (persist) savePreferences();
  loadAll();
}

function setStatus(message, isError = false) {
  statusLine.textContent = message || "";
  statusLine.classList.toggle("error", isError);
}

function setAuthRequiredMessage(message, isError = false) {
  if (!authRequiredMessage) return;
  authRequiredMessage.textContent = message || "";
  authRequiredMessage.hidden = !message;
  authRequiredMessage.classList.toggle("error", isError);
}

function accountDisplayName() {
  return state.user?.name || state.user?.email || i18n("account.login");
}

function userFromSession(session) {
  const user = session?.user;
  if (!user) return null;
  const metadata = user.user_metadata || {};
  const email = user.email || "";
  return {
    id: user.id,
    email,
    name: metadata.full_name || metadata.name || email,
  };
}

function renderAccount() {
  accountPanels.forEach((panel) => {
    const label = panel.querySelector("[data-account-label]");
    const providerButtons = panel.querySelectorAll("[data-auth-provider]");
    const logout = panel.querySelector("[data-auth-logout]");
    if (label) {
      label.removeAttribute("data-i18n");
      label.textContent = accountDisplayName();
      label.title = state.user ? accountDisplayName() : "";
    }
    providerButtons.forEach((button) => { button.hidden = Boolean(state.user); });
    if (logout) logout.hidden = !state.user;
    panel.classList.toggle("is-authenticated", Boolean(state.user));
  });
}

function setAccountExpanded(panel, expanded) {
  const toggle = panel?.querySelector("[data-account-toggle]");
  const actions = panel?.querySelector("[data-account-actions]");
  if (!toggle || !actions) return;
  toggle.setAttribute("aria-expanded", String(expanded));
  actions.hidden = !expanded;
  panel.classList.toggle("is-expanded", expanded);
  if (expanded) panel.scrollIntoView({ block: "nearest" });
}

function visibleAccountPanel() {
  if (isPhoneViewport()) return document.querySelector(".account-mobile-card");
  return document.querySelector(".sidebar .account-section");
}

function requireLogin() {
  if (state.user) return true;
  if (isPhoneViewport()) setViewMode("more");
  const panel = visibleAccountPanel();
  if (document.body.classList.contains("sidebar-collapsed") && !isPhoneViewport()) {
    setSidebarCollapsed(false);
  }
  setAccountExpanded(panel, true);
  setStatus(i18n("account.required"));
  panel?.querySelector("[data-auth-provider]")?.focus();
  return false;
}

async function ensureUser(trigger) {
  if (state.user) return true;
  showAuthRequiredDialog(trigger);
  const session = await currentSupabaseSession();
  if (session) {
    await hydrateAuthenticatedUser(session);
    return Boolean(state.user);
  }
  return false;
}

async function savePreferences() {
  if (!state.user) return;
  try {
    await fetchJson("/api/preferences", {
      method: "PUT",
      body: JSON.stringify({
        language: state.language,
        theme: document.documentElement.dataset.theme === "light" ? "light" : "dark",
        source_preferences: state.sourcePreferences,
      }),
    });
  } catch (error) {
    setStatus(error.message, true);
  }
}

function applyAuthenticatedPreferences(preferences) {
  const defaults = defaultSourcePreferences();
  Object.entries(preferences.source_preferences || {}).forEach(([source, value]) => {
    if (source in defaults && SOURCE_PREFERENCE_VALUES.has(value)) defaults[source] = value;
  });
  state.sourcePreferences = defaults;
  state.appliedSourcePreferences = { ...defaults };
  setTheme(preferences.theme === "light" ? "light" : "dark");
  setLanguage(preferences.language === "en" ? "en" : "es", false);
  renderSourcePreferenceControls();
  syncSourceFilterVisibility();
}

async function hydrateAuthenticatedUser(session) {
  state.session = session || null;
  if (!session) {
    state.user = null;
    state.language = "es";
    state.sourcePreferences = defaultSourcePreferences();
    state.appliedSourcePreferences = { ...state.sourcePreferences };
    setTheme("dark");
    applyTranslations();
    renderSourcePreferenceControls();
    syncSourceFilterVisibility();
    renderAccount();
    return;
  }
  state.user = userFromSession(session);
  renderAccount();
  closeAuthRequiredDialog(false);
  try {
    const [user, preferences] = await Promise.all([fetchJson("/api/me"), fetchJson("/api/preferences")]);
    state.user = user;
    applyAuthenticatedPreferences(preferences);
    renderAccount();
  } catch (error) {
    renderAccount();
    setStatus(error.message, true);
  }
}

async function beginOAuth(provider, button) {
  if (!authClient) {
    setStatus(i18n("account.unavailable"), true);
    button.focus();
    return;
  }
  setAuthRequiredMessage("");
  authProviderButtons.forEach((item) => { item.disabled = true; });
  const label = button.querySelector("[data-i18n]");
  const original = label?.textContent || button.textContent;
  if (label) {
    label.textContent = i18n("account.loading");
  } else {
    button.textContent = i18n("account.loading");
  }
  const { error } = await authClient.auth.signInWithOAuth({
    provider,
    options: { redirectTo: `${window.location.origin}${window.location.pathname}` },
  });
  if (error) {
    authProviderButtons.forEach((item) => { item.disabled = false; });
    if (label) {
      label.textContent = original;
    } else {
      button.textContent = original;
    }
    setStatus(authErrorMessage(error), true);
    button.focus();
  }
}

function cleanOAuthUrl() {
  const url = new URL(window.location.href);
  ["code", "error", "error_code", "error_description"].forEach((key) => {
    url.searchParams.delete(key);
  });
  url.hash = "";
  const next = `${url.pathname}${url.search}${url.hash}`;
  window.history.replaceState({}, "", next || window.location.pathname);
}

async function sessionFromOAuthRedirect() {
  if (!authClient) return null;
  const hashParams = new URLSearchParams(window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "");
  const accessToken = hashParams.get("access_token");
  const refreshToken = hashParams.get("refresh_token");
  if (accessToken && refreshToken) {
    const { data, error } = await authClient.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });
    if (error) throw error;
    cleanOAuthUrl();
    return data.session;
  }

  const code = new URLSearchParams(window.location.search).get("code");
  if (code) {
    const { data, error } = await authClient.auth.exchangeCodeForSession(code);
    if (error) throw error;
    cleanOAuthUrl();
    return data.session;
  }
  return null;
}

function hasOAuthReturnParams() {
  const searchParams = new URLSearchParams(window.location.search);
  const hashParams = new URLSearchParams(window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "");
  return Boolean(
    searchParams.get("code")
    || searchParams.get("error")
    || searchParams.get("error_description")
    || hashParams.get("access_token")
    || hashParams.get("error")
    || hashParams.get("error_description")
  );
}

function oauthReturnSnapshot() {
  const searchParams = new URLSearchParams(window.location.search);
  const hashParams = new URLSearchParams(window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "");
  let storedSession = false;
  try {
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index) || "";
      if (key.startsWith("sb-") && key.includes("auth-token")) {
        storedSession = true;
        break;
      }
    }
  } catch (_error) {
    storedSession = false;
  }
  return {
    code: Boolean(searchParams.get("code")),
    token: Boolean(hashParams.get("access_token")),
    storedSession,
  };
}

function authReturnDiagnostic(message) {
  const snapshot = oauthReturnSnapshot();
  const yes = state.language === "en" ? "yes" : "si";
  const no = "no";
  const labels = state.language === "en"
    ? ["code", "token", "stored session"]
    : ["codigo", "token", "sesion guardada"];
  const values = [snapshot.code, snapshot.token, snapshot.storedSession].map((value) => (value ? yes : no));
  return `${message} (${labels[0]}: ${values[0]}, ${labels[1]}: ${values[1]}, ${labels[2]}: ${values[2]})`;
}

function authErrorMessage(error) {
  const message = String(error?.message || error || "");
  if (message.toLowerCase().includes("unable to exchange external code")) {
    return i18n("account.externalCodeError");
  }
  return message || i18n("account.error");
}

async function currentSupabaseSession() {
  if (!authClient) return null;
  const { data } = await authClient.auth.getSession();
  return data.session || null;
}

async function waitForSupabaseSession(attempts = 10) {
  if (!authClient) return null;
  for (let index = 0; index < attempts; index += 1) {
    const session = await currentSupabaseSession();
    if (session) return session;
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }
  return null;
}

async function initAuth() {
  accountToggles.forEach((toggle) => toggle.addEventListener("click", () => {
    const panel = toggle.closest("[data-account-panel]");
    if (document.body.classList.contains("sidebar-collapsed") && !isPhoneViewport()) {
      setSidebarCollapsed(false);
    }
    setAccountExpanded(panel, toggle.getAttribute("aria-expanded") !== "true");
  }));
  authProviderButtons.forEach((button) => button.addEventListener("click", () => {
    beginOAuth(button.dataset.authProvider, button);
  }));
  authLogoutButtons.forEach((button) => button.addEventListener("click", () => {
    showLogoutConfirmDialog(button);
  }));

  const oauthError = new URLSearchParams(window.location.search).get("error_description");
  if (oauthError) {
    setStatus(oauthError || i18n("account.error"), true);
    window.history.replaceState({}, "", window.location.pathname);
  }
  if (!authClient) {
    renderAccount();
    return;
  }
  const hadOAuthReturn = hasOAuthReturnParams();
  try {
    const redirectSession = await sessionFromOAuthRedirect();
    const session = redirectSession || await waitForSupabaseSession(16);
    await hydrateAuthenticatedUser(session);
    if (hadOAuthReturn && !session) {
      const message = authReturnDiagnostic(i18n("account.noSession"));
      setStatus(message, true);
      showAuthRequiredDialog(null, message, true);
    }
  } catch (error) {
    const session = await waitForSupabaseSession(16);
    await hydrateAuthenticatedUser(session);
    if (!session) {
      const message = hadOAuthReturn
        ? authReturnDiagnostic(authErrorMessage(error))
        : authErrorMessage(error);
      setStatus(message, true);
      if (hadOAuthReturn) showAuthRequiredDialog(null, message, true);
    }
  }
  authClient.auth.onAuthStateChange((_event, session) => {
    window.setTimeout(async () => {
      await hydrateAuthenticatedUser(session);
      loadAll();
    }, 0);
  });
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
  return defaultSourcePreferences();
}

function saveSourcePreferences() {
  savePreferences();
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
    button.addEventListener("click", async () => {
      if (!await ensureUser(button)) return;
      const source = button.dataset.sourcePreference || "";
      const value = button.dataset.sourceValue || "normal";
      if (!source || !SOURCE_PREFERENCE_VALUES.has(value)) return;
      state.sourcePreferences[source] = value;
      renderSourcePreferenceControls();
    });
  });
  sourceActionButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      if (!await ensureUser(button)) return;
      if (button.dataset.sourceAction === "reset") {
        resetSourcePreferences();
        resetFeedPage();
        setStatus(i18n("status.sourcesReset"));
        loadAll();
        loadSuggestions();
      } else {
        applySourcePreferencesToFilters();
        resetFeedPage();
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
  params.set("page", String(state.page));
  params.set("page_size", String(state.pageSize));
  return params;
}

function resetFeedPage() {
  state.page = 1;
}

function setFeedPaginationLoading(loading) {
  if (!feedPagination || feedPagination.hidden) return;
  feedPagination.classList.toggle("is-loading", loading);
  feedPagination.querySelectorAll("button, input").forEach((control) => {
    control.disabled = loading;
  });
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
  const starIndex = text.indexOf("⭐");
  if (starIndex < 0) return { title: text, stars: "" };
  const stars = text.slice(starIndex + 1).match(/^\s*([\d,]+)/);
  if (!stars) return { title: text, stars: "" };
  return { title: text.slice(0, starIndex).trim(), stars: stars[1] };
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

function cleanSuggestionQuery(value) {
  return String(value ?? "")
    .replace(/^\[\w+\]\s*/, "")
    .replace(/\s*[⭐â­]\s*[\d,]+.*$/, "")
    .trim();
}

function renderTitleLabel(value) {
  const parts = splitStarTitle(value);
  const title = parts.title.replace(/^\[\w+\]\s*/, "").trim() || parts.title;
  return `${escapeHtml(title)}${parts.stars ? ` ${renderStarCount(parts.stars)}` : ""}`;
}

function formatScore(value) {
  const score = Number(value || 0);
  return Math.round(Number.isFinite(score) ? score : 0).toLocaleString(locale());
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
  const allDates = Boolean(allDatesToggle?.checked);
  const selectedDate = dateInput?.value || "";
  const latestDate = dateInput?.max || "";
  const showDate = state.view === "today" && (allDates || (selectedDate && latestDate && selectedDate !== latestDate));
  topbarDate.hidden = !showDate;
  topbarDate.textContent = allDates ? i18n("date.all") : (showDate ? formatFeedDate(selectedDate) : "");
}

function syncDateMode() {
  const allDates = Boolean(allDatesToggle?.checked);
  if (dateInput) dateInput.disabled = allDates;
  updateTopbarTitle();
}

function hasSummary(item) {
  const value = (item.resumen_ia || "").trim();
  return value && value !== "Resumen no disponible";
}

async function fetchJson(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.session?.access_token) headers.set("Authorization", `Bearer ${state.session.access_token}`);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(url, { ...options, headers });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.reason || data.detail || i18n("error.requestFailed"));
    error.status = response.status;
    throw error;
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
  if (state.loading) {
    state.pendingLoad = true;
    hideHotTopics();
    feedAbortController?.abort();
    return;
  }
  const requestId = ++feedRequestId;
  feedAbortController = new AbortController();
  const hasRenderedFeed = Boolean(feed.children.length);
  updateTopbarTitle();
  state.loading = true;
  document.body.classList.add("is-loading");
  setFeedPaginationLoading(true);
  const searchActive = Boolean(state.query);
  setSearchMode(searchActive);
  hideHotTopics();
  if (!hasRenderedFeed && searchActive) setStatus(i18n("status.loadingSearch"));
  renderFeedSkeleton();
  try {
    const params = formParams();
    const feedData = await fetchJson(`/api/feed?${params}`, { signal: feedAbortController.signal });
    if (requestId !== feedRequestId) return;
    if (!searchActive) {
      renderHotTopics(feedData.hot_topics || []);
    }
    renderFeed(feedData);
    setStatus("");
  } catch (error) {
    if (error.name !== "AbortError") {
      setStatus(error.message, true);
    }
  } finally {
    if (requestId === feedRequestId) {
      feedAbortController = null;
      state.loading = false;
      document.body.classList.remove("is-loading");
      setFeedPaginationLoading(false);
    }
    if (state.pendingLoad) {
      state.pendingLoad = false;
      loadAll();
    }
  }
}

async function loadDailyBriefs() {
  if (state.loading && state.view !== "briefs") return;
  const requestId = ++dailyBriefRequestId;
  const requestLanguage = state.language;
  state.loading = true;
  document.body.classList.add("is-loading");
  setViewMode("briefs");
  setStatus("");
  renderDailyBriefSkeleton();
  try {
    const [briefData, archiveData] = await Promise.all([
      fetchJson(withLanguage("/api/brief")),
      fetchJson(withLanguage("/api/daily-briefs")),
    ]);
    if (requestId !== dailyBriefRequestId || requestLanguage !== state.language || state.view !== "briefs") return;
    renderBrief(briefData);
    renderDailyBriefs(archiveData.items || [], briefData);
    setStatus("");
  } catch (error) {
    if (requestId !== dailyBriefRequestId || requestLanguage !== state.language || state.view !== "briefs") return;
    setStatus(error.message, true);
  } finally {
    if (requestId === dailyBriefRequestId) {
      state.loading = false;
      document.body.classList.remove("is-loading");
    }
  }
}

async function loadFavorites() {
  if (!await ensureUser()) {
    showFavoritesSignInPrompt();
    return;
  }
  if (state.loading) return;
  state.loading = true;
  document.body.classList.add("is-loading");
  setViewMode("favorites");
  setStatus("");
  renderFavoritesSkeleton();
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

function hideHotTopics() {
  const panel = document.querySelector("#topics-panel");
  if (panel) panel.hidden = true;
  hotTopics.innerHTML = "";
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
  sidebarToggle.setAttribute("aria-label", collapsed ? i18n("sidebar.expand") : i18n("sidebar.collapse"));
}

function setTheme(theme, persist = false) {
  const selectedTheme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = selectedTheme;
  const isLight = selectedTheme === "light";
  themeToggles.forEach((button) => {
    const themeValue = button.dataset.themeValue;
    if (themeValue) {
      const selected = themeValue === selectedTheme;
      button.setAttribute("aria-pressed", String(selected));
      button.setAttribute("aria-label", themeValue === "light" ? i18n("theme.light") : i18n("theme.dark"));
      button.setAttribute("title", themeValue === "light" ? i18n("theme.light") : i18n("theme.dark"));
      return;
    }
    button.setAttribute("aria-pressed", String(isLight));
    button.setAttribute("aria-label", isLight ? i18n("theme.toDark") : i18n("theme.toLight"));
    button.setAttribute("title", isLight ? i18n("theme.toDark") : i18n("theme.toLight"));
  });
  themeStateLabels.forEach((label) => {
    label.textContent = isLight ? i18n("theme.light") : i18n("theme.dark");
  });
  if (persist) savePreferences();
}

function initTheme() {
  setTheme("dark");
  themeToggles.forEach((button) => button.addEventListener("click", () => {
    const currentTheme = document.documentElement.dataset.theme === "light" ? "light" : "dark";
    const nextTheme = button.dataset.themeValue || (currentTheme === "light" ? "dark" : "light");
    setTheme(nextTheme, true);
  }));
}

function initLanguage() {
  applyTranslations();
  languageButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setLanguage(button.dataset.languageOption || "es");
    });
  });
}

function isPhoneViewport() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function syncMobileMenuToggleState() {
  const expanded = document.body.classList.contains("mobile-drawer-open");
  if (mobileMenuToggle) {
    mobileMenuToggle.setAttribute("aria-expanded", String(expanded));
    mobileMenuToggle.setAttribute("aria-label", i18n(expanded ? "mobile.closeFilters" : "mobile.openFilters"));
  }
  if (sidebarToggle && isPhoneViewport()) {
    sidebarToggle.setAttribute("aria-label", i18n(expanded ? "mobile.closeFilters" : "mobile.openFilters"));
  }
}

function openMobileDrawer() {
  if (!isPhoneViewport()) return;
  document.body.classList.add("mobile-drawer-open");
  if (mobileDrawerBackdrop) mobileDrawerBackdrop.hidden = false;
  syncMobileMenuToggleState();
}

function closeMobileDrawer() {
  document.body.classList.remove("mobile-drawer-open");
  if (mobileDrawerBackdrop) mobileDrawerBackdrop.hidden = true;
  syncMobileMenuToggleState();
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

function expandableLabel(expanded) {
  if (state.language === "en") return expanded ? "Show less" : "Show more";
  return expanded ? "Mostrar menos" : "Mostrar más";
}

function textPreview(content, maxLength = 220) {
  const text = String(content || "").replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return text;
  const boundary = text.lastIndexOf(" ", maxLength);
  const cut = boundary > maxLength * 0.65 ? boundary : maxLength;
  return `${text.slice(0, cut).trim()}...`;
}

function expandableText(content, className, label = "", preview = "") {
  const text = String(content || "");
  if (!text) return "";
  const shortText = String(preview || text);
  const labelAttr = label ? ` aria-label="${escapeHtml(label)}"` : "";
  return `
    <button type="button" class="${className} expandable-text" data-expandable-text data-expandable-available="false" aria-expanded="false"${labelAttr}>
      <span data-full-text="${escapeHtml(text)}" data-short-text="${escapeHtml(shortText)}">${escapeHtml(text)}</span>
      <small data-expandable-label>${expandableLabel(false)}</small>
    </button>
  `;
}

function briefText(content) {
  const text = String(content || "").trim();
  return text ? `<p class="brief-text">${escapeHtml(text)}</p>` : "";
}

function toggleExpandableText(button) {
  if (button.dataset.expandableAvailable === "false") return;
  const expanded = button.getAttribute("aria-expanded") === "true";
  const nextExpanded = !expanded;
  button.setAttribute("aria-expanded", String(nextExpanded));
  const text = button.querySelector("span");
  if (text) {
    text.textContent = text.dataset.fullText || text.textContent;
  }
  const label = button.querySelector("[data-expandable-label]");
  if (label) label.textContent = expandableLabel(nextExpanded);
}

function syncExpandableTextLabels(root = document) {
  root.querySelectorAll("[data-expandable-text]").forEach((button) => {
    const text = button.querySelector("span");
    if (!text) return;
    const hasOverflow = text.scrollHeight > text.clientHeight + 1;
    button.dataset.expandableAvailable = String(hasOverflow);
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

function renderArticleSkeleton() {
  return `
    <article class="article article-skeleton" aria-hidden="true">
      <div class="article-top">
        <div class="article-meta-stack skeleton-stack">
          <span class="shimmer-line shimmer-meta"></span>
          <span class="shimmer-pill shimmer-pill-small"></span>
        </div>
        <div class="article-controls">
          <span class="shimmer-line shimmer-score"></span>
          <span class="shimmer-dot"></span>
        </div>
      </div>
      <div class="article-main article-skeleton-main">
        <div class="article-content skeleton-stack">
          <span class="shimmer-line shimmer-title"></span>
          <span class="shimmer-line"></span>
          <span class="shimmer-line shimmer-copy"></span>
          <span class="shimmer-line shimmer-copy-short"></span>
          <div class="tag-row">
            <span class="shimmer-pill"></span>
            <span class="shimmer-pill shimmer-pill-small"></span>
          </div>
        </div>
        <div class="article-visual">
          <span class="shimmer-media"></span>
        </div>
      </div>
      <div class="article-foot">
        <span class="shimmer-line shimmer-foot"></span>
        <div class="article-actions">
          <span class="shimmer-button"></span>
          <span class="shimmer-button shimmer-button-wide"></span>
        </div>
      </div>
    </article>
  `;
}

function renderFeedSkeleton(target = feed, count = 3) {
  if (!target) return;
  target.innerHTML = Array.from({ length: count }, renderArticleSkeleton).join("");
}

function renderInitialFeedSkeleton() {
  if (state.view !== "today" || feed.children.length) return;
  document.body.classList.add("is-loading");
  hideHotTopics();
  renderFeedSkeleton();
}

function renderDailyBriefSkeleton() {
  if (dailyBriefArchiveCount) dailyBriefArchiveCount.textContent = "";
  if (briefMobileHistory) briefMobileHistory.innerHTML = "";
  setBriefMobileHistoryExpanded(false);
  brief.innerHTML = `
    <article class="daily-brief-card brief-loading-card" aria-hidden="true">
      <div class="brief-loading-head">
        <span class="skeleton-stack">
          <span class="brief-loading-line brief-loading-date"></span>
          <span class="brief-loading-line brief-loading-title"></span>
          <span class="brief-loading-line brief-loading-note"></span>
        </span>
        <span class="brief-loading-orb"></span>
      </div>
      <div class="brief-loading-body skeleton-stack">
        <span class="brief-loading-line"></span>
        <span class="brief-loading-line brief-loading-copy"></span>
        <span class="brief-loading-line brief-loading-copy-short"></span>
      </div>
    </article>
  `;
  dailyBriefsList.innerHTML = Array.from({ length: 7 }, () => `
    <div class="brief-archive-item brief-archive-skeleton" aria-hidden="true">
      <span class="brief-loading-dot"></span>
      <span class="skeleton-stack">
        <span class="brief-loading-line brief-loading-row-title"></span>
        <span class="brief-loading-line brief-loading-row-copy"></span>
      </span>
    </div>
  `).join("");
}

function renderFavoritesSkeleton() {
  renderFeedSkeleton(favoritesFeed, 3);
}

function renderBrief(data, context = {}) {
  if (data.available === false) {
    const missingMessage = data.catchup_started || data.catchup_running
      ? i18n("brief.generating")
      : i18n("brief.missing");
    brief.innerHTML = renderCurrentBriefShell(
      `<div class="empty">${escapeHtml(missingMessage)}</div>`,
      "",
      context,
    );
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
          ${briefText(item.summary)}
          ${item.why_it_matters ? `<p><strong>${i18n("brief.why")}</strong> ${escapeHtml(item.why_it_matters)}</p>` : ""}
        </article>
      `)
      .join("");
    if (json.trend_reading) {
      body += `<article class="brief-item"><h4>${i18n("brief.trend")}</h4>${briefText(json.trend_reading)}</article>`;
    }
  } else {
    body = `<p>${escapeHtml(data.texto || "")}</p>`;
  }
  const meta = `${escapeHtml(data.n_noticias)} ${i18n("brief.articles")}`;
  brief.innerHTML = renderCurrentBriefShell(body, meta, context);
}

function renderCurrentBriefShell(body, meta, context = {}) {
  const label = context.label || i18n("date.today");
  const title = context.title || i18n("brief.executive");
  const note = context.note === undefined ? i18n("brief.schedule") : context.note;
  const header = `
    <span>
      <small>${escapeHtml(label)}</small>
      <strong>${escapeHtml(title)}</strong>
      ${note ? `<small class="brief-schedule-note">${escapeHtml(note)}</small>` : ""}
      ${meta ? `<small>${meta}</small>` : ""}
    </span>
  `;
  return `
    <article class="daily-brief-card current-brief-card">
      <div class="daily-brief-toggle current-brief-toggle" data-current-brief-static>
        ${header}
      </div>
      <div id="today-brief-body" class="daily-brief-body current-brief-body">${body}</div>
    </article>
  `;
}

function renderBriefBody(data) {
  const json = data.brief_json;
  if (json && Array.isArray(json.items)) {
    let body = json.intro ? `<p>${escapeHtml(json.intro)}</p>` : "";
    body += json.items
      .map((item, index) => `
        <article class="brief-item">
          <h4>${index + 1}. ${escapeHtml(item.title || i18n("article.untitled"))}</h4>
          ${briefText(item.summary)}
          ${item.why_it_matters ? `<p><strong>${i18n("brief.why")}</strong> ${escapeHtml(item.why_it_matters)}</p>` : ""}
        </article>
      `)
      .join("");
    if (json.trend_reading) {
      body += `<article class="brief-item"><h4>${i18n("brief.trend")}</h4>${briefText(json.trend_reading)}</article>`;
    }
    return body;
  }
  return `<p>${escapeHtml(data.texto || "")}</p>`;
}

function briefArchiveTitle(item) {
  const json = item.brief_json;
  if (json && Array.isArray(json.items) && json.items.length) {
    return json.items[0].title || json.intro || item.fecha || i18n("brief.daily");
  }
  const text = String(item.texto || "").replace(/\s+/g, " ").trim();
  return text ? text.slice(0, 92) : item.fecha || i18n("brief.daily");
}

function formatArchiveDate(value) {
  if (!value) return "";
  const parts = String(value).split("-").map((part) => Number.parseInt(part, 10));
  if (parts.length !== 3 || parts.some(Number.isNaN)) return value;
  const date = new Date(parts[0], parts[1] - 1, parts[2]);
  return date.toLocaleDateString(locale(), { month: "short", day: "numeric" });
}

function archiveMonthKey(value) {
  const parts = String(value || "").split("-").map((part) => Number.parseInt(part, 10));
  if (parts.length !== 3 || parts.some(Number.isNaN)) return "";
  return `${parts[0]}-${String(parts[1]).padStart(2, "0")}`;
}

function formatArchiveMonth(value) {
  const parts = String(value || "").split("-").map((part) => Number.parseInt(part, 10));
  if (parts.length !== 3 || parts.some(Number.isNaN)) return value || "";
  const date = new Date(parts[0], parts[1] - 1, 1);
  return date.toLocaleDateString(locale(), { month: "long", year: "numeric" });
}

function currentArchiveMonthKey() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

function setBriefMobileHistoryExpanded(expanded) {
  dailyBriefs?.setAttribute("data-mobile-history-expanded", String(expanded));
  if (dailyBriefsList) dailyBriefsList.dataset.mobileExpanded = String(expanded);
  if (dailyBriefArchiveCount?.dataset.fullCount) {
    dailyBriefArchiveCount.textContent = expanded
      ? dailyBriefArchiveCount.dataset.previousDaysCount || "0"
      : dailyBriefArchiveCount.dataset.fullCount;
  }
  dailyBriefsList?.querySelectorAll("[data-brief-archive-month-count]").forEach((count) => {
    count.textContent = expanded
      ? count.dataset.previousDaysCount || "0"
      : count.dataset.fullCount || "0";
  });
}

function renderBriefMobileHistory(items, todayData = null) {
  if (!briefMobileHistory) return;
  const quickArchiveItems = items.slice(0, 2);
  briefMobileHistory.innerHTML = `
    ${todayData ? `
      <button class="mobile-history-chip" type="button" data-brief-mobile-today aria-pressed="true">
        ${escapeHtml(i18n("date.today"))}
      </button>
    ` : ""}
    ${quickArchiveItems.map((item, index) => `
      <button class="mobile-history-chip" type="button" data-brief-mobile-index="${index}" aria-pressed="false">
        ${escapeHtml(formatMobileHistoryDate(item.fecha))}
      </button>
    `).join("")}
    <button class="mobile-history-chip brief-archive-earlier" type="button" data-brief-mobile-previous-days aria-pressed="false">
      ${escapeHtml(i18n("mobile.previousDays"))}
    </button>
  `;
  setBriefMobileHistoryExpanded(false);
  briefMobileHistory.querySelector("[data-brief-mobile-today]")?.addEventListener("click", (event) => {
    briefMobileHistory.querySelectorAll(".mobile-history-chip").forEach((button) => {
      button.setAttribute("aria-pressed", String(button === event.currentTarget));
    });
    setBriefMobileHistoryExpanded(false);
    if (todayData) renderBrief(todayData);
  });
  briefMobileHistory.querySelectorAll("[data-brief-mobile-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number.parseInt(button.dataset.briefMobileIndex || "-1", 10);
      const item = items[index];
      if (!item) return;
      briefMobileHistory.querySelectorAll(".mobile-history-chip").forEach((other) => {
        other.setAttribute("aria-pressed", String(other === button));
      });
      setBriefMobileHistoryExpanded(false);
      renderBrief(
        { ...item, available: true },
        { label: formatArchiveDate(item.fecha), title: i18n("brief.daily"), note: "" },
      );
    });
  });
  briefMobileHistory.querySelector("[data-brief-mobile-previous-days]")?.addEventListener("click", (event) => {
    setBriefMobileHistoryExpanded(true);
    briefMobileHistory.querySelectorAll(".mobile-history-chip").forEach((button) => {
      button.setAttribute("aria-pressed", String(button === event.currentTarget));
    });
  });
}

function renderDailyBriefs(items, todayData = null) {
  if (dailyBriefArchiveCount) {
    dailyBriefArchiveCount.dataset.fullCount = String(items.length);
    dailyBriefArchiveCount.dataset.previousDaysCount = String(Math.max(items.length - 2, 0));
    dailyBriefArchiveCount.textContent = dailyBriefArchiveCount.dataset.fullCount;
  }
  renderBriefMobileHistory(items, todayData);
  const todayRow = todayData ? `
    <article class="brief-archive-item brief-archive-today">
      <button class="brief-archive-button" type="button" data-daily-brief-today aria-pressed="true">
        <span class="brief-archive-date">${escapeHtml(i18n("date.today"))}</span>
        <span class="brief-archive-copy">
          <strong>${escapeHtml(briefArchiveTitle(todayData))}</strong>
          <small>${todayData.available ? `${escapeHtml(todayData.n_noticias)} ${i18n("brief.articles")}` : escapeHtml(i18n("brief.missing"))}</small>
        </span>
      </button>
    </article>
  ` : "";
  if (!items.length) {
    dailyBriefsList.innerHTML = `
      ${todayRow}
      <div class="empty archive-empty">
        <strong>${i18n("brief.noPreviousTitle")}</strong>
        <span>${i18n("brief.noPreviousBody")}</span>
      </div>
    `;
    return;
  }
  const groups = [];
  items.forEach((item, index) => {
    const monthKey = archiveMonthKey(item.fecha);
    const lastGroup = groups[groups.length - 1];
    if (!lastGroup || lastGroup.monthKey !== monthKey) {
      groups.push({ monthKey, label: formatArchiveMonth(item.fecha), items: [] });
    }
    groups[groups.length - 1].items.push({ item, index });
  });
  const currentMonthKey = currentArchiveMonthKey();
  const fullArchive = groups
    .map((group, groupIndex) => {
      const expanded = group.monthKey === currentMonthKey;
      const panelId = `brief-archive-month-${groupIndex}`;
      const mobilePreviousCount = group.items.filter(({ index }) => index >= 2).length;
      const monthItems = group.items.map(({ item, index }) => {
      return `
      <article class="brief-archive-item${index < 2 ? " brief-archive-mobile-quick" : ""}">
        <button class="brief-archive-button" type="button" data-daily-brief-toggle data-brief-index="${index}" aria-pressed="false">
          <span class="brief-archive-date">${escapeHtml(formatArchiveDate(item.fecha))}</span>
          <span class="brief-archive-copy">
            <strong>${escapeHtml(briefArchiveTitle(item))}</strong>
            <small>${escapeHtml(item.n_noticias)} ${i18n("brief.articles")}</small>
          </span>
        </button>
      </article>
    `;
      }).join("");
      return `
      <section class="brief-archive-month" data-brief-archive-month data-mobile-previous-count="${mobilePreviousCount}">
        <button class="brief-archive-month-button" type="button" aria-expanded="${expanded}" aria-controls="${panelId}">
          <span class="brief-archive-month-arrow" aria-hidden="true"></span>
          <span>${escapeHtml(group.label)}</span>
          <span class="brief-archive-month-count" data-brief-archive-month-count data-full-count="${group.items.length}" data-previous-days-count="${mobilePreviousCount}">${group.items.length}</span>
        </button>
        <div id="${panelId}" class="brief-archive-month-items" ${expanded ? "" : "hidden"}>
          ${monthItems}
        </div>
      </section>
    `;
    })
    .join("");
  dailyBriefsList.dataset.mobileExpanded = "false";
  dailyBriefsList.innerHTML = `
    ${todayRow}
    <div class="brief-archive-full" data-brief-archive-full>
      ${fullArchive}
    </div>
  `;
  const todayButton = dailyBriefsList.querySelector("[data-daily-brief-today]");
  if (todayButton && todayData) {
    dailyBriefsList.querySelectorAll("[data-daily-brief-today]").forEach((button) => button.addEventListener("click", () => {
      dailyBriefsList.querySelectorAll("[data-daily-brief-toggle], [data-daily-brief-today]").forEach((other) => {
        other.setAttribute("aria-pressed", String(other === button));
      });
      setBriefMobileHistoryExpanded(false);
      renderBrief(todayData);
    }));
  }
  dailyBriefsList.querySelectorAll("[data-daily-brief-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number.parseInt(button.dataset.briefIndex || "-1", 10);
      const item = items[index];
      if (!item) return;
      dailyBriefsList.querySelectorAll("[data-daily-brief-toggle], [data-daily-brief-today]").forEach((other) => {
        other.setAttribute("aria-pressed", String(other === button));
      });
      setBriefMobileHistoryExpanded(false);
      renderBrief(
        { ...item, available: true },
        { label: formatArchiveDate(item.fecha), title: i18n("brief.daily"), note: "" },
      );
    });
  });
  dailyBriefsList.querySelectorAll(".brief-archive-month-button").forEach((button) => {
    button.addEventListener("click", () => {
      const panel = document.getElementById(button.getAttribute("aria-controls"));
      if (!panel) return;
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      panel.hidden = expanded;
    });
  });
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
  syncExpandableTextLabels(favoritesFeed);
}

function closeAuthRequiredDialog(restoreFocus = true) {
  if (!authRequiredDialog) return;
  if (typeof authRequiredDialog.close === "function" && authRequiredDialog.open) {
    authRequiredDialog.close();
  } else {
    authRequiredDialog.hidden = true;
  }
  if (restoreFocus) authDialogReturnFocus?.focus();
  authDialogReturnFocus = null;
}

function showAuthRequiredDialog(trigger, message = "", isError = false) {
  if (state.user) return true;
  authDialogReturnFocus = trigger instanceof HTMLElement ? trigger : document.activeElement;
  if (!authRequiredDialog) {
    requireLogin();
    return false;
  }
  setAuthRequiredMessage(message, isError);
  if (!message) setStatus("");
  if (typeof authRequiredDialog.showModal === "function") {
    if (!authRequiredDialog.open) authRequiredDialog.showModal();
  } else {
    authRequiredDialog.hidden = false;
  }
  authRequiredDialog.querySelector("[data-login-prompt]")?.focus();
  return false;
}

function showFavoritesSignInPrompt(trigger) {
  setViewMode("favorites");
  favoritesFeed.innerHTML = "";
  setStatus("");
  showAuthRequiredDialog(trigger);
}

function closeLogoutConfirmDialog() {
  if (!logoutConfirmDialog) return;
  if (typeof logoutConfirmDialog.close === "function" && logoutConfirmDialog.open) {
    logoutConfirmDialog.close();
  } else {
    logoutConfirmDialog.hidden = true;
  }
}

function showLogoutConfirmDialog(trigger) {
  authDialogReturnFocus = trigger instanceof HTMLElement ? trigger : document.activeElement;
  if (!logoutConfirmDialog) return;
  if (typeof logoutConfirmDialog.showModal === "function") {
    if (!logoutConfirmDialog.open) logoutConfirmDialog.showModal();
  } else {
    logoutConfirmDialog.hidden = false;
  }
  logoutConfirmAction?.focus();
}

async function confirmLogout() {
  closeLogoutConfirmDialog();
  if (authClient) await authClient.auth.signOut();
  await hydrateAuthenticatedUser(null);
  setViewMode("today");
  loadAll();
  authDialogReturnFocus?.focus();
  authDialogReturnFocus = null;
}

function renderHotTopics(items) {
  const panel = document.querySelector("#topics-panel");
  if (!items.length) {
    hideHotTopics();
    return;
  }
  if (panel) panel.hidden = false;
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
  const total = Number(data.total ?? count);
  const page = Number(data.page || 1);
  const pageSize = Number(data.page_size || state.pageSize);
  const start = total && count ? ((page - 1) * pageSize) + 1 : 0;
  const end = total && count ? start + count - 1 : 0;
  feedTitle.textContent = state.query ? i18n("search.results") : i18n("feed.trends");
  const amount = total && count ? `${start}-${end} ${i18n("pagination.of")} ${total}` : "0";
  feedMeta.textContent = `${amount} ${i18n("feed.publications")} - ${data.orden === "Mas reciente" ? i18n("filters.recent") : i18n("filters.score")}`;
  renderFeedPagination(data);
  if (!count) {
    feed.innerHTML = `<div class="empty panel">${i18n("feed.empty")}</div>`;
    return;
  }
  feed.innerHTML = data.items.map(renderArticle).join("");
  bindArticleActions(feed);
  syncExpandableTextLabels(feed);
}

function pageWindow(page, totalPages) {
  const pages = new Set([1, totalPages]);
  for (let index = page - 2; index <= page + 2; index += 1) {
    if (index >= 1 && index <= totalPages) pages.add(index);
  }
  const sorted = Array.from(pages).sort((a, b) => a - b);
  const result = [];
  sorted.forEach((value, index) => {
    const previous = sorted[index - 1];
    if (previous && value - previous > 1) result.push("ellipsis");
    result.push(value);
  });
  return result;
}

function setFeedPage(page) {
  const nextPage = Number.parseInt(page, 10);
  if (!Number.isFinite(nextPage) || nextPage < 1 || nextPage === state.page) return;
  state.page = nextPage;
  loadAll();
}

function renderFeedPagination(data) {
  if (!feedPagination) return;
  const totalPages = Number(data.total_pages || 1);
  const page = Number(data.page || 1);
  state.page = page;
  if (totalPages <= 1) {
    feedPagination.hidden = true;
    feedPagination.innerHTML = "";
    return;
  }
  const disabled = "";
  const pages = pageWindow(page, totalPages).map((value) => {
    if (value === "ellipsis") {
      return `<span class="pagination-ellipsis" aria-label="${i18n("pagination.ellipsis")}">...</span>`;
    }
    const current = value === page;
    return `
      <button class="pagination-page" type="button" data-feed-page="${value}" aria-current="${current ? "page" : "false"}"${disabled}>
        ${value}
      </button>
    `;
  }).join("");
  feedPagination.hidden = false;
  feedPagination.innerHTML = `
    <div class="pagination-pages" role="group" aria-label="${i18n("pagination.feed")}">
      <button class="pagination-step" type="button" data-feed-page="${page - 1}"${page <= 1 ? " disabled" : disabled}>${i18n("pagination.previous")}</button>
      ${pages}
      <button class="pagination-step" type="button" data-feed-page="${page + 1}"${page >= totalPages ? " disabled" : disabled}>${i18n("pagination.next")}</button>
    </div>
    <form class="pagination-jump" data-pagination-jump>
      <label>
        <span>${i18n("pagination.jumpLabel")}</span>
        <input type="number" min="1" max="${totalPages}" value="${page}" inputmode="numeric" aria-label="${i18n("pagination.jumpLabel")}">
      </label>
      <button type="submit"${disabled}>${i18n("pagination.jump")}</button>
    </form>
  `;
  feedPagination.querySelectorAll("[data-feed-page]").forEach((button) => {
    button.addEventListener("click", () => setFeedPage(button.dataset.feedPage));
  });
  feedPagination.querySelector("[data-pagination-jump]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = event.currentTarget.querySelector("input");
    setFeedPage(input?.value || "1");
  });
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
  const summaryPreview = textPreview(summary, isRepository ? 180 : 240);
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
  const visualRail = mediaPreview
    ? `<aside class="article-visual" aria-label="${i18n("article.media")}">${mediaPreview}</aside>`
    : "";

  return `
    <article class="article${visualRail ? " has-visual" : ""}${mediaPreview ? " has-media" : ""}" id="article-${escapeHtml(item.id)}">
      <div class="article-top">
        <div class="article-meta-stack">
          <div class="article-meta">${escapeHtml(item.fuente)}${time ? ` - ${escapeHtml(time)}` : ""}</div>
          <div class="badge-row"><span class="badge">${escapeHtml(item.area_label)}</span>${sourcePreferenceBadge}</div>
        </div>
        <div class="article-controls">
          ${starMetric}
          <div class="score">${Number(item.selected_score || 0).toFixed(0)}</div>
          ${favoriteButton}
        </div>
      </div>
      <div class="article-main">
        <div class="article-content">
          <h4 class="article-heading">${escapeHtml(titleParts.title)}</h4>
          ${summary ? expandableText(summary, "article-summary", titleParts.title, summaryPreview) : ""}
          ${tags ? `<div class="tag-row">${tags}</div>` : ""}
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

function setSummaryLoading(articleId, loading) {
  document.querySelectorAll("[data-summary]").forEach((button) => {
    if (button.dataset.summary !== articleId) return;
    button.disabled = loading;
    button.classList.toggle("is-generating", loading);
    const label = button.querySelector(".summary-button-label");
    if (label) label.textContent = loading ? i18n("article.generating") : i18n("article.generate");
    if (loading) {
      button.setAttribute("aria-busy", "true");
    } else {
      button.removeAttribute("aria-busy");
    }
  });
}

async function generateSummary(articleId, button) {
  if (!await ensureUser(button)) return;
  if (summaryRequests.has(articleId)) return summaryRequests.get(articleId);
  setSummaryLoading(articleId, true);
  const request = (async () => {
    const result = await fetchJson(withLanguage(`/api/articles/${encodeURIComponent(articleId)}/summary`), { method: "POST" });
    if (result.summary) {
      applyGeneratedSummary(articleId, result.summary, button);
    }
  })();
  summaryRequests.set(articleId, request);
  try {
    await request;
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    summaryRequests.delete(articleId);
    setSummaryLoading(articleId, false);
  }
}

function applyGeneratedSummary(articleId, summary, button) {
  const article = document.getElementById(`article-${articleId}`);
  if (!article) return;
  const existingSummary = article.querySelector(".article-summary");
  const cleanSummary = String(summary || "");
  if (existingSummary) {
    const summaryText = existingSummary.querySelector("span");
    if (summaryText) {
      summaryText.textContent = cleanSummary;
      summaryText.dataset.fullText = cleanSummary;
      summaryText.dataset.shortText = cleanSummary;
    } else {
      existingSummary.textContent = cleanSummary;
    }
    existingSummary.setAttribute("aria-expanded", "false");
    const label = existingSummary.querySelector("[data-expandable-label]");
    if (label) label.textContent = expandableLabel(false);
  } else {
    const heading = article.querySelector(".article-heading");
    if (heading) {
      heading.insertAdjacentHTML("afterend", expandableText(cleanSummary, "article-summary", heading.textContent || "", textPreview(cleanSummary, 240)));
    }
  }
  button?.remove();
  syncExpandableTextLabels(article);
}

async function toggleFavorite(articleId, button) {
  if (!await ensureUser(button)) return;
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
  resetFeedPage();
  window.clearTimeout(search._timer);
  suggestions.hidden = true;
  suggestions.innerHTML = "";
  loadAll();
}

function hideSuggestions() {
  suggestionAbortController?.abort();
  suggestionRequestId += 1;
  suggestions.hidden = true;
  suggestions.innerHTML = "";
}

async function loadSuggestions() {
  const q = search.value.trim();
  if (q.length < 2) {
    hideSuggestions();
    return;
  }
  const requestId = ++suggestionRequestId;
  suggestionAbortController?.abort();
  suggestionAbortController = new AbortController();
  try {
    const params = formParams();
    params.set("q", q);
    const data = await fetchJson(`/api/search/suggestions?${params}`, { signal: suggestionAbortController.signal });
    if (requestId !== suggestionRequestId) return;
    if (!data.suggestions.length) {
      suggestions.hidden = true;
      return;
    }
    suggestions.innerHTML = data.suggestions
      .map((item) => `
        <button type="button" data-title="${escapeHtml(item.title)}" data-query="${escapeHtml(item.query || cleanSuggestionQuery(item.title) || item.title)}">
          ${renderTitleLabel(item.title)}
          <small>${escapeHtml(item.source)} - ${i18n("filters.score").toLowerCase()} ${formatScore(item.score)}</small>
        </button>
      `)
      .join("");
    suggestions.hidden = false;
    suggestions.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        search.value = button.dataset.query || button.dataset.title || "";
        state.query = search.value.trim();
        resetFeedPage();
        suggestions.hidden = true;
        loadAll();
      });
    });
  } catch (error) {
    if (error.name !== "AbortError") {
      suggestions.hidden = true;
    }
  } finally {
    if (requestId === suggestionRequestId) {
      suggestionAbortController = null;
    }
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
  resetFeedPage();
  syncDateMode();
  loadAll();
  loadSuggestions();
});
navButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const target = button.dataset.viewTarget || "today";
    if (target === state.view) return;
    if (target === "today") {
      setViewMode("today");
      resetFeedPage();
      loadAll();
    } else if (target === "briefs") {
      loadDailyBriefs();
    } else if (target === "favorites") {
      if (!await ensureUser(button)) {
        showFavoritesSignInPrompt(button);
        return;
      }
      loadFavorites();
    } else if (target === "sources") {
      if (!await ensureUser(button)) return;
      setViewMode("sources");
      setStatus("");
    } else if (target === "more") {
      setViewMode("more");
    } else {
      setViewMode("today");
      resetFeedPage();
      loadAll();
    }
  });
});
search.addEventListener("input", () => {
  if (state.view !== "today") return;
  const draftQuery = search.value.trim();
  window.clearTimeout(search._timer);
  if (!draftQuery) {
    hideSuggestions();
    return;
  }
  loadSuggestions();
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
  resetFeedPage();
  hideSuggestions();
  loadAll();
});
document.addEventListener("click", (event) => {
  const expandable = event.target instanceof Element ? event.target.closest("[data-expandable-text]") : null;
  if (expandable instanceof HTMLButtonElement) {
    toggleExpandableText(expandable);
    return;
  }
  if (event.target instanceof Element && event.target.closest(".search")) return;
  hideSuggestions();
});
mediaModalClose?.addEventListener("click", closeMediaModal);
mediaModal?.addEventListener("click", (event) => {
  if (event.target === mediaModal) closeMediaModal();
});
authRequiredDialog?.querySelector("[data-login-prompt]")?.addEventListener("click", () => {
  closeAuthRequiredDialog(false);
  requireLogin();
});
authRequiredClose?.addEventListener("click", () => closeAuthRequiredDialog());
authRequiredDialog?.querySelector("[data-auth-dialog-close]")?.addEventListener("click", () => closeAuthRequiredDialog());
authRequiredDialog?.addEventListener("cancel", () => {
  window.setTimeout(() => closeAuthRequiredDialog(), 0);
});
logoutConfirmAction?.addEventListener("click", confirmLogout);
logoutConfirmCancel?.addEventListener("click", closeLogoutConfirmDialog);
logoutConfirmClose?.addEventListener("click", closeLogoutConfirmDialog);
logoutConfirmDialog?.addEventListener("cancel", () => {
  window.setTimeout(() => closeLogoutConfirmDialog(), 0);
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
renderInitialFeedSkeleton();
initAuth().finally(loadAll);
window.setInterval(loadAll, 300000);
