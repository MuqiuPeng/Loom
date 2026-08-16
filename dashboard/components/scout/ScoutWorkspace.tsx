"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Header from "@/components/layout/Header";
import AreaSurvey from "@/components/scout/AreaSurvey";
import SavedLeads from "@/components/scout/SavedLeads";
import { api } from "@/lib/api";
import type {
  Industry,
  LeadKind,
  ScoutCandidate,
  ScoutCountry,
  ScoutLead,
  ScoutStats,
} from "@/lib/types";

/** The two campaigns want opposite signals out of the same search.
 *
 * job:       companies that have a real site (so they're contactable) and
 *            ideally a careers page — the hidden job market.
 * freelance: companies with something broken — no site at all, or one the
 *            audit found problems with.
 *
 * They used to be a toggle over one list. They are separate pages now, and
 * separate rows, because the difference outlives the search: only freelance
 * leads may enter the outreach pipeline, and sending the wrong one a
 * commercial pitch is a legal problem rather than an untidy one. */
type Lens = LeadKind;

/** Minimum audit score to count as a freelance lead. A 1 means "no meta
 * description" — real, but nobody knocks on a door over it. */
const LEAD_THRESHOLD = 3;

const LENS_COPY: Record<Lens, { label: string; title: string; hint: string }> = {
  job: {
    label: "Job hunt",
    title: "Company Scout",
    hint: "Companies with a working site and a reachable address. A message asking about employment isn't a commercial electronic message, so the Spam Act's consent rules don't apply.",
  },
  freelance: {
    label: "Freelance",
    title: "Freelance leads",
    hint: "Businesses with no site, or a site with concrete problems — higher score means more to fix. Pitching work IS commercial: you need sender identification and a working opt-out, and it must never share an email with a job enquiry.",
  },
};

function score(c: ScoutCandidate, kind: Lens): number {
  if (kind === "job") {
    return (c.careers_url ? 4 : 0) + (c.emails.length ? 2 : 0) + (c.site_url ? 1 : 0);
  }
  return c.audit?.score ?? 0;
}

/** Warmer as the site gets worse — the eye should land on the best leads. */
function scoreTone(n: number): string {
  if (n >= 8) return "bg-red-50 text-red-700";
  if (n >= 4) return "bg-amber-50 text-amber-700";
  return "bg-gray-100 text-gray-500";
}

/** Mirrors Candidate.persistable() on the backend: place_id plus what came
 * off the company's own site. Google's fields never reach the file. */
function persistable(c: ScoutCandidate) {
  return {
    provider: c.provider,
    place_id: c.place_id,
    site_url: c.site_url,
    site_title: c.site_title,
    careers_url: c.careers_url,
    emails: c.emails,
    audit: c.audit,
    checked_at: c.checked_at,
  };
}

function Badge({ tone, children }: { tone: string; children: React.ReactNode }) {
  return (
    <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${tone}`}>
      {children}
    </span>
  );
}

export default function ScoutWorkspace({ kind }: { kind: Lens }) {
  const [query, setQuery] = useState("");
  const [near, setNear] = useState("");
  const [radius, setRadius] = useState(5000);
  const [limit, setLimit] = useState(20);
  const [tab, setTab] = useState<"areas" | "search" | "saved">("areas");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedLeads, setSavedLeads] = useState<ScoutLead[]>([]);
  const [starred, setStarred] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<ScoutStats | null>(null);
  const [candidates, setCandidates] = useState<ScoutCandidate[]>([]);
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [countries, setCountries] = useState<ScoutCountry[]>([]);
  const [country, setCountry] = useState<string>("");

  const shown = useMemo(() => {
    // Freelance leads need a problem the owner would recognise themselves.
    // Below 3 you're only looking at SEO tags — not worth a conversation.
    const filtered =
      kind === "freelance"
        ? candidates.filter((c) => (c.audit?.score ?? 0) >= LEAD_THRESHOLD)
        : candidates.filter((c) => c.google_website);
    return [...filtered].sort((a, b) => score(b, kind) - score(a, kind));
  }, [candidates, kind]);

  // Which results are already starred — so the stars survive a reload and a
  // re-search of the same area.
  const loadSaved = useCallback(async () => {
    try {
      const res = await api.scout.listLeads(kind);
      setSavedLeads(res.leads);
      setStarred(new Set(res.leads.map((l) => l.place_id)));
    } catch {
      /* the search still works without it */
    }
  }, []);

  useEffect(() => {
    loadSaved();
  }, [loadSaved]);

  useEffect(() => {
    api.scout.industries().then((r) => setIndustries(r.industries)).catch(() => {});
    api.scout.areas().then((r) => setCountries(r.countries)).catch(() => {});
  }, []);

  const chosenCountry = countries.find((c) => c.code === country);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim() && picked.size === 0) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.scout.search({
        query: query || undefined,
        industries: picked.size ? Array.from(picked) : undefined,
        near: near || undefined,
        country: country || undefined,
        radius_m: radius,
        limit,
      });
      setStats(res.stats);
      setCandidates(res.candidates);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  /** Starring is the save. Google's fields ride along for display only — the
   * backend stamps them with a 30-day expiry and blanks them after. */
  async function toggleStar(c: ScoutCandidate) {
    const already = starred.has(c.place_id);
    setStarred((prev) => {
      const next = new Set(prev);
      already ? next.delete(c.place_id) : next.add(c.place_id);
      return next;
    });
    setSaving(true);
    try {
      if (already) {
        const match = savedLeads.find((l) => l.place_id === c.place_id);
        if (match) await api.scout.deleteLead(match.id);
      } else {
        await api.scout.saveLeads(
          [
            {
              ...persistable(c),
              google_name: c.google_name,
              google_address: c.google_address,
              google_phone: c.google_phone,
            },
          ],
          kind,
        );
      }
      await loadSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      await loadSaved();
    } finally {
      setSaving(false);
    }
  }

  function download() {
    const blob = new Blob([JSON.stringify(shown.map(persistable), null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `leads-${kind}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="max-w-5xl">
      <Header title={LENS_COPY[kind].title}>
        {tab === "search" && shown.length > 0 && (
          <button
            onClick={download}
            className="px-3 py-1.5 text-sm rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50"
          >
            Export
          </button>
        )}
      </Header>

      <div className="mb-5 border-b border-gray-200 flex gap-6">
        {(["areas", "search", "saved"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`pb-2 -mb-px text-sm capitalize border-b-2 transition-colors ${
              tab === t
                ? "border-indigo-600 text-indigo-700 font-medium"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t === "areas" ? "Where to work" : t === "saved" ? "Saved leads" : "Search"}
          </button>
        ))}
      </div>

      {tab === "areas" && (
        <AreaSurvey
          onPickArea={(area) => {
            // Carry the choice straight into a real search — the survey's
            // only purpose is deciding where to spend the next hour.
            setNear(area);
            setTab("search");
          }}
        />
      )}
      {tab === "saved" && <SavedLeads kind={kind} />}
      {tab === "search" && (
      <>

      <p className="mb-4 text-xs text-gray-500 max-w-3xl">
        {LENS_COPY[kind].hint}
      </p>

      {/* Search form */}
      <form
        onSubmit={run}
        className="bg-white border border-gray-200 rounded-lg p-4 mb-6 space-y-3"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs font-medium text-gray-500">Category</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={
                kind === "job" ? "software development company" : "cafe"
              }
              className="mt-1 w-full px-3 py-2 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-gray-500">Area</span>
            <input
              value={near}
              onChange={(e) => setNear(e.target.value)}
              placeholder="Marrickville, Sydney"
              className="mt-1 w-full px-3 py-2 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400"
            />
          </label>
        </div>

        {/* Trades, not just whatever comes to mind. A free-text box quietly
            narrows this to cafés; the plumber with no site and a four-figure
            average job never gets typed in. */}
        {industries.length > 0 && (
          <div>
            <span className="text-xs font-medium text-gray-500">
              Industries{picked.size > 0 && ` · ${picked.size} selected`}
            </span>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {industries.map((ind) => {
                const on = picked.has(ind.key);
                return (
                  <button
                    key={ind.key}
                    type="button"
                    title={ind.why}
                    onClick={() =>
                      setPicked((prev) => {
                        const next = new Set(prev);
                        on ? next.delete(ind.key) : next.add(ind.key);
                        return next;
                      })
                    }
                    className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                      on
                        ? "bg-indigo-50 border-indigo-300 text-indigo-700 font-medium"
                        : "bg-white border-gray-200 text-gray-600 hover:border-gray-300"
                    }`}
                  >
                    {ind.label}
                    {ind.visitor_led && (
                      <span
                        className="ml-1 text-amber-500"
                        title="Visitor-led — customers are strangers choosing off a map"
                      >
                        ◆
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="text-xs font-medium text-gray-500">Market</span>
            <select
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className="mt-1 w-44 px-3 py-2 text-sm border border-gray-200 rounded-md bg-white"
            >
              <option value="">Auto (from area)</option>
              {countries.map((c) => (
                <option key={c.code} value={c.code} disabled={!c.available}>
                  {c.name} ({c.areas}){c.available ? "" : " — no provider"}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-gray-500">Radius (m)</span>
            <input
              type="number"
              value={radius}
              min={500}
              step={500}
              onChange={(e) => setRadius(Number(e.target.value))}
              className="mt-1 w-28 px-3 py-2 text-sm border border-gray-200 rounded-md"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-gray-500">Limit</span>
            <input
              type="number"
              value={limit}
              min={1}
              max={60}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="mt-1 w-24 px-3 py-2 text-sm border border-gray-200 rounded-md"
            />
          </label>
          <button
            type="submit"
            disabled={loading || (!query.trim() && picked.size === 0)}
            className="px-4 py-2 text-sm rounded-md bg-indigo-600 text-white font-medium hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? "Searching…" : "Search"}
          </button>
          {loading && (
            <span className="text-xs text-gray-400">
              Fetching each site in turn — about 15–30s for 20
            </span>
          )}
        </div>
      </form>

      {chosenCountry && !chosenCountry.available && (
        <div className="mb-4 p-3 rounded-md bg-amber-50 border border-amber-100 text-sm text-amber-800">
          <strong>{chosenCountry.name}</strong> has {chosenCountry.areas} researched
          areas but no map provider yet — {chosenCountry.detail}. Searching it
          would have to fall back to a provider that cannot answer for this
          market, so it refuses instead.
        </div>
      )}

      {error && (
        <div className="mb-6 p-3 rounded-md bg-red-50 border border-red-100 text-sm text-red-700">
          {error}
        </div>
      )}

      {stats && (
        <div className="mb-4 flex flex-wrap items-center gap-4 text-sm text-gray-500">
          <span>
            <strong className="text-gray-900">{stats.total}</strong> found
          </span>
          <span>
            <strong className="text-gray-900">{stats.without_website}</strong> with
            no website ({stats.pct_without_website}%)
          </span>
          <span>
            <strong className="text-gray-900">
              {candidates.filter((c) => c.emails.length).length}
            </strong>{" "}
            with a published email
          </span>
          <span className="text-gray-400">
            · {shown.length} in this kind
          </span>
        </div>
      )}

      {/* The market-research payload: what's wrong across the whole batch. */}
      {stats && kind === "freelance" && Object.keys(stats.by_finding).length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {Object.entries(stats.by_finding).map(([code, n]) => (
            <Badge key={code} tone="bg-gray-100 text-gray-600">
              {code} × {n}
            </Badge>
          ))}
        </div>
      )}

      {/* Results */}
      <div className="space-y-2">
        {shown.map((c) => (
          <div
            key={c.place_id}
            className="bg-white border border-gray-200 rounded-lg p-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex gap-2">
                <button
                  onClick={() => toggleStar(c)}
                  disabled={saving}
                  title={
                    starred.has(c.place_id)
                      ? "Remove from leads"
                      : "Star — adds it to Saved leads"
                  }
                  className={`text-lg leading-none pt-0.5 transition-colors ${
                    starred.has(c.place_id)
                      ? "text-amber-400 hover:text-amber-500"
                      : "text-gray-200 hover:text-gray-400"
                  }`}
                >
                  ★
                </button>
                <div className="min-w-0">
                  <h3 className="font-medium text-gray-900">
                    {c.google_name}
                    {c.google_maps_uri && (
                      <a
                        href={c.google_maps_uri}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="ml-1.5 text-xs font-normal text-gray-300 hover:text-indigo-600"
                      >
                        ↗
                      </a>
                    )}
                  </h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {c.google_address}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {c.google_rating != null && (
                      <span className="text-amber-600">
                        ★ {c.google_rating}
                        {c.google_rating_count
                          ? ` (${c.google_rating_count})`
                          : ""}
                      </span>
                    )}
                    {c.google_price_level && (
                      <span className="ml-2">
                        {c.google_price_level.replace("PRICE_LEVEL_", "").toLowerCase()}
                      </span>
                    )}
                    {c.google_hours.length > 0 && (
                      <span className="ml-2" title={c.google_hours.join("\n")}>
                        hours ⓘ
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 shrink-0">
                {kind === "freelance" && c.audit && (
                  <Badge tone={scoreTone(c.audit.score)}>
                    score {c.audit.score}
                  </Badge>
                )}
                {!c.google_website && (
                  <Badge tone="bg-amber-50 text-amber-700">no website</Badge>
                )}
                {c.careers_url && (
                  <Badge tone="bg-green-50 text-green-700">careers</Badge>
                )}
                {c.emails.length > 0 && (
                  <Badge tone="bg-indigo-50 text-indigo-700">
                    {c.emails.length} email
                  </Badge>
                )}
                {c.primary_type && (
                  <Badge tone="bg-gray-100 text-gray-500">
                    {c.primary_type}
                  </Badge>
                )}
              </div>
            </div>

            {/* What's wrong, in words you can say to the owner. */}
            {c.audit && c.audit.findings.length > 0 && (
              <ul className="mt-3 space-y-1">
                {c.audit.findings.map((f) => (
                  <li key={f.code} className="flex gap-2 text-sm">
                    <span className="text-amber-500 shrink-0">•</span>
                    <span>
                      <span className="text-gray-800 font-medium">
                        {f.label}
                      </span>
                      {f.detail && (
                        <span className="text-gray-500"> — {f.detail}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-3 space-y-1 text-sm">
              {c.site_url && (
                <div className="flex gap-2">
                  <span className="text-xs text-gray-400 w-16 shrink-0 pt-0.5">
                    site
                  </span>
                  <a
                    href={c.site_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-indigo-600 hover:underline truncate"
                  >
                    {c.site_title || c.site_url}
                  </a>
                </div>
              )}
              {c.careers_url && (
                <div className="flex gap-2">
                  <span className="text-xs text-gray-400 w-16 shrink-0 pt-0.5">
                    careers
                  </span>
                  <a
                    href={c.careers_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-indigo-600 hover:underline truncate"
                  >
                    {c.careers_url}
                  </a>
                </div>
              )}
              {c.emails.length > 0 && (
                <div className="flex gap-2">
                  <span className="text-xs text-gray-400 w-16 shrink-0 pt-0.5">
                    email
                  </span>
                  <span className="text-gray-700 break-all">
                    {c.emails.join(", ")}
                  </span>
                </div>
              )}
              {c.google_phone && (
                <div className="flex gap-2">
                  <span className="text-xs text-gray-400 w-16 shrink-0 pt-0.5">
                    phone
                  </span>
                  <span className="text-gray-700">{c.google_phone}</span>
                </div>
              )}
              {c.fetch_error && (
                <div className="flex gap-2">
                  <span className="text-xs text-gray-400 w-16 shrink-0 pt-0.5">
                    note
                  </span>
                  <span className="text-gray-400 text-xs">{c.fetch_error}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {stats && shown.length === 0 && !loading && (
        <p className="text-sm text-gray-400 py-8 text-center">
          Nothing in this kind — try the other one, or widen the category or area.
        </p>
      )}

      {candidates.length > 0 && (
        <p className="mt-6 text-xs text-gray-400 leading-relaxed">
          Name, address and phone come from Google Places and are shown here
          only. The export contains just the place_id and what was read from
          each company&apos;s own site — Maps Platform Terms 3.2.3. Saving keeps
          Google&apos;s copy for 30 days, then blanks it.
        </p>
      )}
      </>
      )}
    </div>
  );
}
