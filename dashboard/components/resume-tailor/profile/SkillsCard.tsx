"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Skill } from "@/lib/types";

const LEVEL_COLORS: Record<string, string> = {
  expert: "bg-green-100 text-green-800",
  proficient: "bg-blue-100 text-blue-800",
  familiar: "bg-gray-100 text-gray-600",
};

const LEVELS = ["expert", "proficient", "familiar"];
const CATEGORIES = ["Backend", "Frontend", "Database", "AI/ML", "DevOps/Infra", "Testing", "Data Processing", "Other"];

interface Props {
  skills: Skill[];
  onUpdate: () => void;
}

export default function SkillsCard({ skills, onUpdate }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState({ name: "", level: "proficient", category: "Backend" });
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);

  const saveEdit = async (id: string) => {
    setSaving(true);
    try {
      await api.profile.updateSkill(id, { name: draft.name, level: draft.level, category: draft.category });
      setEditingId(null);
      onUpdate();
    } finally { setSaving(false); }
  };

  const remove = async (id: string) => {
    await api.profile.deleteSkill(id);
    setConfirmDeleteId(null);
    onUpdate();
  };

  const addSkill = async () => {
    if (!draft.name.trim()) return;
    setSaving(true);
    try {
      await api.profile.addSkill({ name: draft.name.trim(), level: draft.level, category: draft.category });
      setAdding(false);
      setDraft({ name: "", level: "proficient", category: "Backend" });
      onUpdate();
    } finally { setSaving(false); }
  };

  const grouped: Record<string, Skill[]> = {};
  for (const s of skills) {
    const cat = s.category || "Other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(s);
  }

  const categories = Object.keys(grouped).sort((a, b) => {
    if (a === "Other") return 1;
    if (b === "Other") return -1;
    return a.localeCompare(b);
  });

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Skills</h2>
        {!adding && (
          <button onClick={() => { setDraft({ name: "", level: "proficient", category: "Backend" }); setAdding(true); }}
            className="text-sm text-indigo-600 hover:text-indigo-800">+ Add</button>
        )}
      </div>

      {adding && (
        <div className="flex items-center gap-2 mb-3 p-3 border border-dashed border-indigo-300 rounded-lg">
          <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="Skill name" className="border border-gray-300 rounded-md px-2 py-1 text-sm w-32 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <select value={draft.level} onChange={(e) => setDraft({ ...draft, level: e.target.value })}
            className="border border-gray-300 rounded-md px-2 py-1 text-sm">
            {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}
            className="border border-gray-300 rounded-md px-2 py-1 text-sm">
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button onClick={addSkill} disabled={saving || !draft.name.trim()}
            className="px-3 py-1 bg-indigo-600 text-white text-sm rounded-md hover:bg-indigo-700 disabled:opacity-50">
            {saving ? "..." : "Add"}
          </button>
          <button onClick={() => setAdding(false)} className="text-sm text-gray-500 hover:text-gray-700">Cancel</button>
        </div>
      )}

      {skills.length === 0 && !adding && (
        <p className="text-sm text-gray-400 italic">No skills added yet.</p>
      )}

      <div className="space-y-2">
        {categories.map((cat) => (
          <div key={cat} className="flex items-baseline gap-2">
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wider w-24 shrink-0 text-right">
              {cat}
            </span>
            <div className="flex flex-wrap gap-1">
              {grouped[cat].map((s) => {
                if (editingId === s.id) {
                  return (
                    <span key={s.id} className="inline-flex items-center gap-1 border border-indigo-300 rounded px-1 py-0.5">
                      <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                        className="border-none text-xs w-20 focus:outline-none" />
                      <select value={draft.level} onChange={(e) => setDraft({ ...draft, level: e.target.value })}
                        className="border-none text-xs focus:outline-none">
                        {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
                      </select>
                      <button onClick={() => saveEdit(s.id)} disabled={saving}
                        className="text-xs text-indigo-600 hover:text-indigo-800">{saving ? "..." : "OK"}</button>
                      <button onClick={() => setEditingId(null)}
                        className="text-xs text-gray-400 hover:text-gray-600">X</button>
                    </span>
                  );
                }

                return (
                  <span
                    key={s.id ?? s.name}
                    className={`group inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs cursor-default ${
                      LEVEL_COLORS[s.level] ?? LEVEL_COLORS.familiar
                    }`}
                    title={s.context ?? undefined}
                  >
                    {s.name}
                    <span className="hidden group-hover:inline-flex items-center gap-0.5 ml-0.5">
                      <button onClick={() => { setDraft({ name: s.name, level: s.level, category: s.category || "Other" }); setEditingId(s.id); }}
                        className="text-gray-500 hover:text-indigo-600" title="Edit">
                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                      </button>
                      {confirmDeleteId === s.id ? (
                        <button onClick={() => remove(s.id)} className="text-[9px] bg-red-600 text-white px-1 rounded">Del</button>
                      ) : (
                        <button onClick={() => setConfirmDeleteId(s.id)} onBlur={() => setTimeout(() => setConfirmDeleteId(null), 150)}
                          className="text-gray-500 hover:text-red-600" title="Delete">
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      )}
                    </span>
                  </span>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
