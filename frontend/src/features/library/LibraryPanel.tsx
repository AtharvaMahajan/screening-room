import { useState } from "react";

import { Button } from "../../components/Button";
import { StarRating } from "../../components/StarRating";
import { describeError } from "../../lib/errors";
import { localToday } from "../../lib/format";
import { type TitleState, useLibraryChange, useTitleState } from "./api";

/**
 * The title page's library controls: save, watched (with an optional date, and
 * rewatches), rating, "not for me", each with its undo (data-model.md §5).
 */
export function LibraryPanel({ titleId }: { titleId: number }) {
  const state = useTitleState(titleId);
  const change = useLibraryChange(titleId);

  if (state.isPending) {
    return null; // the page around it is already loaded; avoid a flash of buttons
  }
  if (state.isError) {
    return (
      <p role="alert" className="text-sm">
        Couldn't load your library for this title. {describeError(state.error)}
      </p>
    );
  }
  return (
    <section aria-label="Your library" className="space-y-3">
      <Controls state={state.data} busy={change.isPending} onChange={change.mutate} />
      {change.isError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {describeError(change.error)}
        </p>
      )}
    </section>
  );
}

function Controls({
  state,
  busy,
  onChange,
}: {
  state: TitleState;
  busy: boolean;
  onChange: ReturnType<typeof useLibraryChange>["mutate"];
}) {
  const [watchedOn, setWatchedOn] = useState("");
  const [confirmingUnwatch, setConfirmingUnwatch] = useState(false);
  const today = localToday();

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Toggle
          on={state.in_watchlist}
          disabled={busy}
          onClick={() => {
            onChange({ kind: state.in_watchlist ? "unsave" : "save" });
          }}
        >
          Watchlist
        </Toggle>
        <Toggle
          on={state.not_for_me}
          disabled={busy}
          onClick={() => {
            onChange({ kind: state.not_for_me ? "undo_not_for_me" : "not_for_me" });
          }}
        >
          Not for me
        </Toggle>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        {state.watch_count > 0 && (
          <span>
            Watched {state.watch_count === 1 ? "once" : `${String(state.watch_count)} times`}
            {state.last_watched_on && `, last on ${state.last_watched_on}`}.
          </span>
        )}
        <label className="flex items-center gap-1 text-stone-600 dark:text-stone-400">
          On
          <input
            type="date"
            value={watchedOn}
            max={today}
            onChange={(event) => {
              setWatchedOn(event.target.value);
            }}
            aria-label="Date watched (optional)"
            className="rounded border border-stone-300 bg-white px-1 dark:border-stone-700 dark:bg-stone-900"
          />
        </label>
        <Button
          variant="quiet"
          disabled={busy}
          onClick={() => {
            onChange({ kind: "watched", watchedOn: watchedOn || null });
            setWatchedOn("");
          }}
        >
          {state.watch_count > 0 ? "Watched again" : "Mark watched"}
        </Button>
        {state.watch_count > 0 &&
          (confirmingUnwatch ? (
            <span role="group" aria-label="Confirm removing viewings" className="flex gap-2">
              Remove all {state.watch_count === 1 ? "" : `${String(state.watch_count)} `}viewings?
              <Button
                variant="quiet"
                onClick={() => {
                  onChange({ kind: "unwatch" });
                  setConfirmingUnwatch(false);
                }}
              >
                Remove
              </Button>
              <Button
                variant="quiet"
                onClick={() => {
                  setConfirmingUnwatch(false);
                }}
              >
                Cancel
              </Button>
            </span>
          ) : (
            <Button
              variant="quiet"
              disabled={busy}
              onClick={() => {
                setConfirmingUnwatch(true);
              }}
            >
              Remove from history
            </Button>
          ))}
      </div>

      <div className="flex items-center gap-3 text-sm">
        <StarRating
          value={state.rating}
          disabled={busy}
          onRate={(stars) => {
            onChange({ kind: "rate", stars });
          }}
        />
        {state.rating !== null && (
          <Button
            variant="quiet"
            disabled={busy}
            onClick={() => {
              onChange({ kind: "unrate" });
            }}
          >
            Clear rating
          </Button>
        )}
      </div>
    </div>
  );
}

function Toggle({
  on,
  disabled,
  onClick,
  children,
}: {
  on: boolean;
  disabled: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md border px-3 py-1.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 disabled:opacity-60 ${
        on
          ? "border-amber-600 bg-amber-600 text-white"
          : "border-stone-300 hover:bg-stone-200 dark:border-stone-700 dark:hover:bg-stone-800"
      }`}
    >
      {on && <span aria-hidden="true">✓ </span>}
      {children}
    </button>
  );
}
