import { TMDB_NOTICE } from "./TmdbAttribution";

/** /about: where the data comes from (TMDB attribution, API Terms of Use §3). Public. */
export function AboutPage() {
  return (
    <article className="max-w-prose space-y-4 py-2">
      <h1 className="text-2xl font-semibold tracking-tight">About Screening Room</h1>
      <p>
        Screening Room suggests a short, explained list of movies and TV shows to watch, based on
        what you tell it you like. It's a free, non-commercial project.
      </p>

      <h2 className="text-lg font-semibold">Where the data comes from</h2>
      <p>
        Titles, overviews, genres, cast and crew, posters and the "recommended" lists behind some
        suggestions come from{" "}
        <a
          href="https://www.themoviedb.org/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-amber-700 underline dark:text-amber-500"
        >
          The Movie Database (TMDB)
        </a>
        , a community-built database. Our recommendations and their explanations are our own.
      </p>
      <a href="https://www.themoviedb.org/" target="_blank" rel="noopener noreferrer" className="inline-block">
        <img src="/tmdb-logo.svg" alt="TMDB" className="h-5 w-auto" />
      </a>
      <p className="text-sm">{TMDB_NOTICE}</p>
    </article>
  );
}
