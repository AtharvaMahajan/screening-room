import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { apiError, callsTo, emptyTasteProfile, mockApi, signedIn } from "../../test/mockApi";
import { renderAt } from "../../test/render";
import type { TitleCard } from "../titles/api";
import type { Favorites, Preferences } from "./api";

const DRAMA = 7;
const SCIFI = 16;

const card = (id: number, name: string, year = 2016): TitleCard => ({
  id,
  media_type: "movie",
  name,
  year,
  poster_url: null,
});
const ARRIVAL = card(42, "Arrival");
const DUNE = card(43, "Dune", 2021);

const json = (body: unknown) => () => Response.json(body);

/** A preferences endpoint that remembers what was PUT, like the real one. */
function preferencesApi(initial: Preferences = { liked_genre_ids: [], avoided_genre_ids: [] }) {
  let saved = initial;
  return {
    "GET /api/me/preferences": () => Response.json(saved),
    "PUT /api/me/preferences": (body: unknown) => {
      saved = body as Preferences;
      return Response.json(saved);
    },
  };
}

function genreButton(group: RegExp, name: string) {
  return within(screen.getByRole("group", { name: group })).getByRole("button", { name });
}

describe("onboarding and taste editing", () => {
  it("welcomes new users and lets them skip", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /api/auth/session": () => signedIn(), ...emptyTasteProfile });
    const { router } = renderAt("/welcome");

    expect(
      await screen.findByRole("heading", { name: "What do you like to watch?" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Skip for now" }));

    expect(router.state.location.pathname).toBe("/");
  });

  it("saves each genre choice, and liking a genre clears avoiding it", async () => {
    const user = userEvent.setup();
    const api = mockApi({
      "GET /api/auth/session": () => signedIn(),
      ...emptyTasteProfile,
      ...preferencesApi({ liked_genre_ids: [], avoided_genre_ids: [DRAMA] }),
      [`GET /api/titles?limit=12&genre_ids=${String(SCIFI)}`]: json([]),
      [`GET /api/titles?limit=12&genre_ids=${String(SCIFI)}&genre_ids=${String(DRAMA)}`]: json(
        [],
      ),
    });
    renderAt("/taste");

    await user.click(await screenFind(() => genreButton(/like/, "Science Fiction")));
    await user.click(genreButton(/like/, "Drama"));

    await waitFor(() => {
      expect(callsTo(api, "PUT /api/me/preferences").map((call) => call.body)).toEqual([
        { liked_genre_ids: [SCIFI], avoided_genre_ids: [DRAMA] },
        { liked_genre_ids: [SCIFI, DRAMA], avoided_genre_ids: [] },
      ]);
    });
    expect(genreButton(/like/, "Drama")).toHaveAttribute("aria-pressed", "true");
    expect(genreButton(/avoid/, "Drama")).toHaveAttribute("aria-pressed", "false");
  });

  it("sends saves one at a time, so the last click wins", async () => {
    const user = userEvent.setup();
    let releaseFirst = () => {};
    const firstSave = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    const putsStarted: unknown[] = [];
    const api = mockApi({
      "GET /api/auth/session": () => signedIn(),
      ...emptyTasteProfile,
      "PUT /api/me/preferences": async (body) => {
        putsStarted.push(body);
        if (putsStarted.length === 1) {
          await firstSave; // the first save is slow
        }
        return Response.json(body);
      },
    });
    renderAt("/taste");

    await user.click(await screenFind(() => genreButton(/like/, "Drama")));
    await user.click(genreButton(/like/, "Drama")); // changed my mind

    // The second save waits for the first one instead of racing it.
    expect(putsStarted).toHaveLength(1);
    releaseFirst();
    await waitFor(() => {
      expect(putsStarted).toHaveLength(2);
    });
    expect(callsTo(api, "PUT /api/me/preferences").at(-1)?.body).toEqual({
      liked_genre_ids: [],
      avoided_genre_ids: [],
    });
  });

  it("shows a failed save and puts back what the server has", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      ...emptyTasteProfile,
      "PUT /api/me/preferences": () => apiError(500, "internal_error", "Boom"),
    });
    renderAt("/taste");

    await user.click(await screenFind(() => genreButton(/like/, "Drama")));

    expect(await screen.findByText(/Couldn't save your genres/)).toBeInTheDocument();
    await waitFor(() => {
      expect(genreButton(/like/, "Drama")).toHaveAttribute("aria-pressed", "false");
    });
  });

  it("suggests well-known titles in the genres you like", async () => {
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      ...emptyTasteProfile,
      ...preferencesApi({ liked_genre_ids: [SCIFI], avoided_genre_ids: [] }),
      [`GET /api/titles?limit=12&genre_ids=${String(SCIFI)}`]: json([ARRIVAL, DUNE]),
    });
    renderAt("/taste");

    expect(
      await screen.findByRole("heading", { name: "Popular in your genres" }),
    ).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Pick Arrival, 2016" })).toBeEnabled();
  });

  it("searches, picks and removes favorites", async () => {
    const user = userEvent.setup();
    const withArrival: Favorites = { favorites: [ARRIVAL], max_favorites: 10 };
    const api = mockApi({
      "GET /api/auth/session": () => signedIn(),
      ...emptyTasteProfile,
      "GET /api/titles?limit=12&q=arr": json([ARRIVAL]),
      "POST /api/me/favorites": json(withArrival),
      [`DELETE /api/me/favorites/${String(ARRIVAL.id)}`]: json({
        favorites: [],
        max_favorites: 10,
      }),
    });
    renderAt("/taste");

    await user.type(await screen.findByRole("searchbox"), "arr");
    await user.click(await screen.findByRole("button", { name: "Pick Arrival, 2016" }));

    expect(
      await screen.findByRole("button", { name: "Arrival, 2016 (picked)" }),
    ).toBeDisabled();
    expect(callsTo(api, "POST /api/me/favorites")[0]?.body).toEqual({ title_id: ARRIVAL.id });
    expect(screen.getByText("1 of 10")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove Arrival" }));

    expect(await screen.findByText("0 of 10")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pick Arrival, 2016" })).toBeEnabled();
  });

  it("stops picking at the limit", async () => {
    const ten = Array.from({ length: 10 }, (_, i) => card(100 + i, `Film ${String(i)}`));
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      ...emptyTasteProfile,
      "GET /api/me/favorites": json({ favorites: ten, max_favorites: 10 }),
      "GET /api/titles?limit=12": json([DUNE]),
    });
    renderAt("/taste");

    expect(await screen.findByRole("button", { name: "Pick Dune, 2021" })).toBeDisabled();
    expect(screen.getByText(/picked the maximum/)).toBeInTheDocument();
  });
});

/** Wait for the page to load, then get an element. */
async function screenFind<T>(get: () => T): Promise<T> {
  await screen.findByRole("heading", { level: 2, name: "1. Genres" });
  return get();
}
