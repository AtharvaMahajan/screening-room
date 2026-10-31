import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { apiError, callsTo, mockApi, signedIn, signedOut } from "../../test/mockApi";
import { renderAt } from "../../test/render";
import type { Recommendation, Recommendations } from "./api";

const DRAMA = 7;
const RECOMMEND = "POST /api/recommendations";

let nextResultId = 1;
function result(titleId: number, name: string, reasons: string[] = ["Popular on TMDB"]) {
  return {
    result_id: nextResultId++,
    rank: 1,
    title: {
      id: titleId,
      media_type: "movie",
      name,
      year: 2016,
      poster_url: null,
      overview: `${name} overview.`,
      runtime_minutes: 116,
    },
    reasons: reasons.map((text) => ({ type: "pool_source", text, anchor_title_id: null })),
  } satisfies Recommendation;
}

const shortlist = (results: Recommendation[], extra: Partial<Recommendations> = {}) =>
  Response.json({
    request_id: 1,
    cold_start: false,
    notices: [],
    results: results.map((r, i) => ({ ...r, rank: i + 1 })),
    ...extra,
  } satisfies Recommendations);

const FIRST_FIVE = [
  result(1, "Dune", ["Because you picked Arrival", "Fits your time: 2h 35m"]),
  result(2, "Contact"),
  result(3, "Moon"),
  result(4, "Solaris"),
  result(5, "Gravity"),
];
const NEXT_FIVE = [6, 7, 8, 9, 10].map((id) => result(id, `Film ${String(id)}`));

function discover(routes: Record<string, (body: unknown) => Response> = {}) {
  return mockApi({
    "GET /api/auth/session": () => signedIn(),
    "GET /api/genres": () => Response.json([{ id: DRAMA, slug: "drama", name: "Drama" }]),
    [RECOMMEND]: () => shortlist(FIRST_FIVE),
    ...routes,
  });
}

async function findSomething() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Find something" }));
  await screen.findByRole("heading", { level: 2, name: "Dune" });
  return user;
}

function shownTitles() {
  return screen.queryAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
}

describe("discover", () => {
  it("asks with no context at all and shows explained results", async () => {
    const api = discover();
    renderAt("/");

    await findSomething();

    expect(callsTo(api, RECOMMEND)[0]?.body).toEqual({
      media_type: "any",
      genre_ids: [],
      max_runtime_minutes: null,
      exclude_title_ids: [],
      limit: 5,
    });
    expect(shownTitles()).toEqual(["Dune", "Contact", "Moon", "Solaris", "Gravity"]);
    const why = within(screen.getByRole("list", { name: "Why Dune" })).getAllByRole("listitem");
    expect(why.map((item) => item.textContent)).toEqual([
      "✦Because you picked Arrival",
      "✦Fits your time: 2h 35m",
    ]);
    expect(screen.getByRole("link", { name: "Dune" })).toHaveAttribute("href", "/titles/1");
    expect(screen.getAllByText("Movie · 2016 · 1h 56m")).toHaveLength(5);
  });

  it("sends the chosen context", async () => {
    const user = userEvent.setup();
    const api = discover();
    renderAt("/");

    await user.click(await screen.findByLabelText("Movie"));
    await user.selectOptions(screen.getByLabelText("Genre"), "Drama");
    await user.selectOptions(screen.getByLabelText("Time you have"), "Up to 2h");
    await findSomething();

    expect(callsTo(api, RECOMMEND)[0]?.body).toMatchObject({
      media_type: "movie",
      genre_ids: [DRAMA],
      max_runtime_minutes: 120,
    });
  });

  it("doesn't send a runtime limit for TV, which it doesn't apply to", async () => {
    const user = userEvent.setup();
    const api = discover();
    renderAt("/");

    await user.selectOptions(await screen.findByLabelText("Time you have"), "Up to 1h 30m");
    await user.click(screen.getByLabelText("TV"));
    await findSomething();

    expect(screen.getByLabelText("Time you have")).toBeDisabled();
    expect(screen.getByLabelText("Time you have")).toHaveAccessibleDescription(
      "Applies to movies only.",
    );
    expect(callsTo(api, RECOMMEND)[0]?.body).toMatchObject({
      media_type: "tv",
      max_runtime_minutes: null,
    });
  });

  it("skips a title, then shows more without repeating anything already shown", async () => {
    let call = 0;
    const api = discover({
      [RECOMMEND]: () => shortlist(call++ === 0 ? FIRST_FIVE : NEXT_FIVE),
    });
    const scrollIntoView = vi.spyOn(Element.prototype, "scrollIntoView");
    renderAt("/");
    const user = await findSomething();

    await user.click(screen.getByRole("button", { name: "Skip Moon" }));
    expect(shownTitles()).toEqual(["Dune", "Contact", "Solaris", "Gravity"]);

    await user.click(screen.getByRole("button", { name: "Show me more" }));

    await screen.findByRole("heading", { level: 2, name: "Film 6" });
    expect(callsTo(api, RECOMMEND)[1]?.body).toMatchObject({
      exclude_title_ids: [1, 2, 3, 4, 5], // skipped or not, all were shown
    });
    expect(shownTitles()).toEqual(["Film 6", "Film 7", "Film 8", "Film 9", "Film 10"]);
    // The button was at the bottom: focus moves to the top of the new list.
    expect(screen.getByRole("region", { name: "Recommendations" })).toHaveFocus();
    expect(scrollIntoView).toHaveBeenCalledOnce();
    scrollIntoView.mockRestore();
  });

  it("keeps the shortlist after opening a title and coming back", async () => {
    const api = discover({
      "GET /api/titles/1": () => apiError(404, "title_not_found", "No such title."),
    });
    const { router } = renderAt("/");
    const user = await findSomething();

    await user.click(screen.getByRole("link", { name: "Dune" }));
    await screen.findByRole("heading", { name: "Title not found" });
    await router.navigate(-1);

    expect(await screen.findByRole("heading", { level: 2, name: "Dune" })).toBeInTheDocument();
    expect(callsTo(api, RECOMMEND)).toHaveLength(1); // shown again, not requested again
  });

  it("explains a cold start and a short list, and offers no more", async () => {
    discover({
      [RECOMMEND]: () =>
        shortlist(FIRST_FIVE.slice(0, 2), {
          cold_start: true,
          notices: [
            { code: "cold_start", text: "Recommendations improve as you pick favorites." },
            { code: "few_results", text: "Only 2 titles match. Try a longer runtime." },
          ],
        }),
    });
    renderAt("/");

    await findSomething();

    const recommendations = screen.getByRole("region", { name: "Recommendations" });
    const [coldStart, fewResults] = within(recommendations).getAllByRole("status");
    expect(coldStart).toHaveTextContent(
      "Recommendations improve as you pick favorites. Pick some favorites",
    );
    expect(fewResults).toHaveTextContent("Only 2 titles match. Try a longer runtime.");
    expect(screen.getByRole("link", { name: "Pick some favorites" })).toHaveAttribute(
      "href",
      "/taste",
    );
    expect(screen.queryByRole("button", { name: "Show me more" })).not.toBeInTheDocument();
  });

  it("shows an error and lets you try again", async () => {
    discover({ [RECOMMEND]: () => apiError(500, "internal_error", "Boom") });
    renderAt("/");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Find something" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByRole("button", { name: "Find something" })).toBeEnabled();
  });

  it("forgets the shortlist when you sign out", async () => {
    let signedInNow = true;
    discover({
      "GET /api/auth/session": () => (signedInNow ? signedIn() : signedOut()),
      "POST /api/auth/logout": () => {
        signedInNow = false;
        return signedOut();
      },
      "POST /api/auth/login": () =>
        signedIn({ email: "grace@example.com", display_name: "Grace" }),
    });
    renderAt("/");
    const user = await findSomething();

    await user.click(screen.getByRole("button", { name: "Sign out" }));
    await user.type(await screen.findByLabelText("Email"), "grace@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Grace")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Find something to watch" })).toBeVisible();
    });
    expect(shownTitles()).toEqual([]); // nothing left over from the previous user
  });
});
