# Newser Authentication and Private State Test Plan

## Scope

This plan covers the pre-integration verification for the new Supabase authentication work and related UI changes:

- Google and GitHub login through Supabase Auth.
- FastAPI bearer-token validation and `/api/me`.
- Private favorites, generated summaries, and preferences by authenticated user.
- Guest behavior and clean default state.
- Desktop sidebar and mobile More account UI.
- Protected-feature sign-in popup, logout confirmation, and source-preference gating.
- Shimmer loading states for articles, daily briefs, and favorites.
- Hot Topics visibility during loading.
- Regression checks for feed, search, briefs, media, scheduler health, and SQLite/Postgres schema initialization.

## Test Environments

| Environment | Purpose | Required configuration |
| --- | --- | --- |
| Local safe SQLite | Automated regression without external writes | `scripts/verify_safe.ps1` uses temporary SQLite and clears external API keys |
| Local app with Supabase Auth | Browser OAuth and UI testing | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, local redirect URL in Supabase allow list |
| Production/staging | Final integration smoke test | Production `DATABASE_URL`, Supabase Auth providers enabled, production redirect URL in Supabase allow list |

## Test Accounts and Data

Use at least three identities:

- `user_a_google`: Google login account.
- `user_b_google_or_github`: separate account to verify isolation.
- `user_a_github_same_email`: GitHub identity with the same verified email as `user_a_google`, if testing Supabase automatic linking.

Seed or retain at least:

- One Reuters or blog article without a private generated summary.
- One Hacker News item with comments.
- One GitHub Trending repository.
- At least one daily brief.
- At least one feed date with Hot Topics and one without Hot Topics.

## Automated Gates

Run these before any manual testing.

### A1. Safe Verification

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_safe.ps1
```

Expected:

- Python compilation passes.
- `tests.test_auth`, `tests.test_web_app`, `tests.test_hybrid_brief`, and `tests.test_media` pass.
- No Supabase database writes occur.
- No Gemini or GitHub API credentials are used.

### A2. Focused Static UI Verification

Command:

```powershell
$env:PYTHONPATH='.deps'; $env:DATABASE_URL='sqlite:///:memory:'; python -m unittest -v tests.test_web_app.WebUiStaticTests
```

Expected:

- Auth UI, provider buttons, sign-in popup, logout confirmation, shimmer classes, Hot Topics hiding, and asset version assertions pass.

### A3. Auth Token Verification

Command:

```powershell
$env:PYTHONPATH='.deps'; python -m unittest -v tests.test_auth
```

Expected:

- Valid Supabase JWT resolves user ID, email, and display name.
- Expired, malformed, wrong-audience, and wrong-issuer tokens return `401`.
- Name fallback order is `full_name`, then provider `name`, then email.
- Supabase `/auth/v1/user` fallback behaves as expected when JWKS validation fails.

### A4. Whitespace and Syntax Check

Commands:

```powershell
git diff --check
& 'C:\Users\sebal\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --check static/app.js
```

Expected:

- No whitespace errors.
- Frontend JavaScript parses successfully.

## Backend API Tests

### B1. Public Feed as Guest

Steps:

1. Start the app without an Authorization header.
2. Request `GET /api/feed`.

Expected:

- Response is `200`.
- Items are returned.
- Every item has `is_favorite=false`.
- User-generated summaries are empty for guests.
- No guest `user_id` is accepted or inferred from request data.

### B2. Authenticated Feed Annotations

Steps:

1. Login as `user_a`.
2. Save one article.
3. Generate a summary for another article.
4. Request `GET /api/feed` with `user_a` token.

Expected:

- Only `user_a` saved articles show `is_favorite=true`.
- Only `user_a` generated summaries are attached.
- Shared `noticias.resumen_ia*`, `noticias.is_favorite`, and `noticias.favorited_at` are not updated by these interactive actions.

### B3. User Isolation

Steps:

1. Login as `user_a`; save an article and generate a summary.
2. Login as `user_b`; request `GET /api/feed`, `GET /api/favorites`, and `GET /api/preferences`.
3. Request the same endpoints as a guest.

Expected:

- `user_b` does not see `user_a` favorites, generated summaries, or preferences.
- Guest does not see either user's private data.
- New authenticated users start with clean private tables and default preferences.

### B4. Protected Endpoints Require Auth

Test these endpoints without a bearer token:

- `GET /api/me`
- `GET /api/preferences`
- `PUT /api/preferences`
- `GET /api/favorites`
- `POST /api/articles/{article_id}/summary`
- `POST /api/articles/{article_id}/favorite`
- `DELETE /api/articles/{article_id}/favorite`

Expected:

- Each returns `401`.
- Public endpoints remain accessible: `GET /`, `GET /api/feed`, `GET /api/brief`, `GET /api/daily-briefs`, `GET /api/search/suggestions`, `GET /api/health`.

### B5. Favorite Mutations

Steps:

1. Login as `user_a`.
2. Save an existing article.
3. Save it again.
4. Remove it.
5. Save a missing article ID.

Expected:

- First save returns `200`, `is_favorite=true`, and `favorited_at`.
- Repeated save is idempotent.
- Delete returns `200`, `is_favorite=false`.
- Missing article returns `404`.
- `user_saved_items` uses `(user_id, article_id)` as the effective unique key.

### B6. Summary Generation

Steps:

1. Login as `user_a`.
2. Generate a summary for an existing article in Spanish.
3. Generate again for the same article and language.
4. Generate in English.
5. Attempt generation for a missing article.
6. Attempt generation while Gemini is unavailable.

Expected:

- New summaries are stored in `user_article_summaries`.
- Repeated same-language generation returns cached user summary.
- Spanish and English summaries are separate rows.
- Missing article returns `400` with clear reason.
- Generation failure returns `400` with clear reason.
- Lock key includes `user_id`, `article_id`, and language.

### B7. Preferences

Steps:

1. Login as `user_a`.
2. `GET /api/preferences`.
3. `PUT /api/preferences` with language `en`, theme `light`, and source preferences.
4. Reload and request preferences again.
5. Send invalid language, theme, source, and source preference value.

Expected:

- Default preferences are Spanish, dark theme, no source preferences.
- Valid preferences persist for only the current user.
- Invalid preferences return `400`.
- Request body cannot override `user_id`.

### B8. Schema Initialization

Steps:

1. Run app initialization against temporary SQLite.
2. Inspect tables.
3. Repeat against Postgres staging if available.

Expected:

- `user_saved_items`, `user_article_summaries`, and `user_preferences` exist.
- Foreign keys from private tables to `noticias.id` cascade on article deletion.
- Existing shared favorite and summary columns remain for compatibility.
- New private tables start empty unless user actions populate them.

## Frontend UI Tests

### F1. Desktop Account Section

Steps:

1. Open desktop viewport.
2. Observe sidebar signed-out state.
3. Click account row.
4. Login successfully.
5. Click account row while signed in.

Expected:

- Account block is the final sidebar item.
- Signed out row shows icon and login label.
- Expanded state uses `aria-expanded`.
- Google and GitHub buttons are visible with logos.
- Redirecting disables provider buttons and shows concise loading state.
- Signed-in row shows `full_name`, then provider `name`, then email fallback.
- Signed-in expansion exposes logout.

### F2. Collapsed Desktop Sidebar

Steps:

1. Collapse sidebar.
2. Click account icon.

Expected:

- Collapsed sidebar shows only account icon.
- Clicking expands the sidebar and reveals the account block.

### F3. Mobile More Account Section

Steps:

1. Open phone viewport.
2. Tap More.
3. Inspect Preferences and Account cards.

Expected:

- Account card appears below Preferences.
- Google and GitHub actions expand inline.
- No modal is used for provider choices.
- Card remains above fixed mobile tab bar with safe-area spacing.

### F4. Guest Protected Feature Popup

Steps:

1. As a guest, click Generate Summary.
2. As a guest, click a favorite heart.
3. As a guest, open Favorites.
4. As a guest, open Sources.

Expected:

- Popup opens immediately.
- Popup copy is concise: sign in to continue.
- Buttons are centered, visually balanced, and not cramped.
- Sign-in button starts login flow.
- Cancel and close dismiss the popup and return focus.
- No inline sign-in prompt remains in the page content.

### F5. Logout Confirmation

Steps:

1. Login.
2. Expand account section.
3. Click logout.
4. Cancel.
5. Click logout again and confirm.

Expected:

- Confirmation popup appears.
- Cancel keeps the user logged in.
- Confirm signs out, clears private in-memory state, resets guest defaults, and reloads public feed.

### F6. Guest Language and Theme

Steps:

1. Clear session.
2. Change language.
3. Toggle light/dark theme.

Expected:

- Guest can change language and theme without login.
- No sign-in popup appears for language or theme.
- Guest source preferences still require login.

### F7. Shimmer Loading

Steps:

1. Throttle network or use a slow local endpoint.
2. Load Today's Updates.
3. Open Daily Briefs.
4. Open Favorites while authenticated.
5. Repeat on mobile.

Expected:

- Article list shows shimmer article skeletons while loading.
- Daily Briefs shows current brief and archive-row skeletons while loading.
- Favorites shows article skeletons while loading.
- No `Cargando briefs diarios...` or `Cargando favoritos...` status text appears.
- Archive label does not appear while Daily Brief skeletons load.
- Motion stops when `prefers-reduced-motion: reduce` is enabled.

### F8. Hot Topics During Loading

Steps:

1. Reload the homepage with a slow feed response.
2. Change filters to trigger a reload.

Expected:

- Hot Topics panel is hidden during feed loading.
- Hot Topics appears only after `renderHotTopics()` receives non-empty data.
- No empty Hot Topics box flashes before feed data returns.

### F9. Accessibility and Responsiveness

Steps:

1. Navigate with keyboard only.
2. Test visible focus on account, provider, popup, logout, favorite, summary, language, theme, and source controls.
3. Test long display names and long emails.
4. Test Spanish and English.
5. Test dark and light themes.
6. Test desktop, tablet, narrow phone, and wide phone viewports.

Expected:

- Controls are real buttons or links.
- Focus is visible and logical.
- Dialog focus is trapped by browser modal behavior and returns after close.
- Long names/emails do not overflow.
- Text does not overlap controls.
- UI uses existing product styling and remains visually consistent.

## OAuth Provider Smoke Tests

### O1. Google Local Login

Preconditions:

- Supabase Site URL and Redirect URLs include local app URL.
- Google OAuth Authorized redirect URI is the Supabase callback URL: `https://<project-ref>.supabase.co/auth/v1/callback`.

Steps:

1. Start local app.
2. Click Continue with Google.
3. Complete consent.
4. Return to app.

Expected:

- URL is cleaned after OAuth return.
- Sidebar/mobile account state updates without manual navigation.
- `/api/me` succeeds with bearer token.
- Private endpoints work.

### O2. GitHub Local Login

Preconditions:

- Supabase GitHub provider has client ID and secret.
- GitHub OAuth callback URL is the Supabase callback URL.

Steps:

1. Click Continue with GitHub.
2. Complete consent.
3. Return to app.

Expected:

- Same as Google local login.
- Display name fallback is correct if GitHub email or name differs.

### O3. Production OAuth

Steps:

1. Add production app URL to Supabase redirect allow list.
2. Verify Google and GitHub provider callback URLs still point to Supabase callback URL.
3. Deploy.
4. Login with Google and GitHub on production.

Expected:

- Production login returns to production app, not localhost.
- Account state updates.
- Protected endpoints accept production Supabase tokens.
- No provider access tokens are stored by Newser.

### O4. OAuth Failure and Cancellation

Steps:

1. Cancel Google consent.
2. Cancel GitHub consent.
3. Temporarily test an invalid redirect allow-list entry in a non-production project.

Expected:

- User sees a clear auth error in the status region.
- App does not get stuck in loading state.
- Account section remains usable.
- Existing guest feed remains usable.

## Data Privacy and Retention Tests

### P1. No Cross-User Leakage

Steps:

1. `user_a` saves and summarizes article `A`.
2. `user_b` saves and summarizes article `B`.
3. Compare feed and favorites responses for both users.

Expected:

- `user_a` sees only `A` private state.
- `user_b` sees only `B` private state.
- Guest sees neither.

### P2. Clean New Account

Steps:

1. Create a new Supabase user.
2. Load feed, favorites, preferences, and summaries.

Expected:

- Favorites is empty.
- Preferences are defaults.
- Generated summaries are absent until the user generates them.
- Public articles still appear.

### P3. Article Deletion Cleanup

Steps:

1. Create private favorite and private summary for an article.
2. Delete the article through cleanup or direct test setup.
3. Inspect private tables.

Expected:

- Dependent private rows are removed.
- Other users' unrelated private rows remain.

## Production Readiness Checks

Run after deployment:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_runtime_health.ps1 -BaseUrl https://your-newser-host
```

Expected:

- `/api/health` returns `200`.
- Database connectivity is healthy.
- Feed refresh job exists.
- Daily brief job exists.
- Scheduler has no `last_error`.

Also verify:

- `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` are present.
- `DATABASE_URL` points to the intended production database.
- Supabase JWT signing uses asymmetric keys compatible with JWKS validation.
- Google and GitHub provider secrets are configured only in provider/Supabase dashboards.
- Supabase redirect allow list includes local and production URLs.

## Acceptance Criteria

Integration is ready only when all of the following are true:

- All automated gates pass.
- Google and GitHub login work locally.
- Google and GitHub login work in production or staging.
- Missing, expired, malformed, wrong-issuer, and wrong-audience tokens are rejected.
- Two users cannot see, modify, or receive each other's favorites, summaries, or preferences.
- New users and guests receive clean states.
- Guest protected-feature attempts open the sign-in popup immediately.
- Language and theme remain available to guests.
- Source preferences, favorites, and summary generation require login.
- Logout requires confirmation and clears private UI state.
- Shimmer loading appears for feed, daily briefs, and favorites.
- Hot Topics is hidden while feed content is loading.
- No old shared favorite or summary columns are exposed or updated by interactive web actions.
- Production health check passes.

## Sign-Off Checklist

| Area | Owner | Result | Notes |
| --- | --- | --- | --- |
| Automated safe verification |  |  |  |
| Auth token validation |  |  |  |
| Backend private-data isolation |  |  |  |
| Preferences API |  |  |  |
| Frontend desktop UI |  |  |  |
| Frontend mobile UI |  |  |  |
| Protected-feature popup |  |  |  |
| Logout confirmation |  |  |  |
| Shimmer loading and Hot Topics loading state |  |  |  |
| Google OAuth local |  |  |  |
| GitHub OAuth local |  |  |  |
| Google OAuth production/staging |  |  |  |
| GitHub OAuth production/staging |  |  |  |
| Production health |  |  |  |
