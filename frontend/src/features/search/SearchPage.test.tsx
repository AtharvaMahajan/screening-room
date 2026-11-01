import { screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { callsTo, emptyTasteProfile, mockApi, signedIn } from "../../test/mockApi";
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

  it("asks again for one type as soon as the type changes", async () => {
    const user = userEvent.setup();
    const api = mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/search?q=dune": tmdb(card(1, "Dune"), card(2, "Dune", "tv")),
      "GET /api/search?q=dune&media_type=tv": tmdb(card(2, "Dune", "tv"), card(3, "Dune: Prophecy", "tv")),
    });
    const { router } = renderAt("/search?q=dune");
    await screen.findByText("Movie · 2016");

    await user.click(
      within(screen.getByRole("group", { name: "Type" })).getByRole("button", { name: "TV" }),
    );

    expect(await screen.findByText("Dune: Prophecy")).toBeInTheDocument();
    expect(screen.queryByText("Movie · 2016")).not.toBeInTheDocument();
    expect(new URLSearchParams(router.state.location.search).get("type")).toBe("tv");
    expect(callsTo(api, "GET /api/search?q=dune&media_type=tv")).toHaveLength(1);
  });

  it("narrows the results to a decade instantly, without asking again", async () => {
    const user = userEvent.setup();
    const api = mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/search?q=dune": tmdb(
        { ...card(1, "Dune"), year: 2021 },
        { ...card(2, "Dune (old)"), year: 1984 },
      ),
    });
    renderAt("/search?q=dune");
    await screen.findByText("Dune (old)");

    await user.click(
      within(screen.getByRole("group", { name: "Released" })).getByRole("button", {
        name: "Before 1990",
      }),
    );

    expect(screen.queryByText("Dune")).not.toBeInTheDocument();
    expect(screen.getByText("Dune (old)")).toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 2 results.")).toBeInTheDocument();
    expect(callsTo(api, "GET /api/search?q=dune")).toHaveLength(1);
  });

  it("opens with filters from a link", async () => {
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/search?q=dark&media_type=tv": tmdb({ ...card(7, "Dark", "tv"), year: 2017 }),
    });
    renderAt("/search?q=dark&type=tv&released=2010s");

    expect(await screen.findByText("Dark")).toBeInTheDocument();
    const pressed = screen
      .getAllByRole("button", { pressed: true })
      .map((button) => button.textContent);
    expect(pressed).toEqual(["TV", "2010s"]);
  });

  it("is linked from the header", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /api/auth/session": () => signedIn(), ...emptyTasteProfile });
    const { router } = renderAt("/taste");

    await user.click(await screen.findByRole("link", { name: "Search" }));

    expect(router.state.location.pathname).toBe("/search");
  });
});
