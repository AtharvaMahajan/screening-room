/** Keyboard use (M5d): skip link, and one tab stop per star rating. */
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StarRating } from "../components/StarRating";
import { mockApi, signedIn } from "../test/mockApi";
import { renderAt } from "../test/render";

describe("keyboard", () => {
  it("the first tab stop skips past the header to the page", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /api/auth/session": () => signedIn() });
    renderAt("/");
    await screen.findByRole("heading", { name: "Find something to watch" });

    await user.tab();
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(screen.getByRole("main")).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText("Either")).toHaveFocus(); // the page's first control
  });

  it("a star rating is one tab stop; arrows move, Enter rates", async () => {
    const user = userEvent.setup();
    const onRate = vi.fn();
    render(
      <>
        <button type="button">before</button>
        <StarRating value={null} onRate={onRate} />
        <button type="button">after</button>
      </>,
    );

    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "1 star" })).toHaveFocus();
    await user.keyboard("{ArrowRight}{ArrowRight}{ArrowRight}");
    expect(screen.getByRole("button", { name: "4 stars" })).toHaveFocus();
    expect(onRate).not.toHaveBeenCalled(); // moving doesn't rate
    await user.keyboard("{Enter}");
    expect(onRate).toHaveBeenCalledExactlyOnceWith(4);

    await user.keyboard("{End}{ArrowRight}");
    expect(screen.getByRole("button", { name: "5 stars" })).toHaveFocus(); // stops at the end
    await user.tab();
    expect(screen.getByRole("button", { name: "after" })).toHaveFocus(); // one stop, not five
  });

  it("tab returns to the current rating", async () => {
    const user = userEvent.setup();
    render(<StarRating value={3} onRate={vi.fn()} />);

    await user.tab();

    expect(screen.getByRole("button", { name: "3 stars" })).toHaveFocus();
  });
});
