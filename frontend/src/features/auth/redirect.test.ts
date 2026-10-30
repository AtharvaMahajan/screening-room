import { describe, expect, it } from "vitest";

import { safeNextPath, signInPath } from "./redirect";

describe("safeNextPath", () => {
  it.each([
    ["/", "/"],
    ["/library", "/library"],
    ["/titles/42?tab=cast", "/titles/42?tab=cast"],
  ])("keeps the in-app path %s", (next, expected) => {
    expect(safeNextPath(next)).toBe(expected);
  });

  it.each([
    [null],
    [""],
    ["https://evil.example"],
    ["//evil.example"], // protocol-relative: another host
    ["/\\evil.example"], // browsers treat a backslash like a slash
    ["javascript:alert(1)"],
  ])("falls back to / for %s", (next) => {
    expect(safeNextPath(next)).toBe("/");
  });
});

describe("signInPath", () => {
  it("adds the return path, except for home", () => {
    expect(signInPath("/")).toBe("/sign-in");
    expect(signInPath("/library?x=1")).toBe("/sign-in?next=%2Flibrary%3Fx%3D1");
  });
});
