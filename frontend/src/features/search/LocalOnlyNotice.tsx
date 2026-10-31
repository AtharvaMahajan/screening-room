/** Shown when search results came from our own catalog because TMDB was unreachable. */
export function LocalOnlyNotice() {
  return (
    <p
      role="status"
      className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200"
    >
      TMDB search isn't available right now, so these are only titles already in Screening Room.
    </p>
  );
}
