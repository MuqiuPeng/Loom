"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { ExperienceWithBullets, BulletType, Lang } from "@/lib/types";
import BulletItem from "./BulletItem";

const BULLET_TYPES: { value: BulletType; label: string }[] = [
  { value: "business_impact", label: "Business Impact" },
  { value: "technical_design", label: "Technical Design" },
  { value: "implementation", label: "Implementation" },
  { value: "scale", label: "Scale" },
  { value: "collaboration", label: "Collaboration" },
  { value: "problem_solving", label: "Problem Solving" },
];

interface LinkedProject {
  id: string;
  name: string;
}

interface Props {
  experience: ExperienceWithBullets;
  lang: Lang;
  onUpdate: () => void;
  linkedProjects?: LinkedProject[];
}

export default function ExperienceCard({ experience, lang, onUpdate, linkedProjects }: Props) {
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [toggling, setToggling] = useState(false);

  const toggleVisibility = async () => {
    setToggling(true);
    try {
      await api.profile.updateExperience(experience.id, { is_visible: !experience.is_visible });
      onUpdate();
    } finally {
      setToggling(false);
    }
  };
  const [newContent, setNewContent] = useState("");
  const [newType, setNewType] = useState<BulletType>("implementation");
  const [saving, setSaving] = useState(false);

  const [draft, setDraft] = useState({
    company: experience.company,
    title: experience.title,
    location: experience.location ?? "",
    start_date: experience.start_date?.slice(0, 7) ?? "",
    end_date: experience.end_date?.slice(0, 7) ?? "",
  });

  const period = (() => {
    if (!experience.start_date) return "";
    const start = experience.start_date.slice(0, 7);
    const end = experience.end_date ? experience.end_date.slice(0, 7) : "Present";
    return `${start} - ${end}`;
  })();

  const addBullet = async () => {
    if (!newContent.trim()) return;
    setSaving(true);
    try {
      await api.profile.addBullet({
        experience_id: experience.id,
        content_en: newContent.trim(),
        type: newType,
      });
      setNewContent("");
      setNewType("implementation");
      setAdding(false);
      onUpdate();
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    setSaving(true);
    try {
      const suffix = `_${lang}`;
      const data: Record<string, unknown> = {};
      if (draft.company !== experience.company) data[`company${suffix}`] = draft.company;
      if (draft.title !== experience.title) data[`title${suffix}`] = draft.title;
      if (draft.location !== (experience.location ?? "")) data[`location${suffix}`] = draft.location;
      if (draft.start_date !== (experience.start_date?.slice(0, 7) ?? "")) data.start_date = draft.start_date || null;
      if (draft.end_date !== (experience.end_date?.slice(0, 7) ?? "")) data.end_date = draft.end_date || null;
      if (Object.keys(data).length > 0) {
        await api.profile.updateExperience(experience.id, data);
      }
      setEditing(false);
      onUpdate();
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    await api.profile.deleteExperience(experience.id);
    onUpdate();
  };

  return (
    <div className={`bg-white rounded-lg border border-gray-200 p-6 ${!experience.is_visible ? "opacity-50" : ""}`}>
      {editing ? (
        <div className="space-y-3 mb-4">
          <div className="grid grid-cols-2 gap-3">
            <input value={draft.company} onChange={(e) => setDraft({ ...draft, company: e.target.value })}
              placeholder="Company" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              placeholder="Title" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <input value={draft.start_date} onChange={(e) => setDraft({ ...draft, start_date: e.target.value })}
              placeholder="Start (YYYY-MM)" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <input value={draft.end_date} onChange={(e) => setDraft({ ...draft, end_date: e.target.value })}
              placeholder="End (YYYY-MM)" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <input value={draft.location} onChange={(e) => setDraft({ ...draft, location: e.target.value })}
              placeholder="Location" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
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
        <div className="flex items-start justify-between mb-1">
          <div>
            <h3 className="font-semibold text-gray-900">{experience.company}</h3>
            <p className="text-sm text-gray-600">{experience.title}</p>
          </div>
          <span className="shrink-0 flex items-center gap-1">
            <button
              onClick={toggleVisibility}
              disabled={toggling}
              className={`p-1 transition-colors ${experience.is_visible ? "text-green-500 hover:text-gray-400" : "text-gray-300 hover:text-green-500"}`}
              title={experience.is_visible ? "Visible in resume (click to hide)" : "Hidden from resume (click to show)"}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                {experience.is_visible ? (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                )}
              </svg>
            </button>
            <button onClick={() => { setDraft({ company: experience.company, title: experience.title, location: experience.location ?? "", start_date: experience.start_date?.slice(0, 7) ?? "", end_date: experience.end_date?.slice(0, 7) ?? "" }); setEditing(true); }}
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

      {!editing && (period || experience.location) && (
        <p className="text-xs text-gray-400 mb-2">
          {[period, experience.location].filter(Boolean).join(" · ")}
        </p>
      )}

      {!editing && linkedProjects && linkedProjects.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
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

      <div className="divide-y divide-gray-50">
        {experience.bullets.map((b) => (
          <BulletItem key={b.id} bullet={b} onUpdate={onUpdate} />
        ))}
      </div>

      {experience.bullets.length === 0 && !adding && (
        <p className="text-sm text-gray-300 italic py-2">No bullets yet.</p>
      )}

      {adding ? (
        <div className="mt-4 space-y-3 border-t border-gray-100 pt-4">
          <textarea value={newContent} onChange={(e) => setNewContent(e.target.value)}
            placeholder="Describe the achievement..." rows={2} autoFocus
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <div className="flex items-center gap-3">
            <select value={newType} onChange={(e) => setNewType(e.target.value as BulletType)}
              className="border border-gray-300 rounded-md px-2 py-1.5 text-sm">
              {BULLET_TYPES.map((t) => (<option key={t.value} value={t.value}>{t.label}</option>))}
            </select>
            <button onClick={addBullet} disabled={saving || !newContent.trim()}
              className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded-md hover:bg-indigo-700 disabled:opacity-50">
              {saving ? "Saving..." : "Add"}
            </button>
            <button onClick={() => setAdding(false)} className="text-sm text-gray-500 hover:text-gray-700">Cancel</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setAdding(true)} className="mt-3 text-sm text-indigo-600 hover:text-indigo-800">
          + Add Bullet
        </button>
      )}

    </div>
  );
}
