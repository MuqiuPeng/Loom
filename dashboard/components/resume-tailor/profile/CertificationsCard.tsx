"use client";

import { useState } from "react";
import type { CertificationData } from "@/lib/types";
import { api } from "@/lib/api";

interface Props {
  certifications: CertificationData[];
  onUpdate: () => void;
}

export default function CertificationsCard({ certifications, onUpdate }: Props) {
  const [adding, setAdding] = useState(false);
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [draftYear, setDraftYear] = useState("");
  const [draftName, setDraftName] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async (newList: CertificationData[]) => {
    setSaving(true);
    try {
      await api.profile.updateBasic("certifications", newList);
      onUpdate();
    } finally {
      setSaving(false);
    }
  };

  const handleAdd = async () => {
    if (!draftName.trim()) return;
    await save([...certifications, { year: draftYear.trim(), name: draftName.trim() }]);
    setDraftYear("");
    setDraftName("");
    setAdding(false);
  };

  const handleDelete = async (idx: number) => {
    await save(certifications.filter((_, i) => i !== idx));
  };

  const handleEditSave = async () => {
    if (editIdx === null || !draftName.trim()) return;
    const updated = certifications.map((c, i) =>
      i === editIdx ? { year: draftYear.trim(), name: draftName.trim() } : c
    );
    await save(updated);
    setEditIdx(null);
    setDraftYear("");
    setDraftName("");
  };

  const startEdit = (idx: number) => {
    setEditIdx(idx);
    setDraftYear(certifications[idx].year);
    setDraftName(certifications[idx].name);
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Certifications</h2>
        {!adding && editIdx === null && (
          <button
            onClick={() => setAdding(true)}
            className="text-sm text-indigo-600 hover:text-indigo-800"
          >
            + Add
          </button>
        )}
      </div>

      {certifications.length === 0 && !adding && (
        <p className="text-sm text-gray-400 italic">No certifications added yet.</p>
      )}

      <div className="space-y-2">
        {certifications.map((cert, idx) => (
          <div key={idx} className="group flex items-center justify-between py-1.5">
            {editIdx === idx ? (
              <div className="flex-1 flex items-center gap-2">
                <input
                  value={draftYear}
                  onChange={(e) => setDraftYear(e.target.value)}
                  placeholder="Year"
                  className="w-20 border border-gray-300 rounded px-2 py-1 text-sm"
                />
                <input
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  placeholder="Certification name"
                  className="flex-1 border border-gray-300 rounded px-2 py-1 text-sm"
                />
                <button
                  onClick={handleEditSave}
                  disabled={saving}
                  className="text-xs text-indigo-600 hover:text-indigo-800"
                >
                  Save
                </button>
                <button
                  onClick={() => { setEditIdx(null); setDraftYear(""); setDraftName(""); }}
                  className="text-xs text-gray-400 hover:text-gray-600"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-400 font-mono w-12">{cert.year}</span>
                  <span className="text-sm text-gray-800">{cert.name}</span>
                </div>
                <div className="hidden group-hover:flex items-center gap-2">
                  <button
                    onClick={() => startEdit(idx)}
                    className="text-xs text-gray-400 hover:text-indigo-600"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(idx)}
                    className="text-xs text-gray-400 hover:text-red-600"
                  >
                    Delete
                  </button>
                </div>
              </>
            )}
          </div>
        ))}

        {adding && (
          <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
            <input
              value={draftYear}
              onChange={(e) => setDraftYear(e.target.value)}
              placeholder="Year"
              className="w-20 border border-gray-300 rounded px-2 py-1 text-sm"
              autoFocus
            />
            <input
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              placeholder="Certification name"
              className="flex-1 border border-gray-300 rounded px-2 py-1 text-sm"
            />
            <button
              onClick={handleAdd}
              disabled={saving || !draftName.trim()}
              className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-40"
            >
              {saving ? "..." : "Add"}
            </button>
            <button
              onClick={() => { setAdding(false); setDraftYear(""); setDraftName(""); }}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
