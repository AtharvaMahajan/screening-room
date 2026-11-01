/** Every page, rendered with realistic data, has no axe-core violations (M5d). */
import { screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Recommendations } from "../features/discover/api";
import type { TitleDetail } from "../features/titles/api";
import { accessibilityViolations } from "../test/a11y";
import { fakeLibrary } from "../test/fakeLibrary";
import { emptyTasteProfile, mockApi, signedIn, signedOut } from "../test/mockApi";
import { renderAt } from "../test/render";

const card = (id: number, name: string) => ({
  id,
  media_type: "movie" as const,
  name,
  year: 2016,
  poster_url: null,
});

const TITLE: TitleDetail = {
  ...card(42, "Arrival"),
  original_name: "Arrival",
  overview: "A linguist works to communicate with visitors.",
  release_date: "2016-11-10",
  runtime_minutes: 116,
  number_of_seasons: null,
  original_language: "en",
  vote_average: 7.6,
  vote_count: 20104,
  poster_url: "https://image.tmdb.org/t/p/w342/poster.jpg",
  backdrop_url: null,
  genres: [{ id: 7, slug: "drama", name: "Drama" }],
  cast: [{ name: "Amy Adams", character: "Louise Banks", profile_url: null }],
  directors: ["Denis Villeneuve"],
  creators: [],
  metadata_status: "stale",
};

const SHORTLIST: Recommendations = {
  request_id: 1,
  cold_start: true,
  notices: [{ code: "cold_start", text: "Recommendations improve as you pick favorites." }],
  results: [43, 44].map((id, i) => ({
    result_id: id,
    rank: i + 1,
    title: { ...card(id, `Film ${String(id)}`), overview: "An overview.", runtime_minutes: 100 },
    reasons: [{ type: "pool_source", text: "Popular on TMDB", anchor_title_id: null }],
  })),
};

const signedInApi = {
  "GET /api/auth/session": () => signedIn(),
  ...emptyTasteProfile,
  ...fakeLibrary([42, 43, 44], { 43: 43, 44: 44 }),
};

async function expectNoViolations() {
  expect(await accessibilityViolations()).toEqual([]);
}

describe("accessibility", () => {
  it("sign in", async () => {
    mockApi({ "GET /api/auth/session": signedOut });
    renderAt("/sign-in");
    await screen.findByRole("heading", { name: "Sign in" });
    await expectNoViolations();
  });

  it("register", async () => {
    mockApi({ "GET /api/auth/session": signedOut });
    renderAt("/register");
    await screen.findByRole("heading", { name: "Create your account" });
    await expectNoViolations();
  });

  it("onboarding", async () => {
    mockApi(signedInApi);
    renderAt("/welcome");
    await screen.findByRole("heading", { name: "1. Genres" });
    await expectNoViolations();
  });

  it("discover, with results", async () => {
    mockApi({ ...signedInApi, "POST /api/recommendations": () => Response.json(SHORTLIST) });
    renderAt("/");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Find something" }));
    await screen.findByRole("heading", { name: "Film 43" });
    await expectNoViolations();
  });

  it("a title page, with your library controls", async () => {
    mockApi({ ...signedInApi, "GET /api/titles/42": () => Response.json(TITLE) });
    renderAt("/titles/42");
    await screen.findByRole("region", { name: "Your library" });
    await expectNoViolations();
  });

  it("search, with results", async () => {
    mockApi({
      ...signedInApi,
      "GET /api/search?q=arrival": () => Response.json({ source: "local", results: [card(42, "Arrival")] }),
    });
    renderAt("/search?q=arrival");
    await screen.findByRole("region", { name: "Results for arrival" });
    await expectNoViolations();
  });

  it("library, with entries", async () => {
    mockApi({
      ...signedInApi,
      "GET /api/me/watchlist": () =>
        Response.json([{ title: card(42, "Arrival"), added_at: "2026-10-30T12:00:00Z" }]),
    });
    renderAt("/library");
    await screen.findByRole("button", { name: "Remove Arrival" });
    await expectNoViolations();
  });

  it("account", async () => {
    mockApi(signedInApi);
    renderAt("/account");
    await screen.findByRole("heading", { name: "Delete account" });
    await expectNoViolations();
  });

  it("goodbye", async () => {
    mockApi({ "GET /api/auth/session": signedOut });
    renderAt("/goodbye");
    await screen.findByRole("heading", { name: "Account deleted" });
    await expectNoViolations();
  });

  it("not found", async () => {
    mockApi({ "GET /api/auth/session": signedOut });
    renderAt("/no-such-page");
    await screen.findByRole("heading", { name: "Page not found" });
    await expectNoViolations();
  });
});
