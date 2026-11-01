# M5d accessibility and responsive pass

2026-10-31. Target: WCAG 2.2 AA for the things we can check ourselves.

## How it was checked

| Check | How | Result |
|---|---|---|
| Automated rules (labels, ARIA, headings, names, lists, landmarks…) | axe-core 4.14 on every page, rendered with realistic data, in the component tests (`frontend/src/app/a11y.test.tsx`, 10 pages). Runs in CI with the rest of the tests | 0 violations. Proven able to fail: removing an image's alt text and invalid list markup were both caught |
| Color contrast | axe-core's contrast rule in real Chrome (jsdom can't compute colors), on Discover with results, a title page, Library, Your taste, Search and Account, **in both dark and light themes** (light rendered by removing the dark-mode media rules) | 2 problems found and fixed (below). 0 violations after |
| Keyboard | Real key presses in Chrome through Discover, with every focused element recorded | Logical order; a visible focus ring on every stop. 2 improvements made (below) |
| Phone width (390 px) | Every page in a 390 px frame, horizontal overflow measured | No page scrolls sideways (header fixed earlier in M4) |

## Problems found and fixed

| Problem | WCAG | Fix |
|---|---|---|
| White text on amber buttons, selected chips and the movie/TV switch: contrast 3.19:1 | 1.4.3 (4.5:1 for normal text) | Amber 700 behind white text: about 5.0:1. Focus outlines keep amber 600 (non-text needs 3:1) |
| Gray secondary text (years, dates, hints, counts) in dark mode: 4.12:1 | 1.4.3 | A lighter gray in dark mode only (`dark:text-stone-400`, about 7.9:1). Light mode already passed (4.77:1) |
| Each recommendation card had 10 tab stops, 5 of them stars: 50 presses to pass five cards | 2.1.1 (usability) | Star rating is one tab stop: arrows move between stars, Enter or Space rates. Moving never rates, since every rating is saved |
| 7 header stops before any page content | 2.4.1 Bypass blocks | "Skip to main content" link, first in the tab order, visible when focused |

Each fix has a test, and each test was checked by breaking the fix on purpose.

## Not done (worth doing before a wider launch)

- A pass with a real screen reader (NVDA on Windows, VoiceOver on macOS/iOS).
- The sign-in and register pages' contrast in a real browser (they need a signed-out browser; they use the same button and text styles that were checked).
- Moving focus to the new page's heading after client-side navigation, so screen reader users hear that the page changed.
