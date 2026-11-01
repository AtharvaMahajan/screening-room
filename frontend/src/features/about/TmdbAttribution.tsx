import { Link } from "react-router";

/**
 * TMDB's required attribution (API Terms of Use §3): their logo, less prominent
 * than our own branding, and this exact notice. Shown on every page.
 */
export const TMDB_NOTICE =
  "This website uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB.";

export function TmdbAttribution() {
  return (
    <p className="flex flex-wrap items-center gap-2 text-xs text-stone-600 dark:text-stone-400">
      <a href="https://www.themoviedb.org/" target="_blank" rel="noopener noreferrer">
        {/* Kept small: TMDB's logo must be less prominent than ours (§3). */}
        <img src="/tmdb-logo.svg" alt="TMDB" className="h-3 w-auto" />
      </a>
      <span>{TMDB_NOTICE}</span>
      <Link to="/about" className="underline">
        About the data
      </Link>
    </p>
  );
}
