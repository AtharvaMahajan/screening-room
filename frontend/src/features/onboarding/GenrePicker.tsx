import type { Genre } from "../titles/api";
import type { Preferences } from "./api";

type Stance = "like" | "avoid";

/**
 * Two rows of toggle buttons: genres you like, genres to avoid. A genre can't
 * be both (the API rejects it), so choosing one side clears the other.
 */
export function GenrePicker({
  genres,
  preferences,
  onChange,
}: {
  genres: Genre[];
  preferences: Preferences;
  onChange: (preferences: Preferences) => void;
}) {
  const liked = new Set(preferences.liked_genre_ids);
  const avoided = new Set(preferences.avoided_genre_ids);

  const toggle = (genreId: number, stance: Stance) => {
    const [mine, other] = stance === "like" ? [liked, avoided] : [avoided, liked];
    if (mine.has(genreId)) {
      mine.delete(genreId);
    } else {
      mine.add(genreId);
      other.delete(genreId);
    }
    onChange({ liked_genre_ids: [...liked], avoided_genre_ids: [...avoided] });
  };

  return (
    <div className="space-y-5">
      <GenreRow
        label="Genres you like"
        genres={genres}
        selected={liked}
        stance="like"
        onToggle={toggle}
      />
      <GenreRow
        label="Genres to avoid"
        hint="We'll never recommend these."
        genres={genres}
        selected={avoided}
        stance="avoid"
        onToggle={toggle}
      />
    </div>
  );
}

const SELECTED: Record<Stance, string> = {
  like: "border-amber-600 bg-amber-600 text-white",
  avoid: "border-stone-700 bg-stone-700 text-white line-through dark:border-stone-300 dark:bg-stone-300 dark:text-stone-900",
};

function GenreRow({
  label,
  hint,
  genres,
  selected,
  stance,
  onToggle,
}: {
  label: string;
  hint?: string;
  genres: Genre[];
  selected: Set<number>;
  stance: Stance;
  onToggle: (genreId: number, stance: Stance) => void;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="font-medium">
        {label}
        {hint && <span className="ml-2 text-sm font-normal text-stone-500">{hint}</span>}
      </legend>
      <div className="flex flex-wrap gap-2">
        {genres.map((genre) => {
          const isSelected = selected.has(genre.id);
          return (
            <button
              key={genre.id}
              type="button"
              aria-pressed={isSelected}
              onClick={() => {
                onToggle(genre.id, stance);
              }}
              className={`rounded-full border px-3 py-1 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600 ${
                isSelected
                  ? SELECTED[stance]
                  : "border-stone-300 hover:bg-stone-200 dark:border-stone-700 dark:hover:bg-stone-800"
              }`}
            >
              {genre.name}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
