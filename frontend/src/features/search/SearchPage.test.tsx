import { screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { emptyTasteProfile, mockApi, signedIn } from "../../test/mockApi";
import { renderAt } from "../../test/render";
import type { SearchResults, TitleCard } from "../titles/api";

const card = (id: number, name: string, media_type: "movie" | "tv" = "movie"): TitleCard => ({
  id,
  media_type,
  name,
  year: 2016,
  poster_url: null,
});
const tmdb = (...results: TitleCard[]) => () =>
  Response.json({ source: "tmdb", results } satisfies SearchResults);

describe("search", () => {
  it("searches as you type, keeps the query in the URL, and links to titles", async () => {
    const user = userEvent.setup();
    const api = mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/search?q=arrival": tmdb(card(42, "Arrival"), card(43, "The Arrival")),
    });
    const { router } = renderAt("/search");

    await user.type(await screen.findByLabelText("Movie or TV show"), "arrival");

    const results = await screen.findByRole("region", { name: "Results for arrival" });
    expect(within(results).getByRole("link", { name: /^Arrival/ })).toHaveAttribute(
      "href",
      "/titles/42",
    );
    expect(router.state.location.search).toBe("?q=arrival");
    // One request for the whole word, not one per keystroke ("a", "ar", ...).
    const searches = api.mock.calls.filter(
      ([url]) => typeof url === "string" && url.startsWith("/api/search"), // the client sends strings
    );
    expect(searches).toHaveLength(1);
  });

  it("opens with results from a link", async () => {
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/search?q=dark": tmdb(card(7, "Dark", "tv")),
    });
    renderAt("/search?q=dark");

    expect(await screen.findByText("TV · 2016")).toBeInTheDocument();
    expect(screen.getByLabelText("Movie or TV show")).toHaveValue("dark");
  });

  it("says when TMDB couldn't be reached and only our catalog was searched", async () => {
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/search?q=dune": () =>
        Response.json({ source: "local", results: [card(9, "Dune")] } satisfies SearchResults),
    });
    renderAt("/search?q=dune");

    const notice = await screen.findByText(/TMDB search isn't available right now/);
    expect(notice).toHaveAttribute("role", "status");
    expect(screen.getByText("Dune")).toBeInTheDocument();
  });

  it("says when nothing matches", async () => {
    mockApi({ "GET /api/auth/session": () => signedIn(), "GET /api/search?q=zzz": tmdb() });
    renderAt("/search?q=zzz");

    expect(await screen.findByText("No movies or shows match “zzz”.")).toBeInTheDocument();
  });

  it("is linked from the header", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /api/auth/session": () => signedIn(), ...emptyTasteProfile });
    const { router } = renderAt("/taste");

    await user.click(await screen.findByRole("link", { name: "Search" }));

    expect(router.state.location.pathname).toBe("/search");
  });
});
