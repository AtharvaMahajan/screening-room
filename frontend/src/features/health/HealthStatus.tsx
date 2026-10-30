import { ApiError } from "../../api/client";
import { useHealth } from "./api";

const DOT = {
  ok: "bg-green-600",
  problem: "bg-red-600",
  pending: "bg-stone-400",
} as const;

/** A small system-status indicator, shown in the footer of every page. */
export function HealthStatus() {
  const { isPending, isError, error, refetch, isFetching } = useHealth();

  let message: string;
  let tone: keyof typeof DOT;
  if (isPending) {
    message = "Checking the API…";
    tone = "pending";
  } else if (isError) {
    // The API answered with a known error code: it's up, but the database isn't.
    message =
      error instanceof ApiError && error.code === "database_unavailable"
        ? "The API is running, but it can't reach the database."
        : "Can't reach the API.";
    tone = "problem";
  } else {
    message = "API and database are up.";
    tone = "ok";
  }

  return (
    <div className="flex items-center gap-2 text-xs text-stone-500 dark:text-stone-400">
      <span aria-hidden="true" className={`size-2 rounded-full ${DOT[tone]}`} />
      {/* role="status" announces changes to screen readers. */}
      <p role="status">{message}</p>
      <button
        type="button"
        onClick={() => void refetch()}
        disabled={isFetching}
        className="underline hover:text-stone-700 disabled:no-underline dark:hover:text-stone-200"
      >
        {isFetching ? "Checking…" : "Check again"}
      </button>
    </div>
  );
}
