import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { apiError, mockApi, signedOut } from "../../test/mockApi";
import { renderAt } from "../../test/render";

// The status indicator is in the footer of every page, including sign-in.
describe("footer system status", () => {
  it("reports that API and database are up", async () => {
    mockApi({ "GET /api/auth/session": signedOut });

    renderAt("/sign-in");

    expect(await screen.findByText("API and database are up.")).toBeInTheDocument();
  });

  it("distinguishes a database outage from an unreachable API", async () => {
    mockApi({
      "GET /api/auth/session": signedOut,
      "GET /api/health": () =>
        apiError(503, "database_unavailable", "The database is unavailable."),
    });

    renderAt("/sign-in");

    expect(
      await screen.findByText("The API is running, but it can't reach the database."),
    ).toBeInTheDocument();
  });

  it("reports an unreachable API when the request fails", async () => {
    mockApi({
      "GET /api/auth/session": signedOut,
      "GET /api/health": () => Promise.reject(new TypeError("Failed to fetch")),
    });

    renderAt("/sign-in");

    expect(await screen.findByText("Can't reach the API.")).toBeInTheDocument();
  });
});
