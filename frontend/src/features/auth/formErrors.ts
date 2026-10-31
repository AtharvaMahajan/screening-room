import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "../../api/client";
import { describeError } from "../../lib/errors";

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
