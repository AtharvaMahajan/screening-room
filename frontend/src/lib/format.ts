/** Small display helpers for catalog data. */

/** 116 -> "1h 56m"; 45 -> "45m". */
export function formatRuntime(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) {
    return `${String(rest)}m`;
  }
  return rest === 0 ? `${String(hours)}h` : `${String(hours)}h ${String(rest)}m`;
}

/** "2016-11-10" -> "2016". */
export function yearOf(isoDate: string): string {
  return isoDate.slice(0, 4);
}

const languageNames = new Intl.DisplayNames(["en"], { type: "language" });

/** "ko" -> "Korean". Falls back to the code if the browser doesn't know it. */
export function languageName(code: string): string {
  try {
    return languageNames.of(code) ?? code;
  } catch {
    return code;
  }
}
