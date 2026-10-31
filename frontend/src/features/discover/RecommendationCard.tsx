import { Link } from "react-router";

import { Button } from "../../components/Button";
import { Poster } from "../../components/Poster";
import { StarRating } from "../../components/StarRating";
import { describeError } from "../../lib/errors";
import { formatRuntime } from "../../lib/format";
import { type TitleState, useLibraryChange, useTitleState } from "../library/api";
import { type Recommendation, useResultEvent } from "./api";

/** One result: poster, facts, why it was picked (FR-10), and what you can do with it (FR-11). */
export function RecommendationCard({
  recommendation,
  onHide,
}: {
  recommendation: Recommendation;
  onHide: () => void;
}) {
  const { title, reasons } = recommendation;
  const href = `/titles/${String(title.id)}`;
  const event = useResultEvent(recommendation.result_id);
  const facts = [
    title.media_type === "movie" ? "Movie" : "TV series",
    title.year === null ? null : String(title.year),
    title.media_type === "movie" && title.runtime_minutes
      ? formatRuntime(title.runtime_minutes)
      : null,
  ].filter((fact) => fact !== null);
  const opened = () => {
    event.mutate({ type: "opened" }); // logged in the background while the page opens
  };

  return (
    <article aria-labelledby={`title-${String(title.id)}`} className="flex gap-4">
      <Link to={href} onClick={opened} tabIndex={-1} aria-hidden="true" className="shrink-0">
        <Poster url={title.poster_url} name={title.name} className="w-24 sm:w-32" />
      </Link>
      <div className="min-w-0 flex-1 space-y-2">
        <h2 id={`title-${String(title.id)}`} className="text-lg leading-tight font-semibold">
          <Link to={href} onClick={opened} className="hover:underline">
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
        <CardActions recommendation={recommendation} event={event} onHide={onHide} />
      </div>
    </article>
  );
}

function CardActions({
  recommendation,
  event,
  onHide,
}: {
  recommendation: Recommendation;
  event: ReturnType<typeof useResultEvent>;
  onHide: () => void;
}) {
  const { title } = recommendation;
  const state = useTitleState(title.id).data;
  const unsave = useLibraryChange(title.id); // undoing a save isn't a recommendation event
  const busy = !state || event.isPending || unsave.isPending;
  const error = event.error ?? unsave.error;

  return (
    <div className="space-y-1">
      <div
        role="group"
        aria-label={`Actions for ${title.name}`}
        className="-ml-2 flex flex-wrap items-center gap-1 text-sm"
      >
        <ActionButton
          pressed={state?.in_watchlist ?? false}
          disabled={busy}
          label={`Save ${title.name}`}
          onClick={() => {
            if (state?.in_watchlist) {
              unsave.mutate({ kind: "unsave" });
            } else {
              event.mutate({ type: "saved" });
            }
          }}
        >
          Save
        </ActionButton>
        <ActionButton
          pressed={watched(state)}
          disabled={busy || watched(state)}
          label={`Mark ${title.name} watched`}
          onClick={() => {
            event.mutate({ type: "watched" });
          }}
        >
          Watched
        </ActionButton>
        <StarRating
          label={`Rate ${title.name}`}
          value={state?.rating ?? null}
          disabled={busy}
          onRate={(stars) => {
            event.mutate({ type: "rated", rating: stars });
          }}
        />
        <Button
          variant="quiet"
          disabled={busy}
          aria-label={`${title.name} is not for me`}
          onClick={() => {
            event.mutate({ type: "not_for_me" }, { onSuccess: onHide });
          }}
        >
          Not for me
        </Button>
        <Button
          variant="quiet"
          aria-label={`Skip ${title.name}`}
          onClick={() => {
            onHide(); // right away: a skip is only "not now"
            event.mutate({ type: "skipped" });
          }}
        >
          Skip
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {describeError(error)}
        </p>
      )}
    </div>
  );
}

function watched(state: TitleState | undefined): boolean {
  return (state?.watch_count ?? 0) > 0;
}

function ActionButton({
  pressed,
  disabled,
  label,
  onClick,
  children,
}: {
  pressed: boolean;
  disabled: boolean;
  label: string;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md px-2 py-1 font-medium focus-visible:outline-2 focus-visible:outline-amber-600 disabled:cursor-not-allowed ${
        pressed
          ? "text-amber-700 dark:text-amber-500"
          : "text-stone-700 hover:bg-stone-200 disabled:text-stone-400 dark:text-stone-300 dark:hover:bg-stone-800"
      }`}
    >
      {pressed && <span aria-hidden="true">✓ </span>}
      {children}
    </button>
  );
}
