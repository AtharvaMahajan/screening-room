/** A title's poster, or a same-sized placeholder when TMDB has none. Size it with `className`. */
export function Poster({
  url,
  name,
  className = "",
}: {
  url: string | null;
  name: string;
  className?: string;
}) {
  if (url) {
    return (
      <img
        src={url}
        alt={`Poster for ${name}`}
        loading="lazy"
        className={`aspect-[2/3] shrink-0 rounded-md object-cover shadow-md ${className}`}
      />
    );
  }
  return (
    <div
      aria-hidden="true"
      className={`flex aspect-[2/3] shrink-0 items-center justify-center rounded-md bg-stone-200 text-center text-xs text-stone-500 dark:text-stone-400 dark:bg-stone-800 ${className}`}
    >
      No poster
    </div>
  );
}
