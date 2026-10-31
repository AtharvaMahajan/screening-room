import { screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ADA, apiError, callsTo, mockApi, signedIn, signedOut } from "../../test/mockApi";
import { renderAt } from "../../test/render";

async function deleteWith(password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Your password, to confirm"), password);
  await user.click(screen.getByRole("button", { name: "Delete my account and all its data" }));
}

describe("account page", () => {
  it("is reached from the name in the header", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /api/auth/session": () => signedIn() });
    const { router } = renderAt("/search");

    await user.click(await screen.findByRole("link", { name: ADA.display_name }));

    expect(router.state.location.pathname).toBe("/account");
    expect(screen.getByText(`Signed in as ${ADA.email} (${ADA.display_name})`)).toBeVisible();
  });

  it("deletes the account with the password, then says goodbye signed out", async () => {
    let deleted = false;
    const api = mockApi({
      "GET /api/auth/session": () => (deleted ? signedOut() : signedIn()),
      "DELETE /api/me": () => {
        deleted = true;
        return signedOut();
      },
    });
    const { router } = renderAt("/account");

    await deleteWith("correct horse battery");

    expect(await screen.findByText("Your account and all its data were deleted.")).toBeVisible();
    // Not bounced to "sign in to get back to /account" by the guard.
    expect(router.state.location.pathname).toBe("/goodbye");
    // Signed out: the header no longer shows the user.
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: ADA.display_name })).not.toBeInTheDocument();
    });
    const [call] = callsTo(api, "DELETE /api/me");
    expect(call?.body).toEqual({ password: "correct horse battery" });
    expect(call?.headers["X-CSRF-Token"]).toBe("signed-in-token");
  });

  it("explains a wrong password and stays signed in", async () => {
    mockApi({
      "GET /api/auth/session": () => signedIn(),
      "DELETE /api/me": () => apiError(403, "wrong_password", "That password isn't right."),
    });
    const { router } = renderAt("/account");

    await deleteWith("oops");

    expect(await screen.findByText("That password isn't right.")).toBeVisible();
    expect(screen.getByLabelText("Your password, to confirm")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(router.state.location.pathname).toBe("/account");
  });

  it("can't be submitted without a password", async () => {
    mockApi({ "GET /api/auth/session": () => signedIn() });
    renderAt("/account");

    expect(
      await screen.findByRole("button", { name: "Delete my account and all its data" }),
    ).toBeDisabled();
  });
});
