import { type ReactNode, type Ref, useId, useRef, useState } from "react";
import { Link } from "react-router";

import { Button } from "../../components/Button";
import { describeError } from "../../lib/errors";
import { formatRuntime } from "../../lib/format";
import { type Genre, useGenres } from "../titles/api";
import {
  ANY_CONTEXT,
  SHORTLIST_SIZE,
  type DiscoverContext,
  type DiscoverState,
  useDiscoverState,
  useRecommend,
  useHide,
} from "./api";
import { RecommendationCard } from "./RecommendationCard";

const RUNTIME_LIMITS = [90, 120, 150];

/** "/": pick a context (all optional), get 3-5 explained recommendations (FR-08-10). */
export function DiscoverPage() {
  const state = useDiscoverState().data;
  const genres = useGenres().data ?? [];
  const recommend = useRecommend();
  // The form starts from the last request's context, e.g. after opening a title.
  const [context, setContext] = useState<DiscoverContext>(state?.context ?? ANY_CONTEXT);
  const listRef = useRef<HTMLElement>(null);

  return (
    <div className="space-y-8 py-2">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Find something to watch</h1>
        <p className="text-stone-600 dark:text-stone-400">
          Everything here is optional. Set what you're in the mood for, or just ask.
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          recommend.mutate({ context, seenIds: [] });
        }}
        className="space-y-4"
      >
        <ContextControls
          context={context}
          genres={genres}
          onChange={(next) => {
            setContext(next);
            // Once there's a list, changing a filter updates it right away.
            if (state) {
              recommend.mutate({ context: next, seenIds: [] });
            }
          }}
        />
        <Button type="submit" disabled={recommend.isPending}>
          {recommend.isPending ? "Finding…" : "Find something"}
        </Button>
      </form>

      {recommend.isError && (
        <p role="alert" className="text-red-600 dark:text-red-400">
          {describeError(recommend.error)}
        </p>
      )}

      {state && (
        <Shortlist
          ref={listRef}
          state={state}
          isLoading={recommend.isPending}
          onMore={() => {
            recommend.mutate(
              { context: state.context, seenIds: state.seenIds },
              {
                // The button is at the bottom: take people to the top of the new list.
                onSuccess: () => {
                  listRef.current?.focus({ preventScroll: true });
                  listRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                },
              },
            );
          }}
        />
      )}
    </div>
  );
}

function ContextControls({
  context,
  genres,
  onChange,
}: {
  context: DiscoverContext;
  genres: Genre[];
  onChange: (context: DiscoverContext) => void;
}) {
  const isTv = context.media_type === "tv";
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium">Movie or TV</legend>
        <div className="flex overflow-hidden rounded-md border border-stone-300 text-sm dark:border-stone-700">
          {(
            [
              ["any", "Either"],
              ["movie", "Movie"],
              ["tv", "TV"],
            ] as const
          ).map(([value, label]) => (
            <label
              key={value}
              className="flex-1 cursor-pointer px-3 py-2 text-center has-checked:bg-amber-700 has-checked:text-white has-focus-visible:outline-2 has-focus-visible:outline-amber-600"
            >
              <input
                type="radio"
                name="media_type"
                value={value}
                checked={context.media_type === value}
                onChange={() => {
                  onChange({ ...context, media_type: value });
                }}
                className="sr-only"
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <Select
        label="Genre"
        value={context.genre_id === null ? "" : String(context.genre_id)}
        onChange={(value) => {
          onChange({ ...context, genre_id: value ? Number(value) : null });
        }}
      >
        <option value="">Any genre</option>
        {genres.map((genre) => (
          <option key={genre.id} value={genre.id}>
            {genre.name}
          </option>
        ))}
      </Select>

      <Select
        label="Time you have"
        hint={isTv ? "Applies to movies only." : undefined}
        disabled={isTv}
        value={isTv || context.max_runtime_minutes === null ? "" : String(context.max_runtime_minutes)}
        onChange={(value) => {
          onChange({ ...context, max_runtime_minutes: value ? Number(value) : null });
        }}
      >
        <option value="">Any length</option>
        {RUNTIME_LIMITS.map((minutes) => (
          <option key={minutes} value={minutes}>
            Up to {formatRuntime(minutes)}
          </option>
        ))}
      </Select>
    </div>
  );
}

function Select({
  label,
  hint,
  value,
  disabled = false,
  onChange,
  children,
}: {
  label: string;
  hint?: string | undefined;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <select
        id={id}
        aria-describedby={hint ? `${id}-hint` : undefined}
        value={value}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="block w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-stone-700 dark:bg-stone-900"
      >
        {children}
      </select>
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-stone-500 dark:text-stone-400">
          {hint}
        </p>
      )}
    </div>
  );
}

function Shortlist({
  ref,
  state,
  isLoading,
  onMore,
}: {
  ref: Ref<HTMLElement>;
  state: DiscoverState;
  isLoading: boolean;
  onMore: () => void;
}) {
  const hide = useHide();
  const { shortlist, hiddenIds } = state;
  const visible = shortlist.results.filter((result) => !hiddenIds.includes(result.title.id));
  // Fewer than a full shortlist: nothing else matches (the few_results notice says so).
  const hasMore = shortlist.results.length === SHORTLIST_SIZE;

  return (
    <section
      ref={ref}
      tabIndex={-1} // focusable from code only, after "show me more"
      aria-label="Recommendations"
      aria-busy={isLoading}
      className="scroll-mt-4 space-y-6 outline-none"
    >
      {shortlist.notices.map((notice) => (
        <p
          key={notice.code}
          role="status"
          className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        >
          {notice.text}
          {notice.code === "cold_start" && (
            <>
              {" "}
              <Link to="/taste" className="font-medium underline">
                Pick some favorites
              </Link>
            </>
          )}
        </p>
      ))}

      {visible.length > 0 ? (
        <ol className="space-y-6">
          {visible.map((recommendation) => (
            <li key={recommendation.result_id}>
              <RecommendationCard
                recommendation={recommendation}
                onHide={() => {
                  hide(recommendation.title.id);
                }}
              />
            </li>
          ))}
        </ol>
      ) : (
        shortlist.results.length > 0 && (
          <p className="text-stone-500 dark:text-stone-400">That’s all of these set aside. Want to see more?</p>
        )
      )}

      {hasMore && (
        <Button variant="quiet" onClick={onMore} disabled={isLoading}>
          {isLoading ? "Finding…" : "Show me more"}
        </Button>
      )}
    </section>
  );
}
