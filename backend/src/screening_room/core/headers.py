"""Security headers on every response (security.md §7).

Today they cover the API's JSON. Once the API also serves the built web app
(single same-origin deployment, M5f), the same headers protect its pages,
which is why the Content-Security-Policy is written for the web app: our own
scripts, styles and API, plus TMDB's image CDN.
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

TMDB_IMAGES = "https://image.tmdb.org"

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        f"img-src 'self' {TMDB_IMAGES}",  # posters and photos come from TMDB's CDN
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",  # nobody may frame the app (clickjacking)
    ]
)

# FastAPI's API docs page loads its scripts from a CDN and runs inline code, so
# the policy above would break it. It's a development aid; production turns it off.
DOCS_PATHS = ("/api/docs",)


def security_headers(*, https: bool) -> dict[str, str]:
    headers = {
        "Content-Security-Policy": CONTENT_SECURITY_POLICY,
        "X-Content-Type-Options": "nosniff",  # no guessing content types
        "Referrer-Policy": "same-origin",  # other sites (e.g. TMDB) see no referrer
        "X-Frame-Options": "DENY",  # frame-ancestors for older browsers
        "Cross-Origin-Opener-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    if https:
        # Browsers ignore HSTS over plain http, so it's only sent over HTTPS deployments.
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


def add_security_headers(app: FastAPI, *, https: bool) -> None:
    headers = security_headers(https=https)

    @app.middleware("http")
    async def set_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)  # no blocking work here: just headers
        for name, value in headers.items():
            if name == "Content-Security-Policy" and request.url.path.startswith(DOCS_PATHS):
                continue
            response.headers.setdefault(name, value)
        return response
