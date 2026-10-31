import { ApiError } from "../api/client";

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
