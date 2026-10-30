import { ApiError } from "../../api/client";
import { useHealth } from "./api";

export function HealthStatus() {
  const { isPending, isError, error, refetch, isFetching } = useHealth();

  let message: string;
  let tone: "ok" | "problem" | "pending";
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
    <section className="health" aria-labelledby="health-heading">
      <h2 id="health-heading">System status</h2>
      {/* role="status" announces changes to screen readers. */}
      <p role="status" className={`health__message health__message--${tone}`}>
        {message}
      </p>
      <button
        type="button"
        onClick={() => void refetch()}
        disabled={isFetching}
      >
        {isFetching ? "Checking…" : "Check again"}
      </button>
    </section>
  );
}
