// Adds DOM matchers such as toBeInTheDocument() to Vitest's expect.
import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { onSessionRefreshed, setCsrfToken } from "../api/client";

// findBy*/waitFor resolve as soon as the element appears; this only bounds how
// long a genuinely missing element is waited for. The 1 s default, and later
// 5 s, made the first test in a file fail at random while many files start at
// once on a busy machine (and CI runners are often slower still).
configure({ asyncUtilTimeout: 10_000 });

// jsdom doesn't lay pages out, so it has no scrollIntoView. Spy on it to check calls.
Element.prototype.scrollIntoView = () => {};

afterEach(() => {
  // Vitest globals are off, so Testing Library can't register this itself.
  cleanup();
  vi.unstubAllGlobals();
  // The API client keeps module-level state; don't let it leak between tests.
  setCsrfToken(null);
  onSessionRefreshed(null);
});
