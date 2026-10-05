### D-0092 - A plain-language T-bills explainer on ABOUT

Matt's ask, 2026-10-05 via Emma: ship a plain-language T-bills / sovereign-financing
explainer into Sentinel. The average person doesn't know how this works, and the
myth-bust is load-bearing — cashing a T-bill returns dollars; it is not buying oil.
Sentinel's own headline signals (COMPOSITE bill book, "short-term liquidation",
Japan's Tx 3mo tip, the WTI card) assume the reader already knows what a bill is.
Nothing on the site taught that. The only teaching surface is ABOUT.

**Choice.** One plain-language explainer as the first section on ABOUT (`#/about`),
right under the thesis and above RETIRED, reusing ABOUT section/card chrome. Copy
lives in `ui/src/lib/tbillsExplainer.js` (F-0096 pattern) and renders through
`TBillsExplainer.jsx` with no hooks, no api and no fetch. Four cards in order:
what a T-bill is, how a government uses them, why price changes, and the myth vs
fact card (amber left border, always expanded, never inside `<details>`). A yield
cheat sheet sits in a closed native `<details>`. Body text is 12px in the explainer
only. One muted pointer on the USA card (`USADashboard.jsx`) links via
`tabHref("ABOUT")` to `#/about`. Guards: G1 pins myth phrases and teaching points;
G2 holds an eighth-grade Flesch–Kincaid ceiling with a jargon self-test; G3 forbids
hooks/api/fetch; G4 pins placement above RETIRED and myth-never-in-details; G5 pins
the USA `#/about` link.

**Rejected.**
- *Help drawer.* None exists in the repo; a code search of `ui/src` for
  `drawer|<details|accordion|aria-expanded` finds 0 hits. New chrome against
  Emma's "prefer reuse".
- *Census-adjacent panel.* No Census surface in Sentinel; Census is PharmFold.
- *Full block inside the USA baseball card* next to `FeedbackLoop`. Thematically
  close, but the card is already dense with live charts and a calculator, requires
  the API, and a newcomer doesn't start at Card B. The secondary pointer gives that
  reader a path without the clutter.
- *InfoTip / ColHeader hover bubbles.* Capped at 320px, can't hold four sections,
  and hover-only content can't be clicked, linked or proved.
- *A new EXPLAIN tab.* New chrome plus another `TABS` entry; splits teaching across
  two tabs when ABOUT already exists.
- *One long paragraph.* Fails Peel-simple and makes the myth easy to skim past.
- *Cheat sheet always open.* Five rows open under four cards is clutter.
- *A custom React accordion.* State plus new chrome where native `<details>` does
  the job with keyboard support built in.
- *A live T-bill yield beside the copy.* No bill-rate feed in `METRICS`, and
  inventing one is forbidden.
- *Folding the "T-Bill" label vs all-Treasuries mismatch into this PR.* Held as
  F-0107 candidate; this PR stays copy-only.

**What forced the call.** The load-bearing fact is that Sentinel can see holdings
fall but not what the proceeds bought: TIC feeds are holdings and net transactions
in US Treasuries only (`dataSources.js`), and no series tracks what sovereigns buy
next. The myth card's last line is therefore a true statement about the app. ABOUT
is the only teaching page, fetches nothing, and reuses chrome exactly. Matt asked
for plain language at an eighth-grade level; G2 enforces that ceiling.

*What would change it.* Explainer on the USA card itself: move the component there
and keep the pointer as a back-link. Shareable deep links (`#/about/t-bills`): a
small `parseRoute` extension plus `scrollIntoView`, in a new Spec. A bill-rate
series ingested later: a "today's 3-month yield" line beside the seesaw, with
source and as-of (D-0074). Country-naming (Gulf exporters by name): needs a sourced
claim first.

*Who carries the downside.* Readers carry the risk of oversimplification; the copy
is deliberately approximate ("sells to the best offers", "usually, not always").
Fully reversible: UI copy only, no API, data or schema change. A single squash
revert plus the auto-redeploy restores today exactly. The worst plausible failure
is the myth getting softened in a later edit — G1 and G4 are aimed at precisely that.

*Bias check.* The repeat-of-last-time default was "put it in a hover tip like the
column headers", rejected because InfoTip is capped at 320px and hover-only
(D-0091 already ruled unprovable). The easy default was to bolt the myth onto the
WTI card tip; rejected because the myth is load-bearing and needs its own visible
card. What Emma or Matt seemed to want was the "baseball card"; ABOUT was picked
over the USA card with the pointer keeping that path. One call to flag: the 12px
body text (ABOUT uses 11px) — a small deviation for readability.

<!-- Kaylee: connector could not rewrite the 141KB docs/decisions.md in one Contents API call.
     On squash-merge, append this file's body (from ### D-0092 through Bias check) into docs/decisions.md and delete this file.
     Full decisions.md also in local commit f50321d / bundle /workspace/sentinel-d0092-proof/d0092.bundle -->
