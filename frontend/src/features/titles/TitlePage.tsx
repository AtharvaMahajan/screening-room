import { Link, useParams } from "react-router";

import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { Poster } from "../../components/Poster";
import { describeError } from "../../lib/errors";
import { formatRuntime, languageName, yearOf } from "../../lib/format";
import { type TitleDetail, useTitle } from "./api";

/** /titles/:titleId (signed-in users; behind RequireAuth). */
export function TitlePage() {
  const titleId = Number(useParams().titleId);
  // Anything that isn't a positive whole number can't be a title: no request needed.
  if (!Number.isSafeInteger(titleId) || titleId < 1) {
    return <NotFound />;
  }
  return <TitleLoader titleId={titleId} />;
}

function TitleLoader({ titleId }: { titleId: number }) {
  const title = useTitle(titleId);

  if (title.isPending) {
    return <p className="py-8 text-stone-500">Loading…</p>;
  }
  if (title.isError) {
    if (title.error instanceof ApiError && title.error.status === 404) {
      return <NotFound />;
    }
    return (
      <div className="space-y-3 py-8">
        <p role="alert">{describeError(title.error)}</p>
        <Button variant="quiet" onClick={() => void title.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  return <TitleView title={title.data} />;
}

function NotFound() {
  return (
    <div className="space-y-3 py-4">
      <h1 className="text-2xl font-semibold tracking-tight">Title not found</h1>
      <p>
        <Link to="/" className="text-amber-700 underline dark:text-amber-500">
          Go to the home page
        </Link>
      </p>
    </div>
  );
}

function TitleView({ title }: { title: TitleDetail }) {
  const facts = [
    title.media_type === "movie" ? "Movie" : "TV series",
    title.release_date ? yearOf(title.release_date) : null,
    title.media_type === "movie" && title.runtime_minutes
      ? formatRuntime(title.runtime_minutes)
      : null,
    title.number_of_seasons
      ? `${String(title.number_of_seasons)} season${title.number_of_seasons === 1 ? "" : "s"}`
      : null,
    title.original_language ? languageName(title.original_language) : null,
  ].filter((fact) => fact !== null);
  const people = title.media_type === "movie" ? title.directors : title.creators;

  return (
    <article className="space-y-6 py-2">
      <MetadataNotice status={title.metadata_status} />
      <div className="flex flex-col gap-6 sm:flex-row">
        <Poster url={title.poster_url} name={title.name} className="w-40 self-start sm:w-56" />

        <div className="min-w-0 space-y-3">
          <h1 className="text-3xl font-semibold tracking-tight">{title.name}</h1>
          {title.original_name && title.original_name !== title.name && (
            <p className="text-stone-500 italic">{title.original_name}</p>
          )}
          <p className="text-sm text-stone-600 dark:text-stone-400">{facts.join(" · ")}</p>
          {title.vote_average !== null && title.vote_count ? (
            <p className="text-sm">
              <span className="font-medium">★ {title.vote_average.toFixed(1)}</span>
              <span className="text-stone-500">
                {" "}
                / 10 from {title.vote_count.toLocaleString("en-US")} TMDB votes
              </span>
            </p>
          ) : null}
          {title.genres.length > 0 && (
            <ul aria-label="Genres" className="flex flex-wrap gap-2">
              {title.genres.map((genre) => (
                <li
                  key={genre.slug}
                  className="rounded-full bg-stone-200 px-3 py-1 text-xs dark:bg-stone-800"
                >
                  {genre.name}
                </li>
              ))}
            </ul>
          )}
          {title.overview && <p className="leading-relaxed">{title.overview}</p>}
          {people.length > 0 && (
            <p className="text-sm">
              <span className="text-stone-500">
                {title.media_type === "movie" ? "Directed by" : "Created by"}{" "}
              </span>
              {people.join(", ")}
            </p>
          )}
        </div>
      </div>

      {title.cast.length > 0 && (
        <section aria-labelledby="cast-heading" className="space-y-3">
          <h2 id="cast-heading" className="text-lg font-semibold">
            Cast
          </h2>
          <ul className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
            {title.cast.map((member) => (
              <li key={`${member.name}-${member.character ?? ""}`} className="text-sm">
                <span className="font-medium">{member.name}</span>
                {member.character && <span className="text-stone-500"> as {member.character}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

/** Tells people when TMDB couldn't refresh the data (catalog-ingestion.md §11). */
function MetadataNotice({ status }: { status: TitleDetail["metadata_status"] }) {
  if (status === "fresh") {
    return null;
  }
  return (
    <p
      role="status"
      className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200"
    >
      {status === "stale"
        ? "Some details may be out of date: we couldn't refresh them just now."
        : "Showing basic information only: full details aren't available right now."}
    </p>
  );
}
