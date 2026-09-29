// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAsyncAction } from "./useAsyncAction";

afterEach(() => vi.unstubAllGlobals());

const respond = (spec) => vi.fn(() => Promise.resolve(spec));

describe("useAsyncAction", () => {
  it("records the outcome of a pipeline that succeeded", async () => {
    vi.stubGlobal("fetch", respond({
      ok: true, status: 200, statusText: "OK",
      json: () => Promise.resolve({ inserted: 24 }),
    }));

    const { result } = renderHook(() => useAsyncAction());
    await act(async () => { await result.current.run("FRED Data", "/fetch/fred"); });

    expect(result.current.results["FRED Data"]).toEqual({ ok: true, data: { inserted: 24 } });
    expect(result.current.running["FRED Data"]).toBe(false);
  });

  it("a 500 is recorded as failed, and its body is kept", async () => {
    // Unlike the read path, both call sites already checked response.ok. The
    // body matters even on a failure: it is the error the operator needs.
    vi.stubGlobal("fetch", respond({
      ok: false, status: 500, statusText: "Internal Server Error",
      json: () => Promise.resolve({ detail: "FRED_API_KEY missing" }),
    }));

    const { result } = renderHook(() => useAsyncAction());
    await act(async () => { await result.current.run("FRED Data", "/fetch/fred"); });

    expect(result.current.results["FRED Data"].ok).toBe(false);
    expect(result.current.results["FRED Data"].data.detail).toBe("FRED_API_KEY missing");
  });

  it("an HTML error page does not turn a server fault into a client one", async () => {
    // A hard failure can answer with HTML. Letting the JSON parse error
    // escape would report `ok: false` with the PARSER's message and lose the
    // status entirely.
    vi.stubGlobal("fetch", respond({
      ok: false, status: 502, statusText: "Bad Gateway",
      json: () => Promise.reject(new SyntaxError("Unexpected token <")),
    }));

    const { result } = renderHook(() => useAsyncAction());
    await act(async () => { await result.current.run("TIC Holdings", "/fetch/treasury-holdings"); });

    expect(result.current.results["TIC Holdings"]).toEqual({ ok: false, data: {} });
  });

  it("a rejected request is recorded, not thrown at the caller", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network down"))));

    const { result } = renderHook(() => useAsyncAction());
    await act(async () => { await result.current.run("Gold Reserves", "/fetch/gold-reserves"); });

    expect(result.current.results["Gold Reserves"]).toEqual({
      ok: false, data: { error: "network down" },
    });
  });

  it("tracks progress per key, so two pipelines do not grey out each other's row", async () => {
    // ADMIN runs eight pipelines from one table. A single `running` flag
    // would disable every row the moment one was started.
    let release;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => {
      release = () => resolve({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve({}) });
    })));

    const { result } = renderHook(() => useAsyncAction());
    let pending;
    await act(async () => { pending = result.current.run("FRED Data", "/fetch/fred"); });

    await waitFor(() => expect(result.current.running["FRED Data"]).toBe(true));
    expect(result.current.running["TIC Holdings"]).toBeUndefined();

    await act(async () => { release(); await pending; });
    expect(result.current.running["FRED Data"]).toBe(false);
  });

  it("clears the previous result when the same pipeline is re-run", async () => {
    let failing = true;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(
      failing
        ? { ok: false, status: 500, statusText: "Internal Server Error", json: () => Promise.resolve({ detail: "boom" }) }
        : { ok: true, status: 200, statusText: "OK", json: () => Promise.resolve({ inserted: 3 }) },
    )));

    const { result } = renderHook(() => useAsyncAction());
    await act(async () => { await result.current.run("FRED Data", "/fetch/fred"); });
    expect(result.current.results["FRED Data"].ok).toBe(false);

    failing = false;
    await act(async () => { await result.current.run("FRED Data", "/fetch/fred"); });
    expect(result.current.results["FRED Data"]).toEqual({ ok: true, data: { inserted: 3 } });
  });

  it("uses POST by default and honours an explicit method", async () => {
    // The Stress Score pipeline is a GET. Sending it as POST returns 405 and
    // reads on the ADMIN tab as the pipeline having failed.
    const fetchStub = respond({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve({}) });
    vi.stubGlobal("fetch", fetchStub);

    const { result } = renderHook(() => useAsyncAction());
    await act(async () => { await result.current.run("FRED Data", "/fetch/fred"); });
    await act(async () => { await result.current.run("Stress Score", "/stress-score", { method: "GET" }); });

    expect(fetchStub.mock.calls[0][1].method).toBe("POST");
    expect(fetchStub.mock.calls[1][1].method).toBe("GET");
  });

  it("hands the outcome back to the caller as well as storing it", async () => {
    // So a tab can reload its resources on success without reading state.
    vi.stubGlobal("fetch", respond({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve({ n: 1 }) }));

    const { result } = renderHook(() => useAsyncAction());
    let returned;
    await act(async () => { returned = await result.current.run("cds", "/cds/fetch"); });

    expect(returned).toEqual({ ok: true, data: { n: 1 } });
  });
});
