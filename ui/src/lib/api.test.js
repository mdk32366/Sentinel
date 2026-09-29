import { describe, expect, it } from "vitest";
import { apiUrl, resolveBase } from "./api";

/**
 * F-0052. The old implementation was:
 *
 *   const API = window.location.hostname === "localhost"
 *     ? "http://localhost:8000/api" : "/api";
 *
 * so the app only worked when the page was served from that exact hostname.
 * These cases fail against that and pass against reading the host.
 */

const loc = (hostname, protocol = "http:") => ({ hostname, protocol });

describe("resolveBase", () => {
  it("uses an explicit VITE_API_BASE above everything else", () => {
    expect(resolveBase({ VITE_API_BASE: "https://api.example.test/api", DEV: true },
                       loc("localhost"))).toBe("https://api.example.test/api");
  });

  it("strips a trailing slash from the override", () => {
    expect(resolveBase({ VITE_API_BASE: "https://api.example.test/api/" }, loc("x")))
      .toBe("https://api.example.test/api");
  });

  it("is same-origin in production", () => {
    expect(resolveBase({ DEV: false }, loc("sentinel-holy-rain-4562.fly.dev", "https:")))
      .toBe("/api");
  });

  it("reads the host in dev rather than assuming localhost", () => {
    // The defect, as a test. Each of these fell through to "/api" before.
    expect(resolveBase({ DEV: true }, loc("127.0.0.1"))).toBe("http://127.0.0.1:8000/api");
    expect(resolveBase({ DEV: true }, loc("192.168.1.42"))).toBe("http://192.168.1.42:8000/api");
    expect(resolveBase({ DEV: true }, loc("my-laptop.local"))).toBe("http://my-laptop.local:8000/api");
  });

  it("still works from localhost, which used to be the only case", () => {
    expect(resolveBase({ DEV: true }, loc("localhost"))).toBe("http://localhost:8000/api");
  });

  it("keeps the page's protocol in dev", () => {
    expect(resolveBase({ DEV: true }, loc("dev.internal", "https:")))
      .toBe("https://dev.internal:8000/api");
  });

  it("does not hardcode a dev host into production", () => {
    expect(resolveBase({ DEV: false }, loc("localhost"))).not.toContain("8000");
  });
});

describe("apiUrl", () => {
  it("accepts a path with or without a leading slash", () => {
    // Both forms appear across the 22 call sites.
    expect(apiUrl("/holdings")).toBe(apiUrl("holdings"));
  });

  it("preserves a query string", () => {
    expect(apiUrl("/cds?country=DEU")).toContain("/cds?country=DEU");
  });

  it("returns the base itself for an empty path", () => {
    expect(apiUrl("")).toBe(apiUrl());
  });
});
