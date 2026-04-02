"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Lang } from "@/lib/types";

interface Props {
  profile: {
    id: string;
    name: string;
    email: string | null;
    phone: string | null;
    github: string | null;
    linkedin: string | null;
    location: string | null;
    summary: string | null;
  };
  lang: Lang;
  onUpdate: () => void;
}

const FIELDS = [
  { key: "name", label: "Name", bilingual: true },
  { key: "email", label: "Email", bilingual: false },
  { key: "phone", label: "Phone", bilingual: true },
  { key: "github", label: "GitHub", bilingual: false },
  { key: "linkedin", label: "LinkedIn", bilingual: false },
  { key: "location", label: "Location", bilingual: true },
  { key: "summary", label: "Summary", bilingual: true },
] as const;

export default function BasicInfoCard({ profile, lang, onUpdate }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const startEdit = () => {
    const initial: Record<string, string> = {};
    for (const f of FIELDS) {
      const val = profile[f.key as keyof typeof profile];
      initial[f.key] = (val as string) ?? "";
    }
    setDraft(initial);
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      for (const f of FIELDS) {
        const original = (profile[f.key as keyof typeof profile] as string) ?? "";
        if (draft[f.key] !== original) {
          await api.profile.updateBasic(f.key, draft[f.key], f.bilingual ? lang : "en");
        }
      }
      onUpdate();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Basic Information</h2>
        {!editing && (
          <button
            onClick={startEdit}
            className="text-sm text-indigo-600 hover:text-indigo-800"
          >
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-4">
          {FIELDS.map((f) => (
            <div key={f.key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {f.label}
                {f.bilingual && (
                  <span className="ml-1 text-xs text-gray-400">
                    ({lang.toUpperCase()})
                  </span>
                )}
              </label>
              {f.key === "summary" ? (
                <textarea
                  value={draft[f.key] ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, [f.key]: e.target.value })
                  }
                  rows={3}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              ) : (
                <input
                  type="text"
                  value={draft[f.key] ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, [f.key]: e.target.value })
                  }
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              )}
            </div>
          ))}
          <div className="flex gap-2 pt-2">
            <button
              onClick={save}
              disabled={saving}
              className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
            <button
              onClick={() => setEditing(false)}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
          {FIELDS.map((f) => {
            const val = profile[f.key as keyof typeof profile] as string | null;
            return (
              <div key={f.key} className={f.key === "summary" ? "col-span-2" : ""}>
                <dt className="text-xs text-gray-500">{f.label}</dt>
                <dd className="text-sm mt-0.5">
                  {val || (
                    <span className="text-gray-300 italic">Not set</span>
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
      )}
    </div>
  );
}
