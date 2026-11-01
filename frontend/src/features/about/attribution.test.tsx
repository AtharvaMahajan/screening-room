/** TMDB attribution (API Terms of Use §3): exact notice and logo on every page. */
import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { accessibilityViolations } from "../../test/a11y";
import { mockApi, signedIn, signedOut } from "../../test/mockApi";
import { renderAt } from "../../test/render";

// Copied from TMDB's terms on purpose, not imported: if someone edits the
// constant, this test should notice the wording no longer matches the terms.
const REQUIRED_NOTICE =
  "This website uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB.";

describe("TMDB attribution", () => {
  it.each([
    ["signed out", "/sign-in", signedOut],
    ["signed in", "/", () => signedIn()],
  ])("is in the footer of every page (%s)", async (_, path, session) => {
    mockApi({ "GET /api/auth/session": session });
    renderAt(path);

    const footer = await screen.findByRole("contentinfo");
    expect(within(footer).getByText(REQUIRED_NOTICE)).toBeVisible();
    const logo = within(footer).getByRole("img", { name: "TMDB" });
    expect(logo).toHaveAttribute("src", "/tmdb-logo.svg");
    expect(logo.closest("a")).toHaveAttribute("href", "https://www.themoviedb.org/");
  });

  it("has an about page anyone can open", async () => {
    mockApi({ "GET /api/auth/session": signedOut });
    renderAt("/about");

    expect(
      await screen.findByRole("heading", { name: "Where the data comes from" }),
    ).toBeVisible();
    expect(screen.getAllByText(REQUIRED_NOTICE)).toHaveLength(2); // page and footer
    expect(await accessibilityViolations()).toEqual([]);
  });

  it("opens TMDB in a new tab without giving it access to this one", async () => {
    mockApi({ "GET /api/auth/session": signedOut });
    renderAt("/about");

    const links = await screen.findAllByRole("link", { name: /TMDB/ });
    for (const link of links) {
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });
});
