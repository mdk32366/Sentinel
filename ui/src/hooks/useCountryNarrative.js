import { useCallback, useState } from "react";

import { apiFetch } from "../lib/api";

/**
 * The Sentinel analyst brief for one country.
 *
 * ORDER-03 A2 / `F-0013`: the prompt is assembled server-side from the
 * database. This sends a country code and nothing else — the endpoint rejects
 * a free-form `prompt` with 422, and that is the whole reason the request
 * body is this small. Do not add fields to it.
 *
 * The brief belongs to the country it was generated for, so the state carries
 * its own `iso` and anything belonging to a different one reads as absent.
 * The obvious alternative is an effect that clears the brief when `iso`
 * changes, which is a setState in an effect — a render the component does not
 * need, and a rule this codebase has already had to suppress twice. Derived
 * during render, there is nothing to suppress and no window in which the
 * previous country's brief is on screen under the new country's name.
 */
export function useCountryNarrative(iso) {
  const [state, setState] = useState({ iso, narrative: null, loading: false, provider: null });

  const current = state.iso === iso ? state : { narrative: null, loading: false, provider: null };

  // D-0071: which provider produced the text on screen, reported by the
  // server rather than assumed by the caller. The footer credits this, so a
  // fallback or a default change cannot leave the UI claiming the wrong one
  // (F-0084).
  const generate = useCallback(async (provider) => {
    setState({ iso, narrative: null, loading: true, provider: null });
    try {
      const response = await apiFetch(`/analyze/country`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(provider ? { country: iso, provider } : { country: iso }),
      });

      if (!response.ok) {
        // 429 is the brief limit and says so; anything else is reported as
        // unavailable rather than as a wrong answer.
        setState({
          iso,
          narrative: response.status === 429
            ? "Brief limit reached. Try again later."
            : "Analysis unavailable.",
          loading: false,
          provider: null,
        });
        return;
      }

      const body = await response.json();
      setState({
        iso,
        narrative: body.text || "Analysis unavailable.",
        loading: false,
        provider: body.provider ?? null,
      });
    } catch {
      setState({ iso, narrative: "Failed to generate analysis. Please try again.", loading: false, provider: null });
    }
  }, [iso]);

  return {
    narrative: current.narrative,
    loading: current.loading,
    provider: current.provider,
    generate,
  };
}
