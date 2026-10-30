import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mockApi, signedIn, signedOut } from "../test/mockApi";
import { renderAt } from "../test/render";

describe("routes", () => {
  it("renders the signed-in home page inside the layout", async () => {
    mockApi({ "GET /api/auth/session": () => signedIn() });

    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Welcome, Ada" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Screening Room" })).toBeInTheDocument();
  });

  it("renders a not-found page for unknown paths, signed in or not", () => {
    mockApi({ "GET /api/auth/session": signedOut });

    renderAt("/no-such-page");

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
