# Admin auth testing playbook

Adapted from the custom bcrypt/PyJWT + MongoDB and OWASP synchronizer-token playbooks for the requested password-only administrator. No registration, email, or password-reset flow is in scope. Origin handling updated 2026-09-28 to resolve the user's live lastzhood.fun/admin rejection.

## 1. MongoDB verification
- Read credentials from `/app/memory/test_credentials.md`; URLs and DB settings from existing .env files.
- `admin_users` `_id=admin` has role admin and a bcrypt hash beginning `$2b$`; plaintext passwords/tokens must not be in public API or frontend bundle.
- `admin_sessions.session_id` unique index and `expires_at` TTL index; `admin_login_attempts.expires_at` TTL index.
- Startup is idempotent, preserves campaign values. Changed environment admin password invalidates previous sessions.

## 2. API tests
- Use EXTERNAL REACT_APP_BACKEND_URL, cookie jar; login sends `X-Admin-Client: lastzhood-admin` and application/json. Read login `csrf_token`, set `X-CSRF-Token` for all protected endpoints. Any HTTP(S) origin, lastzhood.fun/www and missing Origin work; CORS preflight reflects a concrete origin, never '*' with credentials. Opaque Origin:null is not a web origin and is not CORS-allowed.
- Anonymous GET/PUT settings and GET me: 401, no settings exposed or changed.
- Wrong login: 401. Correct login: 200; sets HttpOnly, Secure, SameSite=None access and refresh cookies restricted to /api/admin.
- Authenticated GET me/settings: 200, no hashes or Mongo _id.
- Missing login non-simple header or non-JSON content: 400. Correct header + password logs in from any HTTP(S) origin; changing Origin with valid session/proof is permitted. Cookie-only GET me/settings, PUT settings, refresh/logout must fail (401) without changing data/cookies/session. Wrong/mismatched proof: 403. No unauthenticated /csrf endpoint exists.
- Mongo session stores csrf_hash only; the raw proof is returned only by password login, never in public config, settings, me, refresh, logout, or logs. No-hash legacy session is invalid (401). Logging in again restores access; never ask users to clear cookies/cache.
- Save five independent fields, verify GET config and persisted Mongo record match exactly.
- Reject blank/whitespace text, unsafe/javascript/http/non-X URLs, credential URLs, invalid ports, oversized/unknown fields. All-or-nothing save; invalid payload leaves DB unchanged.
- Stale revision: 409, does not overwrite newer settings.
- Expired/tampered access token rejected; valid refresh cookie can get new access; expired/revoked refresh rejected.
- Logout revokes server session and deletes both cookies; replayed pre-logout cookies rejected.
- Six bad login attempts trigger 429; invalid attempts persist in MongoDB, bucketed by the single admin account (not ingress IP). Clean test-created throttle data afterwards.

## 3. Browser and regression
- Desktop 1920x800 and mobile 390x844 screenshots, no horizontal overflow; check long URLs/multiline Turkish/emoji text.
- Password visibility toggle, wrong/right login, reload retains session, Save disabled when unchanged; successful save shows timestamp/status, logout and re-login retain settings.
- Verify Like/Repost can differ. Reply composer text + its own URL; POST ON X composer admin claim_text + admin like_url + existing PUBLIC_APP_URL/?ref=CODE.
- Public already-open tab refreshes config on focus; public routes and participation flow remain functional.
- Test save error, server-unavailable retry, session-expiry behavior, stale revision recovery.
- Restore original campaign settings after tests, delete only test-created participation data.
- Run existing backend pytest regression tests. Real external X actions not performed; X intents are not verified social actions.

## Origin bug regression
- User domain https://lastzhood.fun/admin was independently read before the fix and showed the exact rejection message. Test source-code fix on the external preview URL; separately verify the user domain and explicitly distinguish if that host still serves an older build.
- Verify default wildcard CORS_ORIGINS support plus lastzhood.fun, www, another HTTPS site and missing Origin requests.
- Browser verify admin initial anonymous page displays login rather than old origin error, password login, saved-settings load/save/reload, session refresh, logout; no secrets printed. Same password, no campaign resets.
- Test new-tab/legacy sessions gracefully require login; forged/wrong/missing proof cannot use existing admin cookies from another origin. Test other-tab new login (cookie replaced) doesn't trap prior tab on an unrecoverable error screen.