// @vitest-environment jsdom
/**
 * D-0091 guards (a): the link component (G2, G3) and the chart tick (G8).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CountryAxisTick } from "./CountryAxisTick";
import { CountryLink } from "./CountryLink";

beforeEach(() => { window.location.hash = ""; });
afterEach(() => { cleanup(); });

describe("G2: an unknown key renders no link, and says so", () => {
  for (const bad of ["RUSSIA", "rus", "", null]) {
    it(`iso=${JSON.stringify(bad)}`, () => {
      const { container } = render(<CountryLink iso={bad} name="Russia" />);
      expect(container.querySelector("a")).toBeNull();
      expect(container.textContent).toContain("Russia");
      const marker = container.querySelector(`[data-country-unlinked="${String(bad ?? "")}"]`);
      expect(marker).not.toBeNull();
      // The marker is VISIBLE text, not only an attribute: a silently
      // unlinked name is indistinguishable from a working one.
      const sup = marker.querySelector("sup");
      expect(sup?.textContent).toBe("?");
      expect(sup.getAttribute("aria-label")).toBe("no country card");
    });
  }
});

describe("G3: the anchor contract", () => {
  it("is exactly one real link with the card's href and no target", () => {
    const { container } = render(<CountryLink iso="RUS" name="Russia" />);
    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(1);
    const a = links[0];
    expect(a.getAttribute("href")).toBe("#/country/RUS");
    expect(a.hasAttribute("target")).toBe(false);
    expect(a.getAttribute("data-country")).toBe("RUS");
    const label = a.getAttribute("aria-label");
    expect(label).toContain("Russia");
    expect(label).toContain("RUS");
    expect(a.tabIndex).toBeGreaterThanOrEqual(0);
    expect(a.textContent).toBe("RussiaRUS");
  });

  it("showCode={false} renders the name alone", () => {
    const { container } = render(<CountryLink iso="JPN" name="JPN" showCode={false} />);
    expect(container.querySelector("a").textContent).toBe("JPN");
  });

  it("children replace the name as the content", () => {
    const { container } = render(
      <CountryLink iso="JPN" name="Japan" showCode={false}><span>card body</span></CountryLink>,
    );
    expect(container.querySelector("a span").textContent).toBe("card body");
  });

  it("a click inside a clickable row navigates and does NOT fire the row", async () => {
    // F-0064: the HOLDINGS / GOLD row opens the inline history panel. The
    // name inside it opens the card. Both must keep working, separately.
    const rowSpy = vi.fn();
    const { container } = render(
      <table><tbody><tr onClick={rowSpy}><td><CountryLink iso="RUS" name="Russia" /></td></tr></tbody></table>,
    );
    const a = container.querySelector("a");
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    a.dispatchEvent(event);
    expect(rowSpy).not.toHaveBeenCalled();
    // Not prevented: the browser's own navigation is the behaviour.
    expect(event.defaultPrevented).toBe(false);
    // jsdom performs fragment navigation as a queued task, as browsers do.
    await waitFor(() => expect(window.location.hash).toBe("#/country/RUS"));
  });
});

describe("G8: the GOLD chart navigates", () => {
  it("a tick with an ISO3 value is a link to the card", () => {
    const { container } = render(<svg><CountryAxisTick x={0} y={0} payload={{ value: "USA" }} /></svg>);
    const a = container.querySelector('a[href="#/country/USA"]');
    expect(a).not.toBeNull();
    expect(a.textContent).toContain("USA");
  });

  it("a tick with no ISO3 key renders text and no link", () => {
    const { container } = render(<svg><CountryAxisTick x={0} y={0} payload={{ value: null }} /></svg>);
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("text")).not.toBeNull();
  });

  it("GoldReservesTab wires the tick and the bar (static: ResponsiveContainer is 0x0 in jsdom)", () => {
    const src = readFileSync(join(import.meta.dirname, "../pages/GoldReservesTab.jsx"), "utf8");
    const xAxis = src.match(/<XAxis\b[^\n]*/);
    expect(xAxis, "no <XAxis in GoldReservesTab.jsx").not.toBeNull();
    expect(xAxis[0]).toMatch(/tick=\{<CountryAxisTick\b/);
    const bar = src.match(/<Bar\b[\s\S]*?\/>/);
    expect(bar, "no <Bar .../> in GoldReservesTab.jsx").not.toBeNull();
    expect(bar[0]).toMatch(/onClick=\{[^}]*navigateToCountry\(/);
  });
});
