# M5a security review

Walk-through of [security.md](../architecture/security.md) against the code, 2026-10-31.
Each item was checked in the code, not ticked from memory; "Test" names the test that
fails if the rule breaks.

Legend: ✅ done and tested · ⚠️ done with a caveat · 🔲 open (decision or later slice)

## Threats (§1)

| Threat | Status | Evidence |
|---|---|---|
| Session theft via XSS | ✅ | HttpOnly session cookie; no tokens in browser storage (only an in-memory CSRF token: `frontend/src/api/client.ts`); no `dangerouslySetInnerHTML`; CSP added in M5a (see §7) |
| CSRF, including login CSRF | ✅ | Origin check + signed double-submit token: `test_csrf.py` |
| Cookie tossing | ✅ | `__Host-` names in production (`COOKIE_PREFIX_HOST`, default on) |
| Another user's data (IDOR) | ✅ | Cross-user tests for profile, library, lists, result events, account deletion |
| Password guessing | ✅ | Argon2id, generic errors, rate limits (§8) |
| Secret leakage | ✅ | TMDB token and CSRF secret are `SecretStr` settings; never logged (log calls reviewed, §9) |
| Token leak from the database | ✅ | Only SHA-256 of session tokens stored (`core/security.py`) |

## Rules

| Section | Rule | Status | Evidence |
|---|---|---|---|
| §2 | Argon2id; rehash on login when parameters change | ✅ | `argon2.PasswordHasher` defaults (Argon2id); `password_needs_rehash` in `authenticate` |
| §2 | 10-128 characters, no composition rules; generic errors | ✅ | `RegisterIn`; `test_auth.py` |
| §3 | 256-bit random token, hash stored, absolute 30 days, no sliding expiry | ✅ | `secrets.token_urlsafe(32)`; `test_auth.py` expiry tests |
| §3 | Login always creates a new session, revoking a presented one | ✅ | `_replace_session`; `test_auth.py` |
| §3 | Cookie flags: HttpOnly session, Secure, SameSite=Lax, `__Host-` | ✅ | `_signed_in` / `_set_csrf_cookie` |
| §4 | Same origin, no CORS | ✅ | No CORS middleware; Vite proxy in development. Production: the API serves the web app (M5f) |
| §5 | Signed, session-bound double-submit token; constant-time compares | ✅ | `identity/csrf.py` (`hmac.compare_digest`); `test_csrf.py` |
| §6 | `/api/me/...` only; every query filtered by the session's user | ✅ | Cross-user tests in `test_library.py`, `test_result_events.py`, `test_account_deletion.py` |
| §6 | Account deletion: CSRF + password, cascades everything | ✅ | `test_account_deletion.py` (generic check over every `user_id` table) |
| §7 | Bounded validation on every input | ✅ | Pydantic models with explicit limits |
| §7 | Mutations accept JSON only | ✅ | **Implicit before M5a** (FastAPI won't parse other types into a model). Now pinned: `test_mutations_accept_json_only` + its JSON control |
| §7 | No stack traces or SQL in responses | ✅ | `handle_unexpected_error` returns a generic 500 |
| §7 | SQL only through SQLAlchemy expressions | ✅ | No raw SQL strings in `src/` |
| §7 | HSTS, CSP, nosniff, Referrer-Policy, frame-ancestors | ⚠️ | Added in M5a: `test_security_headers.py`. Caveat: in development Vite serves the HTML, so the CSP only reaches the pages once the API serves the built app (M5f), where it must be re-checked in a browser |
| §8 | Login and registration rate limits | ✅ | Added in M5a: `test_rate_limits.py`, `test_rate_limit.py`. Caveat for M5f: behind a proxy, uvicorn needs `--proxy-headers` so limits see the real client IP |
| §9 | Never logged: passwords, tokens, cookies, Authorization, TMDB token | ✅ | Every log call reviewed. The TMDB client logs paths, not query parameters |
| §9 | Personal data in logs | ✅ | Fixed in M5a: search failures no longer log the search text |

## Dependencies

| Check | Result |
|---|---|
| `pip-audit` (Python, all dependencies) | No known vulnerabilities. Added to CI |
| `npm audit --omit=dev` (what ships to browsers) | 0 vulnerabilities. Added to CI |
| `npm audit` (including dev tools) | 14 moderate, **one advisory**: GHSA-g3hv-75wg-m249, a denial of service in `minimatch` reached only through ESLint and openapi-typescript. They only match our own patterns, so no exposure. The only offered fix (`--force`) downgrades typescript-eslint to 8.14, a breaking change. **Accepted; revisit when ESLint updates.** |

## Open before public launch (§10)

| Item | Status |
|---|---|
| API docs at `/api/docs` | 🔲 Turn off in production (M5f). They're exempt from the CSP because they load a CDN script |
| Breached-password check | 🔲 security.md: "before public launch, if feasible". Needs a decision: e.g. the Have I Been Pwned range API (sends only the first 5 characters of a SHA-1 hash) |
| Password reset by email | 🔲 Deferred: "required before inviting non-test users at scale". Needs email infrastructure |
