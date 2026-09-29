import { USADashboard } from "./USADashboard";
import { useState, useEffect } from "react";
import { apiFetch } from "../lib/api";
import { CountryDetail } from "../components/CountryDetail";

export function CountryTab({ initialIso, onIsoChange, latestAll = {} }) {
  const [countries, setCountries] = useState([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(initialIso || null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch(`/countries`)
      .then(r => r.json())
      .then(d => { setCountries(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const filtered = countries.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.iso_code.toLowerCase().includes(search.toLowerCase())
  );

  const byRegion = filtered.reduce((acc, c) => {
    const r = c.region || "Other";
    if (!acc[r]) acc[r] = [];
    acc[r].push(c);
    return acc;
  }, {});

  if (selected === "USA") {
    return (
      <div>
        <button onClick={() => { setSelected(null); if (onIsoChange) onIsoChange(null); }}
          style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#5A6878", borderRadius: 2, padding: "6px 14px", cursor: "pointer", fontFamily: "monospace", fontSize: 12, marginBottom: 20 }}>
          ← all countries
        </button>
        <USADashboard />
      </div>
    );
  }

  if (selected) {
    return (
      <div>
        <button onClick={() => { setSelected(null); if (onIsoChange) onIsoChange(null); }}
          style={{ background: "transparent", border: "1px solid #1E2D3D", color: "#5A6878", borderRadius: 2, padding: "6px 14px", cursor: "pointer", fontFamily: "monospace", fontSize: 12, marginBottom: 20 }}>
          ← all countries
        </button>
        <CountryDetail iso={selected} onClose={() => setSelected(null)} standalone latestAll={latestAll} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search country name or ISO code (e.g. Turkey, TUR, India, IND, USA)..."
          style={{ width: "100%", boxSizing: "border-box", background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "12px 16px", fontFamily: "monospace", fontSize: 13, color: "#E8E0D0", outline: "none" }}
          onFocus={e => e.target.style.borderColor = "#C8A96E"}
          onBlur={e => e.target.style.borderColor = "#1A2530"}
        />
        {search && <div style={{ fontFamily: "monospace", fontSize: 11, color: "#3A4D5C", marginTop: 6 }}>{filtered.length} countries found</div>}
      </div>

      {/* USA special card — always visible or when matching search */}
      {(!search || "united states usa america".includes(search.toLowerCase())) && (
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 10, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>
            United States <span style={{ color: "#C8A96E" }}>— Issuer Dashboard</span>
          </div>
          <button onClick={() => setSelected("USA")}
            style={{ background: "#0A1520", border: "1px solid #C8A96E44", borderRadius: 2, padding: "12px 20px", cursor: "pointer", fontFamily: "monospace", color: "#C8A96E", textAlign: "left", transition: "all 0.15s" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "#C8A96E"; e.currentTarget.style.background = "#C8A96E0A"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "#C8A96E44"; e.currentTarget.style.background = "#0A1520"; }}>
            <span style={{ fontSize: 10, color: "#5A6878", display: "block", marginBottom: 2 }}>USA</span>
            <span style={{ fontSize: 13 }}>United States of America</span>
            <span style={{ marginLeft: 12, fontSize: 10, color: "#5A6878" }}>M2 · Real Yield · Dollar · CPI · Yield Curve · Rate Scenario Modeler</span>
          </button>
        </div>
      )}

      {loading ? (
        <div style={{ fontFamily: "monospace", color: "#3A4D5C" }}>loading countries...</div>
      ) : (
        <div>
          {Object.entries(byRegion).sort().map(([region, regionCountries]) => (
            <div key={region} style={{ marginBottom: 28 }}>
              <div style={{ fontFamily: "monospace", fontSize: 10, color: "#3A4D5C", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 10, borderBottom: "1px solid #1A2530", paddingBottom: 6 }}>
                {region} <span style={{ color: "#1E2D3D" }}>({regionCountries.length})</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {regionCountries.map(c => (
                  <button key={c.iso_code} onClick={() => setSelected(c.iso_code)}
                    style={{ background: "#0A1520", border: "1px solid #1A2530", borderRadius: 2, padding: "8px 14px", cursor: "pointer", fontFamily: "monospace", fontSize: 12, color: "#8A9BAC", textAlign: "left", transition: "all 0.15s" }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = "#C8A96E"; e.currentTarget.style.color = "#E8E0D0"; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = "#1A2530"; e.currentTarget.style.color = "#8A9BAC"; }}>
                    <span style={{ color: "#5A6878", fontSize: 10, display: "block", marginBottom: 2 }}>{c.iso_code}</span>
                    {c.name}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ── Cross-Asset Tab ───────────────────────────────────────────────────────────
