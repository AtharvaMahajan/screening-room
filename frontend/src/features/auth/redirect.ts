/**
 * Where to go after signing in, from the `?next=` query parameter.
 *
 * Only paths inside this app are allowed. Anything else falls back to "/", so a
 * crafted link like /sign-in?next=//evil.example can't send a freshly signed-in
 * user to another site (an "open redirect").
 */
export function safeNextPath(next: string | null): string {
  if (!next?.startsWith("/")) {
    return "/"; // absolute URLs (https://...) and empty values
  }
  // "//host" and "/\host" are treated by browsers as links to another host.
  if (next.startsWith("//") || next.startsWith("/\\")) {
    return "/";
  }
  return next;
}

/** The sign-in URL that returns to `path` afterwards. */
export function signInPath(path: string): string {
  return path === "/" ? "/sign-in" : `/sign-in?next=${encodeURIComponent(path)}`;
}
