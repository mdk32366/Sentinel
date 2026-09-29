// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useApiResource } from "./useApiResource";

/** A fetch stub that resolves with the given status and body. */
function stub({ ok = true, status = 200, statusText = "OK", body = {} } = {}) {
  return vi.fn(() =>
    Promise.resolve({ ok, status, statusText, json: () => Promise.resolve(body) }),
  );
}

beforeEach(() => vi.stubGlobal("fetch", stub()));
afterEach(() => vi.unstubAllGlobals());

describe("useApiResource: the happy path", () => {
  it("starts loading, then hands back the body", async () => {
    vi.stubGlobal("fetch", stub({ body: { total_billions_usd: 8558.9 } }));
    const { result } = renderHook(() => useApiResource("/holdings"));

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ total_billions_usd: 8558.9 });
    expect(result.current.error).toBeNull();
  });

  it("does not fetch at all when disabled, and does not sit in loading", () => {
    const fetchStub = stub();
    vi.stubGlobal("fetch", fetchStub);
    const { result } = renderHook(() => useApiResource("/holdings", { enabled: false }));

    expect(fetchStub).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });
});

describe("useApiResource: F-0063, an HTTP error is not a resource", () => {
  /**
   * These are the tests that go red against the code this hook replaces.
   *
   * The five inline copies did `.then(r => r.json())` with no `r.ok` check, so
   * a 500 carrying `{"detail": "..."}` was installed AS THE DATA and loading
   * went false. HOLDINGS and GOLD then rendered `data.holdings || []` — an
   * empty table, indistinguishable from a real empty result.
   */
  it("a 500 with a JSON body becomes an error, NOT data", async () => {
    vi.stubGlobal("fetch", stub({
      ok: false, status: 500, statusText: "Internal Server Error",
      body: { detail: "relation \"holdings\" does not exist" },
    }));
    const { result } = renderHook(() => useApiResource("/holdings"));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error.status).toBe(500);
  });

  it("the error names the status, so a caller can say which failure it was", async () => {
    vi.stubGlobal("fetch", stub({ ok: false, status: 401, statusText: "Unauthorized" }));
    const { result } = renderHook(() => useApiResource("/stats"));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error.message).toContain("401");
  });

  it("a rejected fetch is an error, not a permanent spinner", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network down"))));
    const { result } = renderHook(() => useApiResource("/holdings"));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error.message).toBe("network down");
    expect(result.current.data).toBeNull();
  });

  it("malformed JSON on a 200 is an error, not a half-parsed resource", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: true, status: 200, statusText: "OK",
      json: () => Promise.reject(new SyntaxError("Unexpected token <")),
    })));
    const { result } = renderHook(() => useApiResource("/holdings"));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.data).toBeNull();
  });
});

describe("useApiResource: reload and cancellation", () => {
  it("reload() re-runs the request", async () => {
    const fetchStub = stub({ body: { n: 1 } });
    vi.stubGlobal("fetch", fetchStub);
    const { result } = renderHook(() => useApiResource("/cds/all"));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchStub).toHaveBeenCalledTimes(1);

    await act(async () => { result.current.reload(); });
    await waitFor(() => expect(fetchStub).toHaveBeenCalledTimes(2));
  });

  it("a success after a failure clears the error", async () => {
    let failing = true;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(
      failing
        ? { ok: false, status: 503, statusText: "Service Unavailable", json: () => Promise.resolve({}) }
        : { ok: true, status: 200, statusText: "OK", json: () => Promise.resolve({ n: 2 }) },
    )));

    const { result } = renderHook(() => useApiResource("/cds/all"));
    await waitFor(() => expect(result.current.error).not.toBeNull());

    failing = false;
    await act(async () => { result.current.reload(); });
    await waitFor(() => expect(result.current.data).toEqual({ n: 2 }));
    expect(result.current.error).toBeNull();
  });

  it("does not set state after unmount", async () => {
    let settle;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => {
      settle = () => resolve({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve({ n: 1 }) });
    })));
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});

    const { unmount } = renderHook(() => useApiResource("/holdings"));
    unmount();
    await act(async () => { settle(); });

    // React 19 warns on setState after unmount. The point is not the warning
    // — it is that a tab closed mid-flight cannot write into a dead tree.
    expect(errors).not.toHaveBeenCalled();
    errors.mockRestore();
  });

  it("a changed path clears the previous resource instead of relabelling it", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve({
      ok: true, status: 200, statusText: "OK",
      json: () => Promise.resolve({ iso: String(url).split("/").pop() }),
    })));

    const { result, rerender } = renderHook(({ p }) => useApiResource(p), {
      initialProps: { p: "/holdings/JPN" },
    });
    await waitFor(() => expect(result.current.data).toEqual({ iso: "JPN" }));

    rerender({ p: "/holdings/CHN" });
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual({ iso: "CHN" }));
  });
});
