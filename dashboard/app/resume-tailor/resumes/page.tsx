"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import Header from "@/components/layout/Header";
import { api } from "@/lib/api";
import type { ResumeArtifact } from "@/lib/types";

type GroupBy = "none" | "company" | "title" | "month";

export default function ResumesPage() {
  const { data, error, mutate } = useSWR<ResumeArtifact[]>("/resumes", () =>
    api.resumes.list()
  );
  const [search, setSearch] = useState("");
  const [groupBy, setGroupBy] = useState<GroupBy>("none");
  const [expandedId, setExpandedId] = useState<string | null>(null);

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

  const handleDelete = async (id: string) => {
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
          className="px-3 py-1.5 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 w-64"
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

      {/* Grouped list */}
      {data && filtered.length > 0 && (
        <div className="space-y-6">
          {Object.entries(grouped).map(([group, items]) => (
            <div key={group}>
              {group && (
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-1">
                  {group}
                </h3>
              )}
              <div className="bg-white rounded-lg border border-gray-200 divide-y divide-gray-100">
                {items.map((r) => (
                  <div key={r.id}>
                    {/* Row */}
                    <div
                      className="flex items-center justify-between px-4 py-3 hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {r.jd_title || "Resume"}
                          </p>
                          {r.jd_company && (
                            <span className="text-xs text-gray-400">{r.jd_company}</span>
                          )}
                          <span className={`px-1.5 py-0.5 text-[10px] rounded ${
                            r.language === "en" ? "bg-blue-50 text-blue-600" : "bg-orange-50 text-orange-600"
                          }`}>
                            {r.language === "en" ? "EN" : "ZH"}
                          </span>
                          {r.has_pdf && (
                            <span className="text-[10px] text-green-600">PDF</span>
                          )}
                        </div>
                        <p className="text-[10px] text-gray-400 mt-0.5">
                          {new Date(r.created_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5 ml-3">
                        {r.has_pdf && (
                          <button
                            onClick={(e) => { e.stopPropagation(); window.open(`/api/resumes/${r.id}/pdf`, "_blank"); }}
                            className="px-2 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700"
                          >PDF</button>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); r.content_md && download(r.content_md, "md", "text/markdown", r.id); }}
                          disabled={!r.content_md}
                          className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 disabled:opacity-40"
                        >.md</button>
                        <button
                          onClick={(e) => { e.stopPropagation(); r.content_tex && download(r.content_tex, "tex", "application/x-tex", r.id); }}
                          disabled={!r.content_tex}
                          className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 disabled:opacity-40"
                        >.tex</button>
                        <DeleteBtn onDelete={() => handleDelete(r.id)} />
                        <span className="text-gray-300 text-xs ml-1">
                          {expandedId === r.id ? "▲" : "▼"}
                        </span>
                      </div>
                    </div>

                    {/* Expanded preview */}
                    {expandedId === r.id && (
                      <div className="px-4 pb-4 border-t border-gray-50">
                        <div className="flex gap-1 mt-3 mb-2">
                          <span className="text-xs text-gray-500">Preview (Markdown)</span>
                        </div>
                        <pre className="bg-gray-50 rounded p-3 text-[11px] text-gray-700 overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto font-mono leading-relaxed">
                          {r.content_md || "No content"}
                        </pre>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
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
