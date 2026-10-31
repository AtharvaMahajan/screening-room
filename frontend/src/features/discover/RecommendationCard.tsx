import { Link } from "react-router";

import { Button } from "../../components/Button";
import { Poster } from "../../components/Poster";
import { formatRuntime } from "../../lib/format";
import type { Recommendation } from "./api";

/** One result: poster, facts, overview, and why it was picked (FR-10). */
export function RecommendationCard({
  recommendation,
  onSkip,
}: {
  recommendation: Recommendation;
  onSkip: () => void;
}) {
  const { title, reasons } = recommendation;
  const href = `/titles/${String(title.id)}`;
  const facts = [
    title.media_type === "movie" ? "Movie" : "TV series",
    title.year === null ? null : String(title.year),
    title.media_type === "movie" && title.runtime_minutes
      ? formatRuntime(title.runtime_minutes)
      : null,
  ].filter((fact) => fact !== null);

  return (
    <article aria-labelledby={`title-${String(title.id)}`} className="flex gap-4">
      <Link to={href} tabIndex={-1} aria-hidden="true" className="shrink-0">
        <Poster url={title.poster_url} name={title.name} className="w-24 sm:w-32" />
      </Link>
      <div className="min-w-0 flex-1 space-y-2">
        <h2 id={`title-${String(title.id)}`} className="text-lg leading-tight font-semibold">
          <Link to={href} className="hover:underline">
            {title.name}
          </Link>
        </h2>
        <p className="text-sm text-stone-600 dark:text-stone-400">{facts.join(" · ")}</p>
        <ul aria-label={`Why ${title.name}`} className="space-y-1 text-sm">
          {reasons.map((reason) => (
            <li key={reason.type} className="flex gap-2">
              <span aria-hidden="true" className="text-amber-600">
                ✦
              </span>
              {reason.text}
            </li>
          ))}
        </ul>
        {title.overview && (
          <p className="line-clamp-3 text-sm leading-relaxed text-stone-700 dark:text-stone-300">
            {title.overview}
          </p>
        )}
        <Button
          variant="quiet"
          onClick={onSkip}
          aria-label={`Skip ${title.name}`}
          className="-ml-4"
        >
          Skip
        </Button>
      </div>
    </article>
  );
}
