// @vitest-environment jsdom
/**
 * The MARKETS cards and their tooltips.
 *
 * The tooltip is the whole point of these: twelve series on a board titled
 * "sovereign stress" imply that all twelve feed it, and eight do not.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { METRICS } from "../lib/constants";
import { StatCard } from "./StatCard";

afterEach(cleanup);

const DGS10 = METRICS.find((m) => m.code === "DGS10");
const DGS30 = METRICS.find((m) => m.code === "DGS30");

describe("every one of the twelve cards carries an explanation", () => {
  it("has a tip and a stress role", () => {
    expect(METRICS).toHaveLength(12);
    for (const metric of METRICS) {
      expect(metric.tip, `${metric.code} has no tip`).toBeTruthy();
      expect(metric.stressRole, `${metric.code} has no stressRole`).toBeTruthy();
      expect(typeof metric.scored, `${metric.code} has no scored flag`).toBe("boolean");
    }
  });

  it("says what the series IS, not just that it matters", () => {
    // A tooltip that only says "watch this" is decoration. Each one has to
    // carry enough to identify the series.
    for (const metric of METRICS) {
      expect(metric.tip.length, `${metric.code}'s tip is too thin`).toBeGreaterThan(120);
    }
  });

  it("states the scoring connection in a way that matches the flag", () => {
    for (const metric of METRICS) {
      if (metric.scored) {
        expect(metric.stressRole, `${metric.code} is scored but does not say so`).toMatch(/^Scored/);
      } else {
        expect(metric.stressRole, `${metric.code} is unscored but does not say so`).toMatch(/[Nn]ot scored|Context, not a factor/);
      }
    }
  });

  it("marks exactly the three series a scorer actually reads", () => {
    // Cross-checked against the Python scorers by
    // tests/test_markets_tooltips.py, which is the half of this that cannot
    // be asserted from JavaScript.
    const scored = METRICS.filter((m) => m.scored).map((m) => m.code).sort();
    expect(scored).toEqual(["DCOILWTICO", "DGS10", "DGS2"]);
  });
});

describe("StatCard", () => {
  it("renders the value and the change window", () => {
    render(<StatCard label="10Y Treasury" value={4.21} unit="%" color="#C8A96E"
      change={{ value: -0.12, suffix: "pp", window: "vs 30d" }} />);
    expect(screen.getByText("4.21%")).toBeTruthy();
    expect(screen.getByText(/0\.12pp vs 30d/)).toBeTruthy();
  });

  it("shows nothing rather than zero when the series has not loaded", () => {
    render(<StatCard label="Gold Spot" value={null} unit="$/oz" color="#DAA520" />);
    expect(screen.getByText("—")).toBeTruthy();
  });

  it("reveals the tooltip on hover and hides it again", () => {
    const { container } = render(<StatCard label={DGS10.label} value={4.21} unit="%"
      color={DGS10.color} tip={DGS10.tip} stressRole={DGS10.stressRole} scored={DGS10.scored} />);
    const card = container.firstChild;

    expect(screen.queryByRole("tooltip")).toBeNull();

    fireEvent.mouseEnter(card);
    const bubble = screen.getByRole("tooltip");
    expect(bubble.textContent).toContain("reference risk-free rate");
    expect(bubble.textContent).toContain("yield-curve factor");

    fireEvent.mouseLeave(card);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("opens on keyboard focus too, not only on hover", () => {
    // The cards are the explanation of what this application measures. A
    // mouse-only explanation is no explanation for anyone using a keyboard.
    const { container } = render(<StatCard label={DGS30.label} value={4.8} unit="%"
      color={DGS30.color} tip={DGS30.tip} stressRole={DGS30.stressRole} scored={DGS30.scored} />);

    fireEvent.focus(container.firstChild);
    expect(screen.getByRole("tooltip")).toBeTruthy();
    expect(container.firstChild.getAttribute("tabindex")).toBe("0");
  });

  it("says plainly when a card is NOT scored", () => {
    const { container } = render(<StatCard label={DGS30.label} value={4.8} unit="%"
      color={DGS30.color} tip={DGS30.tip} stressRole={DGS30.stressRole} scored={DGS30.scored} />);

    fireEvent.mouseEnter(container.firstChild);
    expect(screen.getByRole("tooltip").textContent).toMatch(/Not scored/);
  });

  it("is not focusable and shows nothing when it has no tip", () => {
    // Every other StatCard call site — there are none today, but the
    // component must not sprout an empty bubble if one appears.
    const { container } = render(<StatCard label="Something" value={1} unit="" color="#fff" />);
    fireEvent.mouseEnter(container.firstChild);
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(container.firstChild.getAttribute("tabindex")).toBeNull();
  });
});
