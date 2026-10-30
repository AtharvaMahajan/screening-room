import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderAt } from "../../test/render";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("home page health status", () => {
  it("reports that API and database are up", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(Response.json({ status: "ok", database: "ok" })),
    );

    renderAt("/");

    expect(await screen.findByText("API and database are up.")).toBeInTheDocument();
  });

  it("distinguishes a database outage from an unreachable API", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        Response.json(
          { error: { code: "database_unavailable", message: "The database is unavailable." } },
          { status: 503 },
        ),
      ),
    );

    renderAt("/");

    expect(
      await screen.findByText("The API is running, but it can't reach the database."),
    ).toBeInTheDocument();
  });

  it("reports an unreachable API when the request fails", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));

    renderAt("/");

    expect(await screen.findByText("Can't reach the API.")).toBeInTheDocument();
  });
});
