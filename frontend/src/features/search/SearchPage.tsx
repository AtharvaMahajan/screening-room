import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Poster } from "../../components/Poster";
import { TextField } from "../../components/TextField";
import { describeError } from "../../lib/errors";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { type SearchResults, useCatalogSearch } from "../titles/api";
import { LocalOnlyNotice } from "./LocalOnlyNotice";

const TYPING_DELAY_MS = 400; // each pause is a TMDB request: don't send one per keystroke

/** /search?q=: find any movie or TV show and open its page (FR-03). */
export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") ?? "");
  const query = useDebouncedValue(text.trim(), TYPING_DELAY_MS);
  const search = useCatalogSearch(query);

  // Keep the query in the URL, so back, refresh and shared links work.
  useEffect(() => {
    if (query !== (params.get("q") ?? "")) {
      setParams(query ? { q: query } : {}, { replace: true });
    }
  }, [query, params, setParams]);

  return (
    <div className="space-y-6 py-2">
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
      {search.isError && <p role="alert">{describeError(search.error)}</p>}
      {query && search.data && <Results results={search.data} query={query} />}
    </div>
  );
}

function Results({ results, query }: { results: SearchResults; query: string }) {
  return (
    <section aria-label={`Results for ${query}`} className="space-y-4">
      {results.source === "local" && <LocalOnlyNotice />}
      {results.results.length === 0 ? (
        <p className="text-stone-500">No movies or shows match “{query}”.</p>
      ) : (
        <ul className="grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-5">
          {results.results.map((title) => (
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
                <span className="block text-xs text-stone-500">
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
