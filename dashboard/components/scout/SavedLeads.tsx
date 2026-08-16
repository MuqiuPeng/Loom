"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import LeadDetail, { STATUSES, type Stage } from "@/components/scout/LeadDetail";
import { api } from "@/lib/api";
import { useCollapseNavWhile } from "@/lib/nav-collapse";
import { useDismissOnOutsideClick } from "@/lib/use-dismiss";
import type { LeadStatus, ScoutLead } from "@/lib/types";

const FILTERS = ["all", ...STATUSES.map((s) => s.value)] as const;

/** A dot per pipeline stage — the whole point of the table is seeing, at a
 * glance across fifty rows, which leads are stalled and where. */
function Progress({ lead }: { lead: ScoutLead }) {
  const stages: [string, boolean][] = [
    ["H", !!lead.harvested_at],
    ["A", !!lead.planned_at],
    ["D", !!lead.demo_built_at],
    ["E", !!lead.draft_body],
  ];
  return (
    <span className="inline-flex gap-1">
      {stages.map(([label, done]) => (
        <span
          key={label}
          title={
            {
              H: "Harvested",
              A: "Analysed",
              D: "Designs built",
              E: "Email drafted",
            }[label]
          }
          className={`w-5 h-5 rounded text-[10px] font-semibold inline-flex items-center justify-center ${
            done ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-300"
          }`}
        >
          {label}
        </span>
      ))}
    </span>
  );
}

export default function SavedLeads() {
  const [filter, setFilter] = useState<string>("all");
  const [leads, setLeads] = useState<ScoutLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, Stage | undefined>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.scout.listLeads(filter);
      setLeads(res.leads);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const selected = useMemo(
    () => leads.find((l) => l.id === selectedId) ?? null,
    [leads, selectedId]
  );

  // The panel needs the width, so the app nav steps aside while one is open.
  useCollapseNavWhile(!!selected);

  const panelRef = useRef<HTMLDivElement>(null);
  const dismiss = useCallback(() => setSelectedId(null), []);
  useDismissOnOutsideClick(panelRef, dismiss, !!selected);

  // Escape closes, as it does everywhere else.
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  async function setStatus(lead: ScoutLead, status: LeadStatus) {
    setLeads((prev) =>
      prev.map((l) => (l.id === lead.id ? { ...l, status } : l))
    );
    try {
      await api.scout.updateLead(lead.id, { status });
      if (filter !== "all") load();
    } catch {
      load();
    }
  }

  async function saveNotes(lead: ScoutLead, notes: string) {
    if (notes === (lead.notes || "")) return;
    setLeads((prev) =>
      prev.map((l) => (l.id === lead.id ? { ...l, notes } : l))
    );
    try {
      await api.scout.updateLead(lead.id, { notes });
    } catch {
      load();
    }
  }

  /** Run one pipeline stage. Stages are slow (a crawl, several Claude calls),
   * so each reports its own error without blocking the rest. */
  async function act(lead: ScoutLead, stage: Stage) {
    setBusy((b) => ({ ...b, [lead.id]: stage }));
    setErrors((e) => ({ ...e, [lead.id]: "" }));
    try {
      if (stage === "harvest") await api.scout.harvest(lead.id);
      if (stage === "plan") await api.scout.plan(lead.id);
      if (stage === "demo") await api.scout.buildDemo(lead.id);
      if (stage === "draft") await api.scout.draft(lead.id);
      await load();
    } catch (err) {
      setErrors((e) => ({
        ...e,
        [lead.id]: err instanceof Error ? err.message : String(err),
      }));
    } finally {
      setBusy((b) => ({ ...b, [lead.id]: undefined }));
    }
  }

  /** Build exactly the directions ticked in the plan. */
  async function build(lead: ScoutLead, directions: string[]) {
    setBusy((b) => ({ ...b, [lead.id]: "demo" }));
    setErrors((e) => ({ ...e, [lead.id]: "" }));
    try {
      await api.scout.buildDemo(lead.id, directions);
      await load();
    } catch (err) {
      setErrors((e) => ({
        ...e,
        [lead.id]: err instanceof Error ? err.message : String(err),
      }));
    } finally {
      setBusy((b) => ({ ...b, [lead.id]: undefined }));
    }
  }

  async function share(lead: ScoutLead, isPublic: boolean) {
    setLeads((prev) =>
      prev.map((l) => (l.id === lead.id ? { ...l, demo_public: isPublic } : l))
    );
    try {
      await api.scout.updateLead(lead.id, { demo_public: isPublic });
    } catch {
      load();
    }
  }

  async function choose(lead: ScoutLead, direction: string) {
    setLeads((prev) =>
      prev.map((l) => (l.id === lead.id ? { ...l, demo_active: direction } : l))
    );
    setBusy((b) => ({ ...b, [lead.id]: "select" }));
    try {
      await api.scout.selectDemo(lead.id, direction);
    } catch (err) {
      setErrors((e) => ({
        ...e,
        [lead.id]: err instanceof Error ? err.message : String(err),
      }));
      load();
    } finally {
      setBusy((b) => ({ ...b, [lead.id]: undefined }));
    }
  }

  async function remove(lead: ScoutLead) {
    if (selectedId === lead.id) setSelectedId(null);
    setLeads((prev) => prev.filter((l) => l.id !== lead.id));
    try {
      await api.scout.deleteLead(lead.id);
    } catch {
      load();
    }
  }

  return (
    // The panel overlays rather than squeezing: reflowing the table every
    // time a row is opened moves the rows under the cursor and drops columns
    // to nothing on a laptop screen.
    <div>
      <div className="mb-4 inline-flex rounded-md border border-gray-200 p-0.5 bg-gray-50">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 text-sm rounded capitalize transition-colors ${
              filter === f
                ? "bg-white text-indigo-700 font-medium shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-50 border border-red-100 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && <p className="text-sm text-gray-400 py-8">Loading…</p>}

      {!loading && leads.length === 0 && (
        <p className="text-sm text-gray-400 py-8 text-center">
          No saved leads{filter !== "all" ? ` with status “${filter}”` : ""}. Run
          a search and star one.
        </p>
      )}

      {leads.length > 0 && (
        <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">Business</th>
                <th className="px-3 py-2 font-medium w-16">Score</th>
                <th className="px-3 py-2 font-medium w-28">Status</th>
                <th className="px-3 py-2 font-medium w-28">Pipeline</th>
                <th className="px-3 py-2 font-medium w-40">Contact</th>
                <th className="px-3 py-2 w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {leads.map((lead) => {
                const active = lead.id === selectedId;
                const status = STATUSES.find((s) => s.value === lead.status);
                return (
                  <tr
                    key={lead.id}
                    onClick={() => setSelectedId(active ? null : lead.id)}
                    className={`cursor-pointer transition-colors ${
                      active ? "bg-indigo-50" : "hover:bg-gray-50"
                    }`}
                  >
                    <td className="px-3 py-2">
                      <div className="font-medium text-gray-900 truncate max-w-xs">
                        {lead.google_name || lead.site_title || lead.place_id}
                      </div>
                      {lead.google_address && (
                        <div className="text-xs text-gray-400 truncate max-w-xs">
                          {lead.google_address}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[11px] font-medium ${
                          lead.score >= 8
                            ? "bg-red-50 text-red-700"
                            : lead.score >= 4
                              ? "bg-amber-50 text-amber-700"
                              : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {lead.score}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                          status?.tone ?? "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {status?.label ?? lead.status}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <Progress lead={lead} />
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500 truncate max-w-[10rem]">
                      {lead.emails[0] || lead.google_phone || "—"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          remove(lead);
                        }}
                        className="text-gray-300 hover:text-red-500"
                        aria-label="Delete lead"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail panel, from the right — the table stays put on the left and
          the nav collapse is what pays for the panel's width. */}
      <div
        ref={panelRef}
        className={`fixed inset-y-0 right-0 z-40 w-full md:w-[46rem] max-w-full bg-white border-l border-gray-200 shadow-xl
          transition-transform duration-200 ease-in-out ${
            selected ? "translate-x-0" : "translate-x-full"
          }`}
        aria-hidden={!selected}
      >
        {selected && (
          <LeadDetail
            lead={selected}
            busy={busy[selected.id]}
            error={errors[selected.id]}
            onClose={() => setSelectedId(null)}
            onAct={act}
            onBuild={build}
            onShare={share}
            onChoose={choose}
            onStatus={setStatus}
            onNotes={saveNotes}
            onRefresh={load}
          />
        )}
      </div>
    </div>
  );
}
