// Adds DOM matchers such as toBeInTheDocument() to Vitest's expect.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { onSessionRefreshed, setCsrfToken } from "../api/client";

afterEach(() => {
  // Vitest globals are off, so Testing Library can't register this itself.
  cleanup();
  vi.unstubAllGlobals();
  // The API client keeps module-level state; don't let it leak between tests.
  setCsrfToken(null);
  onSessionRefreshed(null);
});
