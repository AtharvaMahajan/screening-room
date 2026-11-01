import { Link } from "react-router";

import { Button } from "../../components/Button";
import { describeError } from "../../lib/errors";
import { useGenres } from "../titles/api";
import { useFavorites, usePreferences, useSavePreferences } from "./api";
import { FavoritesPicker } from "./FavoritesPicker";
import { GenrePicker } from "./GenrePicker";

/**
 * The taste profile on one page: genres, then favorite titles (FR-02).
 *
 * `welcome` is the onboarding right after registration (/welcome); otherwise
 * it's the same page for editing later (/taste). Everything is optional and
 * saved as you go, so leaving at any point keeps what you chose.
 */
export function TastePage({ welcome = false }: { welcome?: boolean }) {
  const genres = useGenres();
  const preferences = usePreferences();
  const favorites = useFavorites();
  const save = useSavePreferences();

  const queries = [genres, preferences, favorites];
  const failed = queries.find((query) => query.isError);

  return (
    <div className="space-y-8 py-2">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          {welcome ? "What do you like to watch?" : "Your taste"}
        </h1>
        <p className="text-stone-600 dark:text-stone-400">
          {welcome
            ? "Pick a few genres and favorite titles so your first recommendations fit. Both are optional, and you can change them any time."
            : "Your recommendations use these. Changes are saved as you go."}
        </p>
      </header>

      {failed ? (
        <div className="space-y-3">
          <p role="alert">{describeError(failed.error)}</p>
          <Button
            variant="quiet"
            onClick={() => {
              queries.forEach((query) => void query.refetch());
            }}
          >
            Try again
          </Button>
        </div>
      ) : !genres.data || !preferences.data || !favorites.data ? (
        <p className="text-stone-500 dark:text-stone-400">Loading…</p>
      ) : (
        <>
          <section aria-labelledby="genres-heading" className="space-y-3">
            <h2 id="genres-heading" className="text-lg font-semibold">
              1. Genres
            </h2>
            <GenrePicker
              genres={genres.data}
              preferences={preferences.data}
              onChange={(next) => {
                save.mutate(next);
              }}
            />
            {save.isError && (
              <p role="alert" className="text-sm text-red-600 dark:text-red-400">
                Couldn't save your genres: {describeError(save.error)}
              </p>
            )}
          </section>

          <section aria-labelledby="favorites-heading" className="space-y-3">
            <h2 id="favorites-heading" className="text-lg font-semibold">
              2. Favorite titles
            </h2>
            <FavoritesPicker
              favorites={favorites.data}
              likedGenreIds={preferences.data.liked_genre_ids}
            />
          </section>
        </>
      )}

      <footer className="flex items-center gap-4 border-t border-stone-200 pt-6 dark:border-stone-800">
        <Link
          to="/"
          className="rounded-md bg-amber-700 px-4 py-2 text-sm font-medium text-white hover:bg-amber-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600"
        >
          {welcome ? "Show my recommendations" : "Done"}
        </Link>
        {welcome && (
          <Link to="/" className="text-sm text-stone-600 underline dark:text-stone-400">
            Skip for now
          </Link>
        )}
      </footer>
    </div>
  );
}
