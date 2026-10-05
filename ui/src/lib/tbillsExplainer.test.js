/**
 * D-0092 G1–G3: content, eighth-grade ceiling, and no-data static checks
 * for the T-bills explainer copy.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { TBILLS_EXPLAINER } from "./tbillsExplainer";

const SRC = import.meta.dirname;

/** Spec G2 Flesch–Kincaid heuristic — deterministic, no dependency. */
function syllables(word) {
  const w = word.toLowerCase().replace(/[^a-z]/g, "");
  if (!w) return 0;
  let n = (w.match(/[aeiouy]+/g) || []).length;
  if (w.endsWith("e") && !w.endsWith("le") && n > 1) n -= 1;
  return Math.max(1, n);
}

function fkGrade(text) {
  const sentences = text.split(/[.!?]+(?:\s|$)/).filter((s) => s.trim());
  const words = text.match(/[A-Za-z][A-Za-z'-]*|\$?\d[\d,]*/g) || [];
  const syl = words.reduce((acc, w) => acc + (/^[A-Za-z]/.test(w) ? syllables(w) : 1), 0);
  return 0.39 * (words.length / sentences.length) + 11.8 * (syl / words.length) - 15.59;
}

describe("G1 content and order", () => {
  it("sections are what/how/price and myth exists with enough copy", () => {
    expect(TBILLS_EXPLAINER.sections.map((s) => s.id)).toEqual(["what", "how", "price"]);
    expect(TBILLS_EXPLAINER.myth).toBeTruthy();
    for (const s of [...TBILLS_EXPLAINER.sections, TBILLS_EXPLAINER.myth]) {
      expect(s.heading, s.id).toBeTruthy();
      expect(s.paragraphs.length, s.id).toBeGreaterThanOrEqual(3);
      for (const p of s.paragraphs) expect(p.trim().length, s.id).toBeGreaterThan(0);
    }
  });

  it("myth phrases stay load-bearing", () => {
    const myth = TBILLS_EXPLAINER.myth;
    const joined = myth.paragraphs.join(" ");
    expect(joined).toMatch(/dollars back/i);
    expect(joined).toMatch(/not the same as buying crude oil/i);
    expect(joined).toMatch(/park/i);
    expect(joined).toMatch(/separate step/i);
    expect(myth.paragraphs[0]).toMatch(/^Myth:/);
    expect(myth.paragraphs[1]).toMatch(/^Fact:/);
  });

  it("how teaches auction and rolling over; price teaches the seesaw", () => {
    const how = TBILLS_EXPLAINER.sections.find((s) => s.id === "how").paragraphs.join(" ");
    const price = TBILLS_EXPLAINER.sections.find((s) => s.id === "price").paragraphs.join(" ");
    expect(how).toMatch(/auction/i);
    expect(how).toMatch(/rolling over/i);
    expect(price).toMatch(/seesaw/i);
    expect(price).toMatch(/yield goes up/i);
    expect(price).toMatch(/yield goes down/i);
  });
});

describe("G2 eighth-grade ceiling", () => {
  it("each section body scores ≤ 8.0", () => {
    const bodies = {
      what: TBILLS_EXPLAINER.sections.find((s) => s.id === "what").paragraphs.join(" "),
      how: TBILLS_EXPLAINER.sections.find((s) => s.id === "how").paragraphs.join(" "),
      price: TBILLS_EXPLAINER.sections.find((s) => s.id === "price").paragraphs.join(" "),
      myth: TBILLS_EXPLAINER.myth.paragraphs.join(" "),
    };
    for (const [id, text] of Object.entries(bodies)) {
      const grade = fkGrade(text);
      expect(grade, `${id} grade ${grade}`).toBeLessThanOrEqual(8.0);
    }
  });

  it("the jargon self-test scores above 12 (guard is not vacuous)", () => {
    const jargon =
      "Sovereign debt instruments' secondary-market valuations exhibit considerable sensitivity to anticipated monetary policy recalibrations.";
    expect(fkGrade(jargon)).toBeGreaterThan(12);
  });
});

describe("G3 no data", () => {
  it("explainer files never import hooks/api or call fetch", () => {
    const files = [
      join(SRC, "tbillsExplainer.js"),
      join(SRC, "../components/TBillsExplainer.jsx"),
    ];
    for (const path of files) {
      const body = readFileSync(path, "utf8");
      for (const line of body.split("\n")) {
        expect(line).not.toMatch(/from\s+["'][^"']*(hooks\/|lib\/api|\/api)/);
      }
      expect(body).not.toContain("fetch(");
      expect(body).not.toContain("useApiResource");
    }
  });

  it("TBILLS_EXPLAINER is a plain JSON-round-trippable object", () => {
    const round = JSON.parse(JSON.stringify(TBILLS_EXPLAINER));
    expect(round).toEqual(TBILLS_EXPLAINER);
  });
});
