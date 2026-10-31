import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeLibrary } from "../../test/fakeLibrary";
import { apiError, callsTo, mockApi, signedIn } from "../../test/mockApi";
import { renderAt } from "../../test/render";
import type { TitleDetail } from "./api";

const ARRIVAL: TitleDetail = {
  id: 42,
  media_type: "movie",
  name: "Arrival",
  original_name: "Arrival",
  overview: "Linguist Louise Banks leads an elite team of investigators.",
  release_date: "2016-11-10",
  runtime_minutes: 116,
  number_of_seasons: null,
  original_language: "en",
  vote_average: 7.6,
  vote_count: 20104,
  poster_url: "https://image.tmdb.org/t/p/w342/poster.jpg",
  backdrop_url: null,
  genres: [
    { id: 7, slug: "drama", name: "Drama" },
    { id: 16, slug: "science-fiction", name: "Science Fiction" },
  ],
  cast: [
    { name: "Amy Adams", character: "Louise Banks", profile_url: null },
    { name: "Jeremy Renner", character: "Ian Donnelly", profile_url: null },
  ],
  directors: ["Denis Villeneuve"],
  creators: [],
  metadata_status: "fresh",
};

function showTitle(title: TitleDetail) {
  return mockApi({
    ...fakeLibrary([title.id]),
    "GET /api/auth/session": () => signedIn(),
    [`GET /api/titles/${String(title.id)}`]: () => Response.json(title),
  });
}

describe("title page", () => {
  it("shows a movie's details", async () => {
    showTitle(ARRIVAL);

    renderAt("/titles/42");

    expect(await screen.findByRole("heading", { level: 1, name: "Arrival" })).toBeInTheDocument();
    expect(screen.getByText("Movie · 2016 · 1h 56m · English")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Poster for Arrival" })).toHaveAttribute(
      "src",
      ARRIVAL.poster_url,
    );
    const genres = within(screen.getByRole("list", { name: "Genres" })).getAllByRole("listitem");
    expect(genres.map((genre) => genre.textContent)).toEqual(["Drama", "Science Fiction"]);
    expect(screen.getByText(/Directed by/).closest("p")).toHaveTextContent(
      "Directed by Denis Villeneuve",
    );
    expect(screen.getByText("Amy Adams")).toBeInTheDocument();
    expect(screen.getByText(/20,104 TMDB votes/)).toBeInTheDocument();
    // Fresh data: no "may be out of date" notice.
    expect(screen.queryByRole("status", { name: /out of date/ })).not.toBeInTheDocument();
  });

  it("shows a TV series with seasons and creators", async () => {
    showTitle({
      ...ARRIVAL,
      id: 7,
      media_type: "tv",
      name: "Kingdom",
      original_name: "킹덤",
      original_language: "ko",
      runtime_minutes: null,
      number_of_seasons: 2,
      directors: [],
      creators: ["Kim Eun-hee"],
      poster_url: null,
    });

    renderAt("/titles/7");

    expect(await screen.findByText("TV series · 2016 · 2 seasons · Korean")).toBeInTheDocument();
    expect(screen.getByText("킹덤")).toBeInTheDocument(); // original name, when it differs
    expect(screen.getByText(/Created by/).closest("p")).toHaveTextContent(
      "Created by Kim Eun-hee",
    );
    expect(screen.getByText("No poster")).toBeInTheDocument();
  });

  it.each([
    ["stale", "Some details may be out of date"],
    ["partial", "Showing basic information only"],
  ] as const)("explains %s data", async (status, notice) => {
    showTitle({ ...ARRIVAL, metadata_status: status });

    renderAt("/titles/42");

    expect(await screen.findByText(new RegExp(notice))).toBeInTheDocument();
  });

  it("shows 'not found' for an unknown title", async () => {
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/titles/999": () => apiError(404, "title_not_found", "There's no such title."),
    });

    renderAt("/titles/999");

    expect(
      await screen.findByRole("heading", { name: "Title not found" }),
    ).toBeInTheDocument();
  });

  it("doesn't even ask the API about ids that can't exist", async () => {
    const api = mockApi({ "GET /api/auth/session": () => signedIn() });

    renderAt("/titles/not-a-number");

    expect(
      await screen.findByRole("heading", { name: "Title not found" }),
    ).toBeInTheDocument();
    expect(callsTo(api, "GET /api/titles/not-a-number")).toHaveLength(0);
  });

  it("offers a retry when the API fails", async () => {
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/titles/42": () => Promise.reject(new TypeError("Failed to fetch")),
    });

    renderAt("/titles/42");

    // useTitle retries server trouble once (~1 s) before showing the error.
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach Screening Room");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("your library on the title page", () => {
  async function openArrival() {
    const api = showTitle(ARRIVAL);
    renderAt("/titles/42");
    const library = await screen.findByRole("region", { name: "Your library" });
    return { api, library, user: userEvent.setup() };
  }

  it("saves and unsaves, and marks not for me and undoes it", async () => {
    const { api, library, user } = await openArrival();
    const watchlist = within(library).getByRole("button", { name: "Watchlist" });
    const notForMe = within(library).getByRole("button", { name: "Not for me" });

    await user.click(watchlist);
    await waitFor(() => {
      expect(watchlist).toHaveAttribute("aria-pressed", "true");
    });
    await user.click(watchlist);
    await user.click(notForMe);
    await waitFor(() => {
      expect(notForMe).toHaveAttribute("aria-pressed", "true");
    });

    expect(watchlist).toHaveAttribute("aria-pressed", "false");
    expect(callsTo(api, "PUT /api/me/watchlist/42")).toHaveLength(1);
    expect(callsTo(api, "DELETE /api/me/watchlist/42")).toHaveLength(1);
    expect(callsTo(api, "PUT /api/me/not-for-me/42")).toHaveLength(1);
  });

  it("marks watched with an optional date, then again", async () => {
    const { api, library, user } = await openArrival();

    await user.type(within(library).getByLabelText("Date watched (optional)"), "2026-10-01");
    await user.click(within(library).getByRole("button", { name: "Mark watched" }));
    expect(await within(library).findByText("Watched once, last on 2026-10-01.")).toBeVisible();
    await user.click(within(library).getByRole("button", { name: "Watched again" }));

    expect(await within(library).findByText(/Watched 2 times/)).toBeVisible();
    expect(callsTo(api, "POST /api/me/history/42").map((call) => call.body)).toEqual([
      { watched_on: "2026-10-01" },
      { watched_on: null },
    ]);
  });

  it("asks before removing viewings", async () => {
    const { api, library, user } = await openArrival();
    await user.click(within(library).getByRole("button", { name: "Mark watched" }));
    await user.click(await within(library).findByRole("button", { name: "Remove from history" }));

    await user.click(within(library).getByRole("button", { name: "Cancel" }));
    expect(callsTo(api, "DELETE /api/me/history/42")).toHaveLength(0);

    await user.click(within(library).getByRole("button", { name: "Remove from history" }));
    await user.click(within(library).getByRole("button", { name: "Remove" }));

    expect(await within(library).findByRole("button", { name: "Mark watched" })).toBeVisible();
    expect(callsTo(api, "DELETE /api/me/history/42")).toHaveLength(1);
  });

  it("rates, which marks it watched, and clears the rating", async () => {
    const { api, library, user } = await openArrival();
    const stars = within(library).getByRole("group", { name: "Your rating" });

    await user.click(within(stars).getByRole("button", { name: "5 stars" }));
    expect(await within(library).findByText(/Watched once/)).toBeVisible();
    await user.click(within(library).getByRole("button", { name: "Clear rating" }));

    await waitFor(() => {
      expect(within(stars).getByRole("button", { name: "5 stars" })).toHaveAttribute(
        "aria-pressed",
        "false",
      );
    });
    expect(callsTo(api, "PUT /api/me/ratings/42")[0]?.body).toEqual({ value: 5 });
    expect(callsTo(api, "DELETE /api/me/ratings/42")).toHaveLength(1);
  });
});
