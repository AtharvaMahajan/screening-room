/**
 * Automated accessibility checks with axe-core (M5d): missing labels, broken
 * ARIA, bad heading structure, unnamed buttons and links, and so on.
 *
 * Color contrast is off here: jsdom doesn't lay out or paint, so it can't
 * compute colors. That rule is checked in a real browser instead.
 */
import axe from "axe-core";

export async function accessibilityViolations(root: Element = document.body): Promise<string[]> {
  const results = await axe.run(root, { rules: { "color-contrast": { enabled: false } } });
  return results.violations.map(
    (violation) =>
      `${violation.id}: ${violation.help} -> ${violation.nodes
        .map((node) => node.target.join(" "))
        .join(", ")}`,
  );
}
