const STARS = [1, 2, 3, 4, 5];

/** 1-5 whole stars (ADR-0009). Each star is a button; the current one is "pressed". */
export function StarRating({
  value,
  onRate,
  disabled = false,
  label = "Your rating",
}: {
  value: number | null;
  onRate: (stars: number) => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex">
      {STARS.map((stars) => (
        <button
          key={stars}
          type="button"
          aria-label={`${String(stars)} star${stars === 1 ? "" : "s"}`}
          aria-pressed={value === stars}
          disabled={disabled}
          onClick={() => {
            onRate(stars);
          }}
          className="px-0.5 text-xl leading-none text-amber-500 hover:scale-110 focus-visible:outline-2 focus-visible:outline-amber-600 disabled:opacity-50"
        >
          {stars <= (value ?? 0) ? "★" : "☆"}
        </button>
      ))}
    </div>
  );
}
