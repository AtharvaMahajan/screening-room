# ADR-0007: Authenticate with server-side sessions in HttpOnly cookies, protected by signed double-submit CSRF tokens

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [security](../architecture/security.md) · [ADR-0006](0006-sync-sqlalchemy-handler-owned-transactions.md) · [data-model §3.1](../architecture/data-model.md#31-identity-m1)

## Context

The SPA and API are deployed on one origin. Users must only access their own private data (FR-01). Account deletion must remove sessions. Token storage in JavaScript (e.g. `localStorage`) is exposed to any XSS. Cookie-based authentication requires CSRF protection, including for unauthenticated endpoints such as login, because login CSRF is a real attack. The SPA needs a defined way to obtain its first CSRF token before it has a session.

## Decision

**Sessions**
- Email and password. Argon2id password hashes.
- A 256-bit random session token in a **HttpOnly, Secure, SameSite=Lax** cookie (`__Host-sr_session` in production). The database stores only its **SHA-256 hash** in `user_sessions`.
- **Absolute expiry** (initial value: 30 days). **No sliding expiry and no `last_seen_at` writes**, so session validation is read-only and shares the request transaction ([ADR-0006](0006-sync-sqlalchemy-handler-owned-transactions.md)).
- Login always issues a new session and revokes any session presented with the request. Logout revokes. Account deletion cascades.

**CSRF: signed double-submit, bound to the session**
- Token = `nonce.HMAC-SHA256(CSRF_SECRET, binding | nonce)`, with `binding = "anon"` when there's no valid session, or the session's token hash when authenticated. No CSRF state is stored.
- **Bootstrap:** `GET /api/auth/session` returns `{user | null, csrf_token}` and sets the readable `__Host-sr_csrf` cookie if it's missing or invalid for the current binding. The SPA keeps the token in memory and sends `X-CSRF-Token` on every unsafe request.
- **Unauthenticated unsafe requests** (register, login) require a valid **anonymous-bound** token and an allowed `Origin`.
- **On login or registration** the token is **rotated** to a session-bound token, returned in both the cookie and the body.
- **Validation of each unsafe request:** Origin allowlist → resolve session → header equals cookie → MAC valid for the current binding. Failures return `403 origin_rejected` or `403 csrf_failed`. Route authentication (401) runs after that.
- An expired session makes session-bound tokens fail. The SPA re-bootstraps once and then retries or routes to sign-in.
- **Defence in depth:** SameSite=Lax, JSON-only mutations, `__Host-` prefixes, no CORS.

**Deployment:** same origin (Vite proxy in development). Login and registration rate limiting before public deployment (M5).

## Alternatives considered

| Option | Why not chosen |
|---|---|
| JWT access + refresh tokens | Revocation needs a denylist or short lifetimes with refresh rotation. Storing tokens in JS is exposed to XSS, and storing them in cookies reintroduces CSRF anyway |
| Third-party auth service or OAuth only | External dependency and extra setup. Email and password is enough for the MVP |
| Synchronizer token stored in `user_sessions` | Needs a separate mechanism (and storage) for anonymous login and registration tokens. The signed token covers both cases without state |
| Plain (unsigned) double-submit | Vulnerable to cookie injection. Signing plus session binding closes that |
| SameSite cookies alone | Doesn't cover same-site attacks or older browser edge cases. Login CSRF needs an explicit defence |
| Sliding sessions with `last_seen_at` | Writes on every read request, which conflicts with read-only requests ([ADR-0006](0006-sync-sqlalchemy-handler-owned-transactions.md)). Deferred |

## Consequences

**Positive**
- No tokens are readable by page scripts except the CSRF token, which is useless without the HttpOnly session cookie.
- Instant revocation and simple deletion.
- Stateless CSRF validation that also protects login.

**Negative / accepted costs**
- One indexed session lookup per request.
- `CSRF_SECRET` becomes a managed secret. Rotating it forces a harmless re-bootstrap.
- Users are logged out after 30 days regardless of activity. Sliding expiry is deferred.
- Same-origin deployment is a requirement.

## Revisit when

A non-browser client (e.g. a native app) needs API access, users ask for longer or sliding sessions, or multi-instance deployment needs shared rate-limit state.
