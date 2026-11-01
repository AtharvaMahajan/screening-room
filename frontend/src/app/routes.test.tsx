import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mockApi, signedIn, signedOut } from "../test/mockApi";
import { renderAt } from "../test/render";

describe("routes", () => {
  it("renders the signed-in home page inside the layout", async () => {
    mockApi({ "GET /api/auth/session": () => signedIn() });

    renderAt("/");

    expect(
      await screen.findByRole("heading", { name: "Find something to watch" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Screening Room" })).toBeInTheDocument();
  });

  it("renders a not-found page for unknown paths, signed in or not", () => {
    mockApi({ "GET /api/auth/session": signedOut });

    renderAt("/no-such-page");

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});

describe("header", () => {
  it.each([
    ["/", "Discover"],
    ["/search", "Search"],
    ["/library", "Library"],
    ["/taste", "Your taste"],
  ])("marks the current page's tab (%s)", async (path, current) => {
    mockApi({ "GET /api/auth/session": () => signedIn() });
    renderAt(path);

    const nav = await screen.findByRole("navigation", { name: "Main" });
    const marked = within(nav)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page")
      .map((link) => link.textContent);
    expect(marked).toEqual([current]);
  });

  it("shows the logo as the home link, and no page tabs when signed out", async () => {
    mockApi({ "GET /api/auth/session": signedOut });
    renderAt("/sign-in");

    expect(await screen.findByRole("link", { name: "Screening Room" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });
});
