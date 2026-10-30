import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderAt } from "../test/render";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("routes", () => {
  it("renders the home page inside the layout", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(Response.json({ status: "ok", database: "ok" })),
    );

    renderAt("/");

    expect(screen.getByRole("link", { name: "Screening Room" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Screening Room" })).toBeInTheDocument();
    await screen.findByText("API and database are up.");
  });

  it("renders a not-found page for unknown paths", () => {
    renderAt("/no-such-page");

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
