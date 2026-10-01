# Admin panel — final verification (2026-09-28)

## Resolved findings from iteration_4.json
- HIGH: ingress IP rotation split failed login attempts. Replaced IP bucket with an atomic MongoDB bucket for the single administrator; no forwarded headers trusted. Targeted throttle test: **1 passed**. Full suite afterwards: **34 passed**, zero failures/skips, `/app/test_reports/pytest/admin_final_results.xml`.
- Initial-load retry coverage completed using test-only browser request interception: injected 503 displays error + retry, removing interception and retrying restores login/settings successfully. No production test hook or mocked production API added.
- Additional conflict UX fix: editing after a 409 no longer hides the reload action while Save remains locked. Browser verified that reload stays visible, restores saved values, and logout returns to login.

## Verified flows
- Password-only login, invalid password, visibility toggle, cookie session reload/refresh, logout revocation, missing/evil Origin rejected, payload validation, stale revision protection.
- Five independently editable fields persisted in MongoDB; public tasks and share intents use them. Reply text/link and claim text handle Turkish, multiline text and emojis. Existing referral URL retained.
- Public console, claim/POST ON X, profile, referrals and public-tab focus refresh passed testing agent checks.
- Desktop 1920×800, mobile 390×844 screenshots; no horizontal overflow. Testing agent also measured 320/768/1024/1440 widths.
- Initial build: successful. Final browser failure/recovery script: all PASS; mobile overflow `[]`. Screenshot `/app/test_reports/admin-error-recovery-mobile.jpg`.

## Data / scope
- Original campaign values restored after mutation tests. Temporary UI participant removed. Removed disposable restore-to-.env and cleanup scripts to avoid accidental future resets.
- Existing X tasks remain user-declared: X intent generation works, but actual social actions are not verified by X API.
- No remaining known core-flow bugs. Authentication credentials documented in `/app/memory/test_credentials.md`.