"use client";

import { useState } from "react";
import Markdown from "react-markdown";
import { api } from "@/lib/api";
import type { ProjectData, ProjectBullet, Lang } from "@/lib/types";

const TYPE_COLORS: Record<string, string> = {
  business_impact: "bg-green-100 text-green-700",
  technical_design: "bg-blue-100 text-blue-700",
  scale: "bg-orange-100 text-orange-700",
  implementation: "bg-gray-100 text-gray-600",
  collaboration: "bg-purple-100 text-purple-700",
  problem_solving: "bg-red-100 text-red-700",
};

const TYPE_LABELS: Record<string, string> = {
  business_impact: "Impact",
  technical_design: "Design",
  scale: "Scale",
  implementation: "Impl",
  collaboration: "Collab",
  problem_solving: "Debug",
};

const BULLET_TYPES = [
  { value: "business_impact", label: "Business Impact" },
  { value: "technical_design", label: "Technical Design" },
  { value: "implementation", label: "Implementation" },
  { value: "scale", label: "Scale" },
  { value: "collaboration", label: "Collaboration" },
  { value: "problem_solving", label: "Problem Solving" },
];

interface LinkOption {
  id: string;
  label: string;
  type: "experience" | "education";
}

interface Props {
  project: ProjectData;
  lang: Lang;
  onUpdate: () => void;
  linkedName?: string;
  linkedHref?: string;
  linkOptions?: LinkOption[];
}

export default function ProjectCard({ project, lang, onUpdate, linkedName, linkedHref, linkOptions }: Props) {
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [saving, setSaving] = useState(false);
  const [linkDropdown, setLinkDropdown] = useState(false);
  const [toggling, setToggling] = useState(false);
  const isOngoing = !project.end_date;
  const isVisible = project.is_visible !== false; // default true if undefined

  const toggleVisibility = async () => {
    setToggling(true);
    try {
      await api.profile.updateProject(project.id, { is_visible: !isVisible });
      onUpdate();
    } finally {
      setToggling(false);
    }
  };

  const changeLink = async (opt: LinkOption | null) => {
    setSaving(true);
    try {
      const data: Record<string, unknown> = {
        experience_id: null,
        education_id: null,
      };
      if (opt) {
        if (opt.type === "experience") data.experience_id = opt.id;
        else data.education_id = opt.id;
      }
      await api.profile.updateProject(project.id, data);
      onUpdate();
    } finally {
      setSaving(false);
      setLinkDropdown(false);
    }
  };
  const [editingBulletIdx, setEditingBulletIdx] = useState<number | null>(null);
  const [bulletDraft, setBulletDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newType, setNewType] = useState("implementation");
  const [confirmDeleteBullet, setConfirmDeleteBullet] = useState<number | null>(null);
  const [draft, setDraft] = useState({
    name: project.name,
    description: project.description ?? "",
    role: project.role ?? "",
    start_date: project.start_date?.slice(0, 7) ?? "",
    end_date: project.end_date?.slice(0, 7) ?? "",
  });

  const period = (() => {
    if (!project.start_date) return "";
    const start = project.start_date.slice(0, 7);
    const end = project.end_date ? project.end_date.slice(0, 7) : "Present";
    return `${start} - ${end}`;
  })();

  const saveEdit = async () => {
    setSaving(true);
    try {
      const suffix = `_${lang}`;
      const data: Record<string, unknown> = {};
      if (draft.name !== project.name) data[`name${suffix}`] = draft.name;
      if (draft.description !== (project.description ?? "")) data[`description${suffix}`] = draft.description;
      if (draft.role !== (project.role ?? "")) data[`role${suffix}`] = draft.role;
      if (draft.start_date !== (project.start_date?.slice(0, 7) ?? "")) data.start_date = draft.start_date || null;
      if (draft.end_date !== (project.end_date?.slice(0, 7) ?? "")) data.end_date = draft.end_date || null;
      if (Object.keys(data).length > 0) {
        await api.profile.updateProject(project.id, data);
      }
      setEditing(false);
      onUpdate();
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    await api.profile.deleteProject(project.id);
    onUpdate();
  };

  // Bullet operations — update the whole JSONB array
  const updateBullets = async (newBullets: ProjectBullet[]) => {
    setSaving(true);
    try {
      await api.profile.updateProject(project.id, { bullets: newBullets });
      onUpdate();
    } finally {
      setSaving(false);
    }
  };

  const saveBulletEdit = async (idx: number) => {
    const contentKey = lang === "zh" ? "content_zh" : "content_en";
    const updated = project.bullets.map((b, i) =>
      i === idx ? { ...b, [contentKey]: bulletDraft, content: bulletDraft } : b
    );
    await updateBullets(updated);
    setEditingBulletIdx(null);
  };

  const deleteBullet = async (idx: number) => {
    const updated = project.bullets.filter((_, i) => i !== idx);
    await updateBullets(updated);
    setConfirmDeleteBullet(null);
  };

  const addBullet = async () => {
    if (!newContent.trim()) return;
    const contentKey = lang === "zh" ? "content_zh" : "content_en";
    const otherKey = lang === "zh" ? "content_en" : "content_zh";
    const newBullet: ProjectBullet = {
      [contentKey]: newContent.trim(),
      [otherKey]: newContent.trim(),
      content: newContent.trim(),
      type: newType,
      priority: project.bullets.length + 1,
    };
    await updateBullets([...project.bullets, newBullet]);
    setNewContent("");
    setNewType("implementation");
    setAdding(false);
  };

  return (
    <div id={`project-${project.id}`} className={`bg-white rounded-lg border border-gray-200 p-6 scroll-mt-4 ${!isVisible ? "opacity-50" : ""}`}>
      {editing ? (
        <div className="space-y-3 mb-4">
          <div className="grid grid-cols-2 gap-3">
            <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="Project name" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <input value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })}
              placeholder="Role" className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <textarea value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            placeholder="Description" rows={2}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
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
        <>
          <div className="flex items-start justify-between mb-1">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-gray-900">{project.name}</h3>
              {/* Link tag — click to change */}
              <div className="relative"
                onBlur={(e) => {
                  if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                    setLinkDropdown(false);
                  }
                }}
              >
                <button
                  onClick={() => setLinkDropdown(!linkDropdown)}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                    linkedName
                      ? "bg-indigo-50 text-indigo-600 hover:bg-indigo-100"
                      : "bg-gray-50 text-gray-400 hover:bg-gray-100"
                  }`}
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                  </svg>
                  {linkedName || "Link..."}
                </button>
                {linkDropdown && linkOptions && (
                  <div className="absolute left-0 top-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg z-20 py-1 w-56 max-h-48 overflow-y-auto">
                    {linkedName && (
                      <button
                        onClick={() => changeLink(null)}
                        className="block w-full text-left px-3 py-1.5 text-xs text-red-500 hover:bg-red-50"
                      >
                        Remove link
                      </button>
                    )}
                    {linkOptions.filter(o => o.type === "experience").length > 0 && (
                      <p className="px-3 py-1 text-[10px] text-gray-400 uppercase">Experiences</p>
                    )}
                    {linkOptions.filter(o => o.type === "experience").map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() => changeLink(opt)}
                        className={`block w-full text-left px-3 py-1.5 text-xs hover:bg-gray-50 ${
                          project.experience_id === opt.id ? "text-indigo-600 font-medium" : "text-gray-700"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                    {linkOptions.filter(o => o.type === "education").length > 0 && (
                      <p className="px-3 py-1 text-[10px] text-gray-400 uppercase">Education</p>
                    )}
                    {linkOptions.filter(o => o.type === "education").map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() => changeLink(opt)}
                        className={`block w-full text-left px-3 py-1.5 text-xs hover:bg-gray-50 ${
                          project.education_id === opt.id ? "text-indigo-600 font-medium" : "text-gray-700"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {isOngoing && (
                <span className="px-2 py-0.5 bg-green-50 text-green-600 rounded text-[10px] font-medium">
                  Ongoing
                </span>
              )}
            </div>
            <span className="shrink-0 flex items-center gap-1">
              {project.role && (
                <span className="text-xs text-gray-500 bg-gray-50 px-2 py-0.5 rounded mr-1">{project.role}</span>
              )}
              <button
                onClick={toggleVisibility}
                disabled={toggling}
                className={`p-1 transition-colors ${isVisible ? "text-green-500 hover:text-gray-400" : "text-gray-300 hover:text-green-500"}`}
                title={isVisible ? "Visible in resume (click to hide)" : "Hidden from resume (click to show)"}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  {isVisible ? (
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                  )}
                </svg>
              </button>
              <button onClick={() => { setDraft({ name: project.name, description: project.description ?? "", role: project.role ?? "", start_date: project.start_date?.slice(0, 7) ?? "", end_date: project.end_date?.slice(0, 7) ?? "" }); setEditing(true); }}
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
          {(project.description || period || project.local_repo_path) && (
            <div className="mb-3">
              {project.description && <p className="text-sm text-gray-600">{project.description}</p>}
              {period && <p className="text-xs text-gray-400 mt-0.5">{period}</p>}
              {project.local_repo_path && (
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-gray-400 font-mono">
                    {project.local_repo_path.replace(/^\/Users\/[^/]+/, "~")}
                  </span>
                  {project.last_analyzed_at && (
                    <span className="text-[10px] text-gray-300">
                      analyzed {new Date(project.last_analyzed_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {!editing && project.tech_stack.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {project.tech_stack.map((t) => (
            <span key={t.name} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">{t.name}</span>
          ))}
        </div>
      )}

      {!editing && (
        <div className="divide-y divide-gray-50 border-t border-gray-100 pt-2">
          {project.bullets.map((b, i) => {
            const bType = (b.type as string) || "implementation";
            const colorClass = TYPE_COLORS[bType] ?? TYPE_COLORS.implementation;
            const label = TYPE_LABELS[bType] ?? bType;
            const content = (b.content as string) ?? "";

            if (editingBulletIdx === i) {
              return (
                <div key={i} className="py-2 space-y-2">
                  <textarea value={bulletDraft} onChange={(e) => setBulletDraft(e.target.value)}
                    rows={2} className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  <div className="flex gap-2">
                    <button onClick={() => saveBulletEdit(i)} disabled={saving}
                      className="px-3 py-1 bg-indigo-600 text-white text-xs rounded hover:bg-indigo-700 disabled:opacity-50">
                      {saving ? "..." : "Save"}
                    </button>
                    <button onClick={() => setEditingBulletIdx(null)} className="px-3 py-1 text-xs text-gray-500 hover:text-gray-700">Cancel</button>
                  </div>
                </div>
              );
            }

            return (
              <div key={i} className="group flex items-start gap-2 py-1.5">
                <span className="mt-0.5 shrink-0 w-12 text-center">
                  <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${colorClass}`}>{label}</span>
                </span>
                <span className="flex-1 text-sm text-gray-800 leading-snug [&_strong]:font-semibold [&_em]:italic [&_em]:text-gray-600 [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs [&_p]:inline">
                  <Markdown>{content}</Markdown>
                </span>
                <span className="shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-2">
                  <button onClick={() => { setBulletDraft(content); setEditingBulletIdx(i); }}
                    className="p-1 text-gray-400 hover:text-indigo-600" title="Edit">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                    </svg>
                  </button>
                  {confirmDeleteBullet === i ? (
                    <button onClick={() => deleteBullet(i)} className="px-1.5 py-0.5 text-[10px] bg-red-600 text-white rounded">Confirm</button>
                  ) : (
                    <button onClick={() => setConfirmDeleteBullet(i)} onBlur={() => setTimeout(() => setConfirmDeleteBullet(null), 150)}
                      className="p-1 text-gray-400 hover:text-red-600" title="Delete">
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {!editing && (
        adding ? (
          <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
            <textarea value={newContent} onChange={(e) => setNewContent(e.target.value)}
              placeholder="Describe the achievement..." rows={2} autoFocus
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <div className="flex items-center gap-3">
              <select value={newType} onChange={(e) => setNewType(e.target.value)}
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
        )
      )}
    </div>
  );
}
