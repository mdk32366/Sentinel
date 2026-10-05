// @vitest-environment jsdom
/**
 * D-0092 G4–G5: render, placement, myth visibility, accordion, USA pointer.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AboutTab } from "../pages/AboutTab";
import { USADashboard } from "../pages/USADashboard";

function stubResponse(url) {
  if (url.includes("/stress/composite")) {
    return { crisis: [], stressed: [], elevated: [], watch: [], summary: {}, as_of: "2026-09-28" };
  }
  if (url.includes("/timeseries") || url.includes("/metric/")) return [];
  return {};
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url) =>
    Promise.resolve({
      ok: true,
      status: 200,
      statusText: "OK",
      json: () => Promise.resolve(stubResponse(String(url))),
      text: () => Promise.resolve(""),
    }),
  ));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("G4 render, placement and myth visibility", () => {
  it("renders the title, four headings and every myth paragraph without fetching", () => {
    render(<AboutTab />);
    expect(screen.getByText(/START HERE — HOW T-BILLS WORK/)).toBeTruthy();
    expect(screen.getByText("What is a T-bill?")).toBeTruthy();
    expect(screen.getByText("How does a government use them?")).toBeTruthy();
    expect(screen.getByText("Why does the price change?")).toBeTruthy();
    expect(screen.getByText("Cashing a T-bill is not buying oil")).toBeTruthy();
    expect(screen.getByText(/dollars back/i)).toBeTruthy();
    expect(screen.getByText(/not the same as buying crude oil/i)).toBeTruthy();
    expect(screen.getByText(/park those dollars/i)).toBeTruthy();
    expect(screen.getByText(/separate step/i)).toBeTruthy();
    expect(screen.getByText(/cannot see what the dollars bought next/i)).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("START HERE precedes the retired STRESS tab in document order", () => {
    render(<AboutTab />);
    const start = screen.getByText(/START HERE/);
    const stress = screen.getByText(/STRESS tab/);
    expect(start.compareDocumentPosition(stress) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("myth lines are never inside a details accordion", () => {
    render(<AboutTab />);
    for (const re of [/dollars back/i, /separate step/i]) {
      const el = screen.getByText(re);
      expect(el.closest("details")).toBeNull();
    }
  });

  it("cheat sheet is one closed details with 5 rows, 3 headers and the note", () => {
    render(<AboutTab />);
    const root = document.getElementById("t-bills");
    expect(root).toBeTruthy();
    const detailsList = root.querySelectorAll("details");
    expect(detailsList.length).toBe(1);
    const details = detailsList[0];
    expect(details.open).toBe(false);
    expect(details.querySelector("summary").textContent).toMatch(/Cheat sheet/);
    expect(details.querySelectorAll("th").length).toBe(3);
    expect(details.querySelectorAll("tbody tr").length).toBe(5);
    expect(details.textContent).toMatch(/Usually, not always/);
  });
});

describe("G5 USA pointer", () => {
  it("USADashboard has exactly one link to #/about about T-bills", () => {
    render(<USADashboard />);
    const links = Array.from(document.querySelectorAll('a[href="#/about"]'));
    expect(links.length).toBe(1);
    expect(links[0].textContent).toMatch(/T-bills/);
  });
});
