"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import Header from "@/components/layout/Header";
import ResumeDetail from "@/components/resume-tailor/resumes/ResumeDetail";
import { useCollapseNavWhile } from "@/lib/nav-collapse";
import { useDismissOnOutsideClick } from "@/lib/use-dismiss";
import { api } from "@/lib/api";
import type { ResumeArtifact } from "@/lib/types";

type GroupBy = "none" | "company" | "title" | "month";

export default function ResumesPage() {
  const { data, error, mutate } = useSWR<ResumeArtifact[]>("/resumes", () =>
    api.resumes.list()
  );
  const [search, setSearch] = useState("");
  const [groupBy, setGroupBy] = useState<GroupBy>("none");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genLang, setGenLang] = useState<"en" | "zh">("en");

  const handleGenerateGeneral = async () => {
    if (generating) return;
    setGenerating(true);
    try {
      const { task_id } = await api.tasks.generateGenericResume({
        language: genLang,
        format: "markdown",
      });
      for (;;) {
        await new Promise((r) => setTimeout(r, 2500));
        const t = await api.tasks.get(task_id);
        mutate();
        if (t.status === "completed" || t.status === "failed") break;
      }
    } catch {
      // task polling failed; list refresh below still shows current state
    } finally {
      setGenerating(false);
      mutate();
    }
  };

  // Filter by search
  const filtered = useMemo(() => {
    if (!data) return [];
    if (!search.trim()) return data;
    const q = search.toLowerCase();
    return data.filter(
      (r) =>
        (r.jd_title || "").toLowerCase().includes(q) ||
        (r.jd_company || "").toLowerCase().includes(q) ||
        (r.content_md || "").toLowerCase().includes(q)
    );
  }, [data, search]);

  // Group
  const grouped = useMemo(() => {
    if (groupBy === "none") return { "": filtered };
    const groups: Record<string, ResumeArtifact[]> = {};
    for (const r of filtered) {
      let key = "";
      if (groupBy === "company") key = r.jd_company || "Unknown";
      else if (groupBy === "title") key = r.jd_title || "Unknown";
      else if (groupBy === "month") key = r.created_at.slice(0, 7);
      if (!groups[key]) groups[key] = [];
      groups[key].push(r);
    }
    return groups;
  }, [filtered, groupBy]);

  const selected = useMemo(
    () => (data ?? []).find((r) => r.id === selectedId) ?? null,
    [data, selectedId]
  );

  // The preview wants the width; the app nav steps aside while it is open.
  useCollapseNavWhile(!!selected);

  const panelRef = useRef<HTMLDivElement>(null);
  const dismiss = useCallback(() => setSelectedId(null), []);
  useDismissOnOutsideClick(panelRef, dismiss, !!selected);

  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  const handleDelete = async (id: string) => {
    if (selectedId === id) setSelectedId(null);
    await api.resumes.delete(id);
    mutate();
  };

  const download = (content: string, ext: string, mime: string, id: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `resume_${id.slice(0, 8)}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-5xl">
      <Header title="Resumes" />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-4 mb-6 text-sm">
          Failed to load resumes.
        </div>
      )}

      {/* Search + Group controls */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search resumes..."
          className="px-3 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 w-full sm:w-64"
        />
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <span>Group:</span>
          {(["none", "company", "title", "month"] as GroupBy[]).map((g) => (
            <button
              key={g}
              onClick={() => setGroupBy(g)}
              className={`px-2 py-1 rounded transition-colors ${
                groupBy === g
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {g === "none" ? "All" : g.charAt(0).toUpperCase() + g.slice(1)}
            </button>
          ))}
        </div>
        <div className="flex items-center">
          <select
            value={genLang}
            onChange={(e) => setGenLang(e.target.value as "en" | "zh")}
            disabled={generating}
            className="px-2 py-1.5 text-sm border border-gray-200 rounded-l-md bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-100 disabled:text-gray-400"
          >
            <option value="en">EN</option>
            <option value="zh">中文</option>
          </select>
          <button
            onClick={handleGenerateGeneral}
            disabled={generating}
            className={`px-3 py-1.5 text-sm rounded-r-md transition-colors ${
              generating
                ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                : "bg-indigo-600 text-white hover:bg-indigo-700"
            }`}
          >
            {generating ? "Generating…" : "General Resume (no JD)"}
          </button>
        </div>
        <span className="text-xs text-gray-400 ml-auto">
          {filtered.length} resume{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Loading */}
      {!data && !error && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 p-4 animate-pulse h-16" />
          ))}
        </div>
      )}

      {/* Empty */}
      {data && filtered.length === 0 && (
        <div className="text-center py-16">
          <p className="text-gray-400">
            {search ? "No resumes match your search." : "No resumes generated yet."}
          </p>
        </div>
      )}

      {/* Grouped tables */}
      {data && filtered.length > 0 && (
        <div className="space-y-6">
          {Object.entries(grouped).map(([group, items]) => (
            <div key={group}>
              {group && (
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-1">
                  {group}
                </h3>
              )}
              <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-500">
                    <tr className="text-left">
                      <th className="px-3 py-2 font-medium">Role</th>
                      <th className="px-3 py-2 font-medium w-40">Company</th>
                      <th className="px-3 py-2 font-medium w-16">Lang</th>
                      <th className="px-3 py-2 font-medium w-16">PDF</th>
                      <th className="px-3 py-2 font-medium w-36">Created</th>
                      <th className="px-3 py-2 w-24" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {items.map((r) => {
                      const active = r.id === selectedId;
                      return (
                        <tr
                          key={r.id}
                          onClick={() => setSelectedId(active ? null : r.id)}
                          className={`cursor-pointer transition-colors ${
                            active ? "bg-indigo-50" : "hover:bg-gray-50"
                          }`}
                        >
                          <td className="px-3 py-2 font-medium text-gray-900 truncate max-w-xs">
                            {r.jd_title || "Resume"}
                          </td>
                          <td className="px-3 py-2 text-gray-500 truncate max-w-[10rem]">
                            {r.jd_company || "—"}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className={`px-1.5 py-0.5 text-[10px] rounded ${
                                r.language === "en"
                                  ? "bg-blue-50 text-blue-600"
                                  : "bg-orange-50 text-orange-600"
                              }`}
                            >
                              {r.language === "en" ? "EN" : "ZH"}
                            </span>
                          </td>
                          <td className="px-3 py-2">
                            {r.has_pdf ? (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  window.open(`/api/resumes/${r.id}/pdf`, "_blank");
                                }}
                                className="px-2 py-0.5 text-[11px] bg-indigo-600 text-white rounded hover:bg-indigo-700"
                              >
                                PDF
                              </button>
                            ) : (
                              <span className="text-xs text-gray-300">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-xs text-gray-400">
                            {new Date(r.created_at).toLocaleDateString()}
                          </td>
                          <td className="px-3 py-2 text-right">
                            <span onClick={(e) => e.stopPropagation()}>
                              <DeleteBtn onDelete={() => handleDelete(r.id)} />
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Preview panel, from the right — the list stays put. */}
      <div
        ref={panelRef}
        className={`fixed inset-y-0 right-0 z-40 w-full md:w-[46rem] max-w-full bg-white border-l border-gray-200 shadow-xl
          transition-transform duration-200 ease-in-out ${
            selected ? "translate-x-0" : "translate-x-full"
          }`}
        aria-hidden={!selected}
      >
        {selected && (
          <ResumeDetail
            resume={selected}
            onClose={() => setSelectedId(null)}
            onDownload={download}
          />
        )}
      </div>

    </div>
  );
}

function DeleteBtn({ onDelete }: { onDelete: () => void }) {
  const [confirm, setConfirm] = useState(false);
  return confirm ? (
    <button
      onClick={(e) => { e.stopPropagation(); onDelete(); }}
      className="px-2 py-1 text-xs text-red-600 hover:text-red-800"
    >Confirm</button>
  ) : (
    <button
      onClick={(e) => { e.stopPropagation(); setConfirm(true); }}
      onBlur={() => setTimeout(() => setConfirm(false), 200)}
      className="px-2 py-1 text-xs text-gray-400 hover:text-red-600"
    >Delete</button>
  );
}
