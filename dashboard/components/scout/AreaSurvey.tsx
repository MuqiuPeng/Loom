"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AreaResult, AreaSuggestion, ScoutCountry } from "@/lib/types";

/** Which town is worth working, answered with evidence.
 *
 * This is the decision that matters more than anything downstream: in a
 * mature market the good operators already have good sites and the rest are
 * coasting on regulars. A survey scans several areas the same way a real
 * search does and reports how many businesses in each are actually workable.
 */
export default function AreaSurvey({
  onPickArea,
}: {
  onPickArea: (area: string) => void;
}) {
  const [query, setQuery] = useState("cafe");
  const [limit, setLimit] = useState(20);
  const [suggestions, setSuggestions] = useState<AreaSuggestion[]>([]);
  const [countries, setCountries] = useState<ScoutCountry[]>([]);
  const [avoid, setAvoid] = useState<{ note?: string; patterns?: string[] }>({});
  const [chosen, setChosen] = useState<string[]>([]);
  const [results, setResults] = useState<AreaResult[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.scout
      .areas()
      .then((res) => {
        setSuggestions(res.areas);
        setCountries(res.countries || []);
        setAvoid(res.avoid || {});
        setChosen(res.default);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  /** Markets whose map provider does not exist yet.
   *
   * Their areas stay on screen rather than being hidden: the research is the
   * work, and it holds whether or not the integration has been written. They
   * are just not selectable, because a survey of them would fail at the first
   * request — Google cannot answer for mainland China, and falling back to it
   * would return results that look fine and mean nothing. */
  const blocked = useMemo(() => {
    const out = new Map<string, ScoutCountry>();
    for (const c of countries) if (!c.available) out.set(c.code, c);
    return out;
  }, [countries]);

  const unavailable = (s: AreaSuggestion) => blocked.has(s.country ?? "");

  const byRegion = useMemo(() => {
    const groups: Record<string, AreaSuggestion[]> = {};
    for (const s of suggestions) {
      // Several countries now, so a bare "NSW" or "浙江" is ambiguous.
      const label = s.country_name ? `${s.country_name} · ${s.region}` : s.region;
      (groups[label] ||= []).push(s);
    }
    return groups;
  }, [suggestions]);

  const toggle = (area: string) => {
    const entry = suggestions.find((s) => s.area === area);
    if (entry && unavailable(entry)) return;
    setChosen((prev) =>
      prev.includes(area) ? prev.filter((a) => a !== area) : [...prev, area]
    );
  };

  async function run() {
    if (!chosen.length) return;
    setRunning(true);
    setError(null);
    try {
      const res = await api.scout.survey(query, chosen, limit);
      setResults(res.areas);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-5">
        <div className="flex flex-wrap items-end gap-3 mb-4">
          <label className="block">
            <span className="text-xs font-medium text-gray-500">Category</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="mt-1 w-56 px-3 py-2 text-sm border border-gray-200 rounded-md"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-gray-500">Per area</span>
            <input
              type="number"
              value={limit}
              min={5}
              max={30}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="mt-1 w-24 px-3 py-2 text-sm border border-gray-200 rounded-md"
            />
          </label>
          <button
            onClick={run}
            disabled={running || chosen.length === 0}
            className="px-4 py-2 text-sm rounded-md bg-indigo-600 text-white font-medium hover:bg-indigo-700 disabled:opacity-40"
          >
            {running ? "Scanning…" : `Survey ${chosen.length} areas`}
          </button>
          <span className="text-xs text-gray-400">
            about {(chosen.length * 0.035).toFixed(2)} USD · {chosen.length * 20}s
          </span>
        </div>

        <div className="space-y-3">
          {Object.entries(byRegion).map(([region, entries]) => (
            <div key={region}>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
                {region}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {entries.map((s) => {
                  const on = chosen.includes(s.area);
                  const off = unavailable(s);
                  return (
                    <button
                      key={s.area}
                      onClick={() => toggle(s.area)}
                      disabled={off}
                      title={
                        off
                          ? `${s.note} — not searchable yet: ${
                              blocked.get(s.country ?? "")?.provider
                            } is not implemented`
                          : s.note
                      }
                      className={`px-2.5 py-1 rounded text-xs border transition-colors ${
                        off
                          ? "border-gray-100 text-gray-300 bg-gray-50 cursor-not-allowed line-through"
                          : on
                          ? "bg-indigo-50 border-indigo-300 text-indigo-700"
                          : "border-gray-200 text-gray-600 hover:bg-gray-50"
                      }`}
                    >
                      {s.area.replace(/ (NSW|VIC|QLD|WA|SA|TAS)$/, "")}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {avoid.patterns && avoid.patterns.length > 0 && (
          <details className="mt-4">
            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">
              Where not to look
            </summary>
            <ul className="mt-1 text-xs text-gray-500 space-y-0.5">
              {avoid.patterns.map((p) => (
                <li key={p}>· {p}</li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-50 border border-red-100 text-sm text-red-700">
          {error}
        </div>
      )}

      {results.length > 0 && (
        <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">Area</th>
                <th className="px-3 py-2 font-medium w-20">Workable</th>
                <th className="px-3 py-2 font-medium w-20">Hit rate</th>
                <th className="px-3 py-2 font-medium w-20">No site</th>
                <th className="px-3 py-2 font-medium w-20">Broken</th>
                <th className="px-3 py-2 font-medium w-24">Reachable</th>
                <th className="px-3 py-2 font-medium w-20">Signal</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {results.map((r) => (
                <tr
                  key={r.area}
                  onClick={() => onPickArea(r.area)}
                  title="Search this area"
                  className="cursor-pointer hover:bg-gray-50"
                >
                  <td className="px-3 py-2">
                    <div className="font-medium text-gray-900">{r.area}</div>
                    {r.note && (
                      <div className="text-xs text-gray-400">{r.note}</div>
                    )}
                    {r.top.length > 0 && (
                      <div className="text-xs text-gray-500 mt-0.5">
                        first calls: {r.top.join(", ")}
                      </div>
                    )}
                    {r.error && (
                      <div className="text-xs text-red-600">{r.error}</div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span className="font-semibold text-gray-900">
                      {r.workable}
                    </span>
                    <span className="text-gray-400"> / {r.total}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[11px] font-medium ${
                        r.hit_rate >= 40
                          ? "bg-green-50 text-green-700"
                          : r.hit_rate >= 25
                            ? "bg-amber-50 text-amber-700"
                            : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {r.hit_rate}%
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-600">{r.no_website}</td>
                  <td className="px-3 py-2 text-gray-600">{r.broken_site}</td>
                  <td className="px-3 py-2 text-gray-600">{r.contactable}</td>
                  <td className="px-3 py-2 text-gray-600">{r.avg_signal}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {results.length > 0 && (
        <p className="mt-3 text-xs text-gray-400 leading-relaxed">
          Workable means a real problem to fix AND a business likely to pay —
          both, since either alone is not a lead. Click an area to search it.
          Rendering is skipped during a survey; leads you pursue get the full
          check.
        </p>
      )}
    </div>
  );
}
