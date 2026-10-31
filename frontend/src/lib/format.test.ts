import { describe, expect, it } from "vitest";

import { formatRuntime, languageName, yearOf } from "./format";

describe("format", () => {
  it.each([
    [116, "1h 56m"],
    [45, "45m"],
    [120, "2h"],
  ])("formatRuntime(%i) is %s", (minutes, expected) => {
    expect(formatRuntime(minutes)).toBe(expected);
  });

  it("yearOf takes the year from an ISO date", () => {
    expect(yearOf("2016-11-10")).toBe("2016");
  });

  it("languageName names known languages and falls back to the code", () => {
    expect(languageName("ko")).toBe("Korean");
    expect(languageName("xx")).toBe("xx");
  });
});
