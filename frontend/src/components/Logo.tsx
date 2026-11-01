/**
 * Screening Room's logo: a small cinema screen with a play mark, and a two-tone
 * wordmark. Kept clearly larger than TMDB's logo in the footer (their terms, §3).
 * The same mark is the browser-tab icon (public/favicon.svg).
 */
export function LogoMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <defs>
        <linearGradient id="logo-gradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f59e0b" />
          <stop offset="1" stopColor="#e11d48" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-gradient)" />
      {/* A wide screen, gently curved like a cinema's, on two short legs. */}
      <path d="M6 9.5 Q16 7.5 26 9.5 V20.5 Q16 18.5 6 20.5 Z" fill="#fff" fillOpacity="0.95" />
      <path d="M14 11.5 L19.5 14.5 L14 17.5 Z" fill="#e11d48" />
      <path d="M11 22 L10 25.5 M21 22 L22 25.5" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="flex items-center gap-2">
      <LogoMark className="h-8 w-8 shrink-0" />
      <span className="text-lg leading-none font-bold tracking-tight whitespace-nowrap">
        Screening{" "}
        <span className="bg-gradient-to-r from-amber-600 to-rose-600 bg-clip-text text-transparent dark:from-amber-400 dark:to-rose-400">
          Room
        </span>
      </span>
    </span>
  );
}
