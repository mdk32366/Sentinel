/**
 * D-0091 guards (a): the card's address.
 *
 * G1 pins the href format, G2 pins that a non-ISO key gets NO href (the
 * frontend never upper-cases or maps), G4 pins how a hash resolves to a tab.
 */
import { describe, expect, it } from "vitest";

import { countryHref, isCountryKey, parseRoute, tabHref } from "./countryRoute";

describe("G1: countryHref builds the card's address", () => {
  it("is #/country/<ISO3>", () => {
    expect(countryHref("RUS")).toBe("#/country/RUS");
    expect(countryHref("USA")).toBe("#/country/USA");
  });
});

describe("G2: a missing or non-ISO key has no address", () => {
  // Red if someone "helpfully" upper-cases or maps a token here. "RUSSIA" is
  // the CDS namespace token F-0106 was about; the server maps it, not us.
  for (const bad of [null, undefined, "", "RUSSIA", "UNITED_STATES", "rus", "RU", "RUSS", 42]) {
    it(`${JSON.stringify(bad)} -> null`, () => {
      expect(countryHref(bad)).toBeNull();
      expect(isCountryKey(bad)).toBe(false);
    });
  }
});

describe("tabHref", () => {
  it("lower-cases the tab into a hash", () => {
    expect(tabHref("HOLDINGS")).toBe("#/holdings");
    expect(tabHref("CROSS-ASSET")).toBe("#/cross-asset");
    expect(tabHref("COUNTRY")).toBe("#/country");
  });
});

describe("G4: parseRoute", () => {
  const TABLE = [
    ["", { tab: "MARKETS", iso: null }],
    ["#/holdings", { tab: "HOLDINGS", iso: null }],
    ["#/cross-asset", { tab: "CROSS-ASSET", iso: null }],
    ["#/country", { tab: "COUNTRY", iso: null }],
    ["#/country/jpn", { tab: "COUNTRY", iso: "JPN" }],
    ["#/country/RUSSIA", { tab: "COUNTRY", iso: null }],
    ["#/bogus", { tab: "MARKETS", iso: null }],
    // Not in the Spec's table, pinned anyway: the round trip and a bad escape.
    ["#/country/USA", { tab: "COUNTRY", iso: "USA" }],
    ["#/country/%E0%A4%A", { tab: "COUNTRY", iso: null }],
  ];
  for (const [hash, expected] of TABLE) {
    it(`${JSON.stringify(hash)} -> ${expected.tab} / ${expected.iso}`, () => {
      expect(parseRoute(hash)).toEqual(expected);
    });
  }

  it("every tab's own href parses back to that tab", () => {
    for (const t of ["MARKETS", "HOLDINGS", "CROSS-ASSET", "GOLD", "COMPOSITE", "CDS", "COUNTRY", "ADMIN", "ABOUT"]) {
      expect(parseRoute(tabHref(t)).tab).toBe(t);
    }
  });

  it("a card href parses back to that card", () => {
    expect(parseRoute(countryHref("DEU"))).toEqual({ tab: "COUNTRY", iso: "DEU" });
  });
});
