import { type KeyboardEvent, useRef } from "react";

const STARS = [1, 2, 3, 4, 5];

/**
 * 1-5 whole stars (ADR-0009). Each star is a button; the current one is "pressed".
 *
 * One tab stop for the whole row (M5d): Tab reaches the current rating (or the
 * first star), arrow keys move between stars, Enter or Space rates. Moving
 * doesn't rate: every rating is saved, so it must be a deliberate choice.
 */
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
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const tabStop = value ?? 1;

  const move = (event: KeyboardEvent, from: number) => {
    const target = {
      ArrowRight: from + 1,
      ArrowUp: from + 1,
      ArrowLeft: from - 1,
      ArrowDown: from - 1,
      Home: 1,
      End: 5,
    }[event.key];
    if (target === undefined) {
      return;
    }
    event.preventDefault(); // don't scroll the page
    buttons.current[Math.min(5, Math.max(1, target)) - 1]?.focus();
  };

  return (
    <div role="group" aria-label={label} className="flex">
      {STARS.map((stars) => (
        <button
          key={stars}
          ref={(element) => {
            buttons.current[stars - 1] = element;
          }}
          type="button"
          tabIndex={stars === tabStop ? 0 : -1}
          aria-label={`${String(stars)} star${stars === 1 ? "" : "s"}`}
          aria-pressed={value === stars}
          disabled={disabled}
          onClick={() => {
            onRate(stars);
          }}
          onKeyDown={(event) => {
            move(event, stars);
          }}
          className="px-0.5 text-xl leading-none text-amber-500 hover:scale-110 focus-visible:outline-2 focus-visible:outline-amber-600 disabled:opacity-50"
        >
          {stars <= (value ?? 0) ? "★" : "☆"}
        </button>
      ))}
    </div>
  );
}
