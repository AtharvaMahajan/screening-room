/** Sign in, register, sign out and the route guard, against a mocked API. */
import { screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  ADA,
  apiError,
  callsTo,
  emptyTasteProfile,
  mockApi,
  signedIn,
  signedOut,
} from "../../test/mockApi";
import { renderAt } from "../../test/render";

async function fillSignIn(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

// --- Route guard ------------------------------------------------------------------------

describe("route guard", () => {
  it("sends a signed-out visitor from home to sign-in", async () => {
    mockApi({ "GET /api/auth/session": signedOut });

    const { router } = renderAt("/");

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/sign-in");
  });

  it("shows an error with a retry when the session can't be loaded", async () => {
    mockApi({ "GET /api/auth/session": () => Promise.reject(new TypeError("Failed to fetch")) });

    renderAt("/");

    // useSession retries once (after ~1 s) before giving up; the 5 s wait in
    // test/setup.ts covers that.
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach Screening Room");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("sends a signed-in user away from the sign-in page", async () => {
    mockApi({ "GET /api/auth/session": () => signedIn() });

    renderAt("/sign-in");

    expect(await screen.findByRole("heading", { name: "Welcome, Ada" })).toBeInTheDocument();
  });
});

// --- Sign in ----------------------------------------------------------------------------

describe("sign in", () => {
  it("signs in and lands on home", async () => {
    const api = mockApi({
      "GET /api/auth/session": signedOut,
      "POST /api/auth/login": () => signedIn(),
    });
    renderAt("/");

    await fillSignIn("ada@example.com", "correct horse battery");

    expect(await screen.findByRole("heading", { name: "Welcome, Ada" })).toBeInTheDocument();
    const [login] = callsTo(api, "POST /api/auth/login");
    expect(login?.body).toEqual({ email: "ada@example.com", password: "correct horse battery" });
    expect(login?.headers["X-CSRF-Token"]).toBe("anon-token"); // from the session bootstrap
  });

  it("returns to the page the user was going to", async () => {
    mockApi({
      "GET /api/auth/session": signedOut,
      "POST /api/auth/login": () => signedIn(),
    });
    const { router } = renderAt("/sign-in?next=%2Fsomewhere%3Fx%3D1");

    await fillSignIn("ada@example.com", "correct horse battery");

    await waitFor(() => {
      expect(router.state.location.pathname + router.state.location.search).toBe(
        "/somewhere?x=1",
      );
    });
  });

  it("ignores a next parameter that points to another site", async () => {
    mockApi({
      "GET /api/auth/session": signedOut,
      "POST /api/auth/login": () => signedIn(),
    });
    const { router } = renderAt("/sign-in?next=%2F%2Fevil.example");

    await fillSignIn("ada@example.com", "correct horse battery");

    expect(await screen.findByRole("heading", { name: "Welcome, Ada" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("shows the server's message for wrong credentials", async () => {
    mockApi({
      "GET /api/auth/session": signedOut,
      "POST /api/auth/login": () =>
        apiError(401, "invalid_credentials", "Invalid email or password."),
    });
    renderAt("/sign-in");

    await fillSignIn("ada@example.com", "wrong password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
  });

  it("validates in the browser before sending anything", async () => {
    const api = mockApi({ "GET /api/auth/session": signedOut });
    renderAt("/sign-in");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(callsTo(api, "POST /api/auth/login")).toHaveLength(0);
  });
});

// --- Register ---------------------------------------------------------------------------

describe("register", () => {
  async function fillRegister(password = "correct horse battery") {
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Name (optional)"), "Ada");
    await user.type(screen.getByLabelText("Password"), password);
    await user.click(screen.getByRole("button", { name: "Create account" }));
  }

  it("creates the account, signs in and goes on to onboarding", async () => {
    const api = mockApi({
      "GET /api/auth/session": signedOut,
      "POST /api/auth/register": () => signedIn(),
      ...emptyTasteProfile,
    });
    const { router } = renderAt("/register");

    await fillRegister();

    expect(
      await screen.findByRole("heading", { name: "What do you like to watch?" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/welcome");
    expect(callsTo(api, "POST /api/auth/register")[0]?.body).toEqual({
      email: "ada@example.com",
      password: "correct horse battery",
      display_name: "Ada",
    });
  });

  it("checks password length in the browser", async () => {
    const api = mockApi({ "GET /api/auth/session": signedOut });
    renderAt("/register");

    await fillRegister("short");

    expect(await screen.findByText("Use at least 10 characters.")).toBeInTheDocument();
    expect(callsTo(api, "POST /api/auth/register")).toHaveLength(0);
  });

  it("shows a taken email next to the email field", async () => {
    mockApi({
      "GET /api/auth/session": signedOut,
      "POST /api/auth/register": () =>
        apiError(409, "email_unavailable", "This email can't be used."),
    });
    renderAt("/register");

    await fillRegister();

    expect(await screen.findByText("This email can't be used.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows server-side field errors next to their fields", async () => {
    mockApi({
      "GET /api/auth/session": signedOut,
      "POST /api/auth/register": () =>
        apiError(422, "validation_failed", "The request is invalid.", [
          { field: "body.password", message: "Password is too common." },
        ]),
    });
    renderAt("/register");

    await fillRegister();

    expect(await screen.findByText("Password is too common.")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows a general message when the server can't be reached", async () => {
    mockApi({
      "GET /api/auth/session": signedOut,
      "POST /api/auth/register": () => Promise.reject(new TypeError("Failed to fetch")),
    });
    renderAt("/register");

    await fillRegister();

    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach Screening Room");
  });
});

// --- Sign out ---------------------------------------------------------------------------

describe("sign out", () => {
  it("signs out with the session's CSRF token and goes to sign-in", async () => {
    const api = mockApi({
      "GET /api/auth/session": () => signedIn(),
      "POST /api/auth/logout": signedOut,
    });
    const { router } = renderAt("/");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/sign-in");
    expect(callsTo(api, "POST /api/auth/logout")[0]?.headers["X-CSRF-Token"]).toBe(
      "signed-in-token",
    );
    expect(screen.queryByText(ADA.display_name)).not.toBeInTheDocument();
  });
});
