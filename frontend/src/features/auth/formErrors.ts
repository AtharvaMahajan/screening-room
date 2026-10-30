import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "../../api/client";

/** A message for people, for any error a request can throw. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    // Our API's messages are written for users, except for these two.
    if (error.code === "unknown_error" || error.code === "internal_error") {
      return "Something went wrong on our side. Please try again.";
    }
    return error.message;
  }
  return "Can't reach Screening Room. Check your connection and try again.";
}

/**
 * Show a failed submission on the form: per-field messages from a 422 next to
 * their inputs, anything else as one message for the whole form.
 */
export function showServerErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly Path<T>[],
): void {
  if (error instanceof ApiError && error.code === "validation_failed") {
    let placed = false;
    for (const detail of error.details) {
      const field = detail.field.replace(/^body\./, "") as Path<T>;
      if (fields.includes(field)) {
        setError(field, { message: detail.message });
        placed = true;
      }
    }
    if (placed) {
      return;
    }
  }
  setError("root.server", { message: describeError(error) });
}
