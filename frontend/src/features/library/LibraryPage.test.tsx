import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeLibrary } from "../../test/fakeLibrary";
import { callsTo, mockApi, signedIn } from "../../test/mockApi";
import { renderAt } from "../../test/render";
import type { TitleCard } from "../titles/api";
import type { NotForMeItem, RatedItem, Viewing, WatchlistItem } from "./api";

const card = (id: number, name: string, media_type: "movie" | "tv" = "movie"): TitleCard => ({
  id,
  media_type,
  name,
  year: 2016,
  poster_url: null,
});
const ARRIVAL = card(42, "Arrival");
const DARK = card(43, "Dark", "tv");
const AT = "2026-10-30T12:00:00Z"; // noon UTC: still Oct 30 in nearly every time zone

const json = (body: unknown) => () => Response.json(body);

function rowNames() {
  return screen
    .queryAllByRole("listitem")
    .map((item) => within(item).getAllByRole("link").at(-1)?.textContent);
}

describe("library page", () => {
  it("opens on the watchlist, and removes from it", async () => {
    const user = userEvent.setup();
    let watchlist: WatchlistItem[] = [
      { title: ARRIVAL, added_at: AT },
      { title: DARK, added_at: AT },
    ];
    const library = fakeLibrary([42, 43]);
    const api = mockApi({
      "GET /api/auth/session": () => signedIn(),
      ...library,
      "GET /api/me/watchlist": () => Response.json(watchlist),
      "DELETE /api/me/watchlist/42": (body) => {
        watchlist = watchlist.filter((item) => item.title.id !== 42);
        return library["DELETE /api/me/watchlist/42"]?.(body) ?? json({})();
      },
    });
    renderAt("/library");

    expect(await screen.findByText("Arrival")).toBeInTheDocument();
    expect(rowNames()).toEqual(["Arrival", "Dark"]);
    expect(screen.getAllByText(/Saved Oct 30, 2026/)).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Remove Arrival" }));

    await waitFor(() => {
      expect(rowNames()).toEqual(["Dark"]); // the list refetched after the change
    });
    expect(callsTo(api, "GET /api/me/watchlist")).toHaveLength(2);
  });

  it("switches lists and filters by media type, in the URL", async () => {
    const user = userEvent.setup();
    const ratings: RatedItem[] = [{ title: DARK, value: 4, rated_at: AT }];
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/me/watchlist": json([]),
      "GET /api/me/ratings": json(ratings),
      "GET /api/me/ratings?media_type=tv": json(ratings),
      "GET /api/me/ratings?media_type=movie": json([]),
    });
    const { router } = renderAt("/library");

    await user.click(await screen.findByRole("button", { name: "Ratings" }));
    expect(await screen.findByLabelText("4 out of 5 stars")).toHaveTextContent("★★★★☆");
    await user.click(screen.getByRole("button", { name: "Movies" }));

    expect(await screen.findByText("Nothing here of that kind.")).toBeInTheDocument();
    expect(router.state.location.search).toBe("?tab=ratings&type=movie");
    await user.click(screen.getByRole("button", { name: "TV" }));
    expect(await screen.findByText("Dark")).toBeInTheDocument();
  });

  it("opens straight to a list from a link", async () => {
    const history: Viewing[] = [
      { id: 2, title: ARRIVAL, watched_on: null, created_at: AT },
      { id: 1, title: ARRIVAL, watched_on: "2024-02-03", created_at: AT },
    ];
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      "GET /api/me/history?media_type=movie": json(history),
    });
    renderAt("/library?tab=history&type=movie");

    expect(await screen.findByText(/Watched 2024-02-03/)).toBeInTheDocument();
    expect(screen.getByText(/Marked watched Oct 30, 2026/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "History" })).toHaveAttribute("aria-pressed", "true");
  });

  it("undoes a not for me", async () => {
    const user = userEvent.setup();
    let dismissed: NotForMeItem[] = [{ title: ARRIVAL, marked_at: AT }];
    const library = fakeLibrary([42]);
    const api = mockApi({
      "GET /api/auth/session": () => signedIn(),
      ...library,
      "GET /api/me/not-for-me": () => Response.json(dismissed),
      "DELETE /api/me/not-for-me/42": (body) => {
        dismissed = [];
        return library["DELETE /api/me/not-for-me/42"]?.(body) ?? json({})();
      },
    });
    renderAt("/library?tab=not-for-me");

    await user.click(await screen.findByRole("button", { name: "Undo not for me for Arrival" }));

    expect(await screen.findByText(/You haven't turned anything down/)).toBeInTheDocument();
    expect(callsTo(api, "DELETE /api/me/not-for-me/42")).toHaveLength(1);
  });

  it("is linked from the header", async () => {
    mockApi({ "GET /api/auth/session": () => signedIn(), "GET /api/me/watchlist": json([]) });
    const user = userEvent.setup();
    const { router } = renderAt("/taste");

    await user.click(await screen.findByRole("link", { name: "Library" }));

    expect(router.state.location.pathname).toBe("/library");
    expect(await screen.findByText(/Nothing saved yet/)).toBeInTheDocument();
  });
});
