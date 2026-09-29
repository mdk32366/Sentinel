import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = import.meta.dirname;

/** Every non-test .js/.jsx under ui/src, as [relativePath, contents]. */
function sourceFiles(dir = SRC, prefix = "") {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) out.push(...sourceFiles(join(dir, entry.name), rel));
    else if (/\.jsx?$/.test(entry.name) && !/\.test\.jsx?$/.test(entry.name)) {
      out.push([rel, readFileSync(join(dir, entry.name), "utf8")]);
    }
  }
  return out;
}

/**
 * `D-0055` states that no component talks to the API directly. A claim in the
 * register that nothing enforces is decoration, so this enforces it.
 *
 * The point is not tidiness. `F-0063` was one defect in five hand-copied
 * fetch blocks; it was fixable in one place only because every call site
 * could be routed through one module. The moment a component fetches for
 * itself, the next such defect has two homes again.
 */
describe("D-0055: the API lives behind hooks", () => {
  const ALLOWED = [/^lib\/api\.js$/, /^hooks\//];

  it("only lib/api.js and the hooks call apiFetch", () => {
    const offenders = sourceFiles()
      .filter(([, body]) => /\bapiFetch\s*\(/.test(body))
      .map(([rel]) => rel)
      .filter((rel) => !ALLOWED.some((ok) => ok.test(rel)));
    expect(offenders).toEqual([]);
  });

  it("no component or page reaches for window.fetch either", () => {
    // Routing around apiFetch would reintroduce F-0052: a hardcoded base URL
    // that only resolves when the app is served from localhost.
    const offenders = sourceFiles()
      .filter(([rel]) => rel.startsWith("pages/") || rel.startsWith("components/") || rel === "App.jsx")
      .filter(([, body]) => /(^|[^.\w])fetch\s*\(/.test(body))
      .map(([rel]) => rel);
    expect(offenders).toEqual([]);
  });

  it("nothing but lib/api.js spells an absolute API host", () => {
    // F-0052 proper: `window.location.hostname === "localhost"` decided the
    // base URL, so the app could not be previewed from any other host.
    const offenders = sourceFiles()
      .filter(([rel]) => rel !== "lib/api.js")
      .filter(([, body]) => /https?:\/\/localhost|127\.0\.0\.1|\.fly\.dev/.test(body))
      .map(([rel]) => rel);
    expect(offenders).toEqual([]);
  });

  it("App.jsx stays a shell rather than growing a data layer again", () => {
    // D-0054 brought it from 2,398 lines to 240 and D-0055 to 166. A soft
    // ceiling, generous on purpose: this should fail when someone starts
    // rebuilding a tab inside it, not when they add a button.
    const [, app] = sourceFiles().find(([rel]) => rel === "App.jsx");
    expect(app.split("\n").length).toBeLessThan(400);
  });
});
