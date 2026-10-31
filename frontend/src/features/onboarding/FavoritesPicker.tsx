import { useState } from "react";

import { Poster } from "../../components/Poster";
import { TextField } from "../../components/TextField";
import { describeError } from "../../lib/errors";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { type TitleCard, useTitleSearch } from "../titles/api";
import { type Favorites, useAddFavorite, useRemoveFavorite } from "./api";

const RESULTS = 12;
const TYPING_DELAY_MS = 250;

/**
 * Pick favorite titles from the local pool: search by name, or choose from
 * well-known titles in the genres you like. Each pick is saved immediately.
 */
export function FavoritesPicker({
  favorites,
  likedGenreIds,
}: {
  favorites: Favorites;
  likedGenreIds: number[];
}) {
  const [query, setQuery] = useState("");
  const typed = useDebouncedValue(query.trim(), TYPING_DELAY_MS);
  const results = useTitleSearch(typed, likedGenreIds, RESULTS);
  const add = useAddFavorite();
  const remove = useRemoveFavorite();

  const picked = new Set(favorites.favorites.map((title) => title.id));
  const isFull = favorites.favorites.length >= favorites.max_favorites;
  const error = add.error ?? remove.error;

  let heading = "Popular picks";
  if (typed) {
    heading = `Results for “${typed}”`;
  } else if (likedGenreIds.length > 0) {
    heading = "Popular in your genres";
  }

  return (
    <div className="space-y-5">
      <section aria-labelledby="picked-heading" className="space-y-2">
        <h3 id="picked-heading" className="font-medium">
          Your favorites{" "}
          <span className="text-sm font-normal text-stone-500">
            {favorites.favorites.length} of {favorites.max_favorites}
          </span>
        </h3>
        {favorites.favorites.length === 0 ? (
          <p className="text-sm text-stone-500">None yet. Pick a few titles you love below.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {favorites.favorites.map((title) => (
              <li
                key={title.id}
                className="flex items-center gap-1 rounded-full bg-stone-200 py-1 pr-1 pl-3 text-sm dark:bg-stone-800"
              >
                {title.name}
                <button
                  type="button"
                  aria-label={`Remove ${title.name}`}
                  disabled={remove.isPending}
                  onClick={() => {
                    remove.mutate(title.id);
                  }}
                  className="rounded-full px-2 text-stone-500 hover:bg-stone-300 hover:text-stone-900 dark:hover:bg-stone-700 dark:hover:text-stone-100"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {describeError(error)}
        </p>
      )}

      <TextField
        label="Search for a movie or show"
        type="search"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
        }}
        hint={isFull ? "You've picked the maximum. Remove one to pick another." : undefined}
      />

      <section aria-labelledby="results-heading" className="space-y-2">
        <h3 id="results-heading" className="font-medium">
          {heading}
        </h3>
        {results.isError && (
          <p role="alert" className="text-sm">
            {describeError(results.error)}
          </p>
        )}
        {results.data?.length === 0 && (
          <p className="text-sm text-stone-500">
            Nothing matches. Our catalog is a curated set of well-known titles, so try another.
          </p>
        )}
        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
          {results.data?.map((title) => (
            <li key={title.id}>
              <PickButton
                title={title}
                isPicked={picked.has(title.id)}
                disabled={isFull || add.isPending}
                onPick={() => {
                  add.mutate(title.id);
                }}
              />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function PickButton({
  title,
  isPicked,
  disabled,
  onPick,
}: {
  title: TitleCard;
  isPicked: boolean;
  disabled: boolean;
  onPick: () => void;
}) {
  const label = [title.name, title.year].filter((part) => part !== null).join(", ");
  return (
    <button
      type="button"
      aria-label={isPicked ? `${label} (picked)` : `Pick ${label}`}
      aria-pressed={isPicked}
      disabled={isPicked || disabled}
      onClick={onPick}
      className="group w-full space-y-1 text-left text-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 disabled:cursor-not-allowed"
    >
      <span className="relative block">
        <Poster
          url={title.poster_url}
          name={title.name}
          className="w-full group-enabled:group-hover:opacity-80"
        />
        {isPicked && (
          <span className="absolute inset-0 flex items-center justify-center rounded-md bg-amber-600/80 text-sm font-semibold text-white">
            ✓ Picked
          </span>
        )}
      </span>
      <span className="line-clamp-2 font-medium">{title.name}</span>
      {title.year !== null && <span className="text-stone-500">{title.year}</span>}
    </button>
  );
}
