"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { EducationData, Lang } from "@/lib/types";

interface LinkedProject {
  id: string;
  name: string;
}

interface Props {
  education: EducationData;
  lang: Lang;
  onUpdate: () => void;
  linkedProjects?: LinkedProject[];
}

export default function EducationCard({ education, lang, onUpdate, linkedProjects }: Props) {
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    institution: education.institution,
    degree: education.degree ?? "",
    field: education.field ?? "",
    start_date: education.start_date?.slice(0, 7) ?? "",
    end_date: education.end_date?.slice(0, 7) ?? "",
  });

  const period = (() => {
    if (!education.start_date) return "";
    const start = education.start_date.slice(0, 7);
    const end = education.end_date ? education.end_date.slice(0, 7) : "Present";
    return `${start} - ${end}`;
  })();

  const saveEdit = async () => {
    setSaving(true);
    try {
      const suffix = `_${lang}`;
      const data: Record<string, unknown> = {};
      if (draft.institution !== education.institution) data[`institution${suffix}`] = draft.institution;
      if (draft.degree !== (education.degree ?? "")) data[`degree${suffix}`] = draft.degree;
      if (draft.field !== (education.field ?? "")) data[`field${suffix}`] = draft.field;
      if (draft.start_date !== (education.start_date?.slice(0, 7) ?? "")) data.start_date = draft.start_date || null;
      if (draft.end_date !== (education.end_date?.slice(0, 7) ?? "")) data.end_date = draft.end_date || null;
      if (Object.keys(data).length > 0) {
        await api.profile.updateEducation(education.id, data);
      }
      setEditing(false);
      onUpdate();
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    await api.profile.deleteEducation(education.id);
    onUpdate();
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      {editing ? (
        <div className="space-y-3">
          <input value={draft.institution} onChange={(e) => setDraft({ ...draft, institution: e.target.value })}
            placeholder="Institution" className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <div className="grid grid-cols-2 gap-3">
            <input value={draft.degree} onChange={(e) => setDraft({ ...draft, degree: e.target.value })}
              placeholder="Degree" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <input value={draft.field} onChange={(e) => setDraft({ ...draft, field: e.target.value })}
              placeholder="Field of study" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <input value={draft.start_date} onChange={(e) => setDraft({ ...draft, start_date: e.target.value })}
              placeholder="Start (YYYY-MM)" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <input value={draft.end_date} onChange={(e) => setDraft({ ...draft, end_date: e.target.value })}
              placeholder="End (YYYY-MM)" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <div className="flex gap-2">
            <button onClick={saveEdit} disabled={saving}
              className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded-md hover:bg-indigo-700 disabled:opacity-50">
              {saving ? "Saving..." : "Save"}
            </button>
            <button onClick={() => setEditing(false)} className="text-sm text-gray-500 hover:text-gray-700">Cancel</button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-semibold text-gray-900">{education.institution}</h3>
            <p className="text-sm text-gray-600">
              {[education.degree, education.field].filter(Boolean).join(" in ")}
            </p>
            {period && <p className="text-xs text-gray-400 mt-1">{period}</p>}
            {linkedProjects && linkedProjects.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {linkedProjects.map((p) => (
                  <a
                    key={p.id}
                    href={`#project-${p.id}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded text-[10px] font-medium hover:bg-indigo-100 transition-colors"
                  >
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                    </svg>
                    {p.name}
                  </a>
                ))}
              </div>
            )}
          </div>
          <span className="shrink-0 flex items-center gap-1">
            <button onClick={() => { setDraft({ institution: education.institution, degree: education.degree ?? "", field: education.field ?? "", start_date: education.start_date?.slice(0, 7) ?? "", end_date: education.end_date?.slice(0, 7) ?? "" }); setEditing(true); }}
              className="p-1 text-gray-400 hover:text-indigo-600" title="Edit">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
              </svg>
            </button>
            {confirmDelete ? (
              <button onClick={remove} className="px-2 py-0.5 text-xs bg-red-600 text-white rounded">Confirm</button>
            ) : (
              <button onClick={() => setConfirmDelete(true)} onBlur={() => setTimeout(() => setConfirmDelete(false), 150)}
                className="p-1 text-gray-400 hover:text-red-600" title="Delete">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
          </span>
        </div>
      )}
    </div>
  );
}
