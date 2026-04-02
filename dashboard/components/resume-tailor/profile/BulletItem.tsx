"use client";

import { useState } from "react";
import Markdown from "react-markdown";
import { api } from "@/lib/api";
import type { BulletData, BulletType } from "@/lib/types";

const TYPE_COLORS: Record<BulletType, string> = {
  business_impact: "bg-green-100 text-green-700",
  technical_design: "bg-blue-100 text-blue-700",
  scale: "bg-orange-100 text-orange-700",
  implementation: "bg-gray-100 text-gray-600",
  collaboration: "bg-purple-100 text-purple-700",
  problem_solving: "bg-red-100 text-red-700",
};

const TYPE_LABELS: Record<BulletType, string> = {
  business_impact: "Impact",
  technical_design: "Design",
  scale: "Scale",
  implementation: "Impl",
  collaboration: "Collab",
  problem_solving: "Debug",
};

interface Props {
  bullet: BulletData;
  onUpdate: () => void;
}

export default function BulletItem({ bullet, onUpdate }: Props) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(bullet.content ?? bullet.raw_text);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.profile.updateBullet(bullet.id, { content_en: content });
      onUpdate();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    await api.profile.deleteBullet(bullet.id);
    onUpdate();
  };

  const colorClass = TYPE_COLORS[bullet.type] ?? TYPE_COLORS.implementation;
  const label = TYPE_LABELS[bullet.type] ?? bullet.type;

  return (
    <div className="group flex items-start gap-2 py-1.5">
      <span className="mt-0.5 shrink-0 w-12 text-center">
        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${colorClass}`}>
          {label}
        </span>
      </span>

      {editing ? (
        <div className="flex-1 space-y-2">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={2}
            className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <div className="flex gap-2">
            <button
              onClick={save}
              disabled={saving}
              className="px-3 py-1 bg-indigo-600 text-white text-xs rounded hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "..." : "Save"}
            </button>
            <button
              onClick={() => setEditing(false)}
              className="px-3 py-1 text-xs text-gray-500 hover:text-gray-700"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-start justify-between">
          <span className="text-sm text-gray-800 leading-snug [&_strong]:font-semibold [&_em]:italic [&_em]:text-gray-600 [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs [&_p]:inline">
            <Markdown>{bullet.content ?? bullet.raw_text}</Markdown>
          </span>
          <span className="shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-2">
            <button
              onClick={() => setEditing(true)}
              className="p-1 text-gray-400 hover:text-indigo-600"
              title="Edit"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
              </svg>
            </button>
            {confirmDelete ? (
              <button
                onClick={remove}
                className="px-1.5 py-0.5 text-[10px] bg-red-600 text-white rounded"
              >
                Confirm
              </button>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                onBlur={() => setTimeout(() => setConfirmDelete(false), 150)}
                className="p-1 text-gray-400 hover:text-red-600"
                title="Delete"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
