import { type ReactNode, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Poster } from "../../components/Poster";
import { TextField } from "../../components/TextField";
import { describeError } from "../../lib/errors";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { type SearchResults, useCatalogSearch } from "../titles/api";
import { LocalOnlyNotice } from "./LocalOnlyNotice";

const TYPING_DELAY_MS = 400; // each pause is a TMDB request: don't send one per keystroke

const TYPES = [
  { value: null, label: "All" },
  { value: "movie", label: "Movies" },
  { value: "tv", label: "TV" },
] as const;
type MediaType = (typeof TYPES)[number]["value"];

// Released: a decade, matched on the year. Applied to the results already loaded.
const DECADES = [
  { value: null, label: "Any year", matches: () => true },
  { value: "2020s", label: "2020s", matches: (y: number) => y >= 2020 },
  { value: "2010s", label: "2010s", matches: (y: number) => y >= 2010 && y < 2020 },
  { value: "2000s", label: "2000s", matches: (y: number) => y >= 2000 && y < 2010 },
  { value: "1990s", label: "1990s", matches: (y: number) => y >= 1990 && y < 2000 },
  { value: "older", label: "Before 1990", matches: (y: number) => y < 1990 },
] as const;
type Decade = (typeof DECADES)[number]["value"];

/**
 * /search?q=&type=&released=: find any movie or TV show and open its page (FR-03).
 * Filters apply as soon as they change: the type asks TMDB again (for a full page
 * of that type), the decade narrows the results already shown.
 */
export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") ?? "");
  const query = useDebouncedValue(text.trim(), TYPING_DELAY_MS);
  const type = TYPES.find((t) => t.value === params.get("type"))?.value ?? null;
  const decade = DECADES.find((d) => d.value === params.get("released"))?.value ?? null;
  const search = useCatalogSearch(query, type);

  // Keep everything in the URL, so back, refresh and shared links work.
  const update = (next: { q?: string; type?: MediaType; released?: Decade }) => {
    const merged = { q: query, type, released: decade, ...next };
    const entries = Object.entries(merged).filter((entry): entry is [string, string] =>
      Boolean(entry[1]),
    );
    setParams(Object.fromEntries(entries), { replace: true });
  };
  const urlQuery = params.get("q") ?? "";
  useEffect(() => {
    if (query !== urlQuery) {
      update({ q: query });
    }
  }, [query, urlQuery]); // eslint-disable-line react-hooks/exhaustive-deps -- syncs the typed query only

  return (
    <div className="space-y-5 py-2">
      <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
      <TextField
        label="Movie or TV show"
        type="search"
        value={text}
        autoFocus
        onChange={(event) => {
          setText(event.target.value);
        }}
      />
      <div className="flex flex-wrap gap-x-6 gap-y-3">
        <Filter label="Type">
          {TYPES.map((t) => (
            <Chip
              key={t.label}
              pressed={type === t.value}
              onClick={() => {
                update({ type: t.value });
              }}
            >
              {t.label}
            </Chip>
          ))}
        </Filter>
        <Filter label="Released">
          {DECADES.map((d) => (
            <Chip
              key={d.label}
              pressed={decade === d.value}
              onClick={() => {
                update({ released: d.value });
              }}
            >
              {d.label}
            </Chip>
          ))}
        </Filter>
      </div>
      {search.isError && <p role="alert">{describeError(search.error)}</p>}
      {query && search.data && <Results results={search.data} query={query} decade={decade} />}
    </div>
  );
}

function Filter({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      <span aria-hidden="true" className="mr-1 text-sm font-medium">
        {label}
      </span>
      {children}
    </div>
  );
}

function Chip({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 ${
        pressed
          ? "border-amber-700 bg-amber-700 text-white"
          : "border-stone-300 hover:bg-stone-200 dark:border-stone-700 dark:hover:bg-stone-800"
      }`}
    >
      {children}
    </button>
  );
}

function Results({
  results,
  query,
  decade,
}: {
  results: SearchResults;
  query: string;
  decade: Decade;
}) {
  const inDecade = DECADES.find((d) => d.value === decade)?.matches ?? (() => true);
  const shown = results.results.filter(
    (title) => decade === null || (title.year !== null && inDecade(title.year)),
  );
  return (
    <section aria-label={`Results for ${query}`} className="space-y-4">
      {results.source === "local" && <LocalOnlyNotice />}
      {decade !== null && results.results.length > 0 && (
        <p className="text-sm text-stone-600 dark:text-stone-400">
          Showing {shown.length} of {results.results.length} results.
        </p>
      )}
      {shown.length === 0 ? (
        <p className="text-stone-500 dark:text-stone-400">
          No movies or shows match “{query}”{decade === null ? "" : " from then"}.
        </p>
      ) : (
        <ul className="grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-5">
          {shown.map((title) => (
            <li key={title.id}>
              <Link
                to={`/titles/${String(title.id)}`}
                className="group block space-y-1 text-sm focus-visible:outline-2 focus-visible:outline-amber-600"
              >
                <Poster
                  url={title.poster_url}
                  name={title.name}
                  className="w-full group-hover:opacity-80"
                />
                <span className="line-clamp-2 font-medium">{title.name}</span>
                <span className="block text-xs text-stone-500 dark:text-stone-400">
                  {[title.media_type === "movie" ? "Movie" : "TV", title.year]
                    .filter((part) => part !== null)
                    .join(" · ")}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
