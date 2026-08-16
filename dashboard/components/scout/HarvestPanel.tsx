"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Harvest, HarvestSelection, ScoutLead } from "@/lib/types";

const EMPTY_SELECTION: HarvestSelection = {
  images: [],
  menu: [],
  use_hours: true,
  use_about: true,
  highlight: null,
};

/** Harvests saved before `selection` existed have no such key, and the API
 * hands back the stored JSON untouched. Fill the gap here so old rows don't
 * need a migration. */
function normalise(harvest: Harvest): Harvest {
  return {
    ...harvest,
    images: harvest.images ?? [],
    menu: harvest.menu ?? [],
    pages_read: harvest.pages_read ?? [],
    socials: harvest.socials ?? {},
    selection: { ...EMPTY_SELECTION, ...(harvest.selection ?? {}) },
  };
}

/** Empty selection means "use everything" — a fresh harvest is usable as-is,
 * and ticking things off is an optional narrowing step. */
function isPicked(list: string[], value: string): boolean {
  return list.length === 0 || list.includes(value);
}

function toggle(list: string[], value: string, all: string[]): string[] {
  // First click on an untouched selection has to materialise the full list,
  // otherwise unticking one item would read as "select only that one".
  const current = list.length === 0 ? all : list;
  return current.includes(value)
    ? current.filter((v) => v !== value)
    : [...current, value];
}

export default function HarvestPanel({
  lead,
  onSaved,
}: {
  lead: ScoutLead;
  onSaved: () => void;
}) {
  const harvest = lead.harvest;
  const [draft, setDraft] = useState<Harvest | null>(
    harvest ? normalise(harvest) : null
  );
  const [saving, setSaving] = useState(false);
  const [newImage, setNewImage] = useState("");

  if (!harvest || !draft) return null;
  const pick = draft.selection;
  const allImages = draft.images;
  const allMenu = draft.menu.map((m) => m.name);

  function update(next: Partial<Harvest["selection"]>) {
    setDraft((d) => (d ? { ...d, selection: { ...d.selection, ...next } } : d));
  }

  async function persist() {
    if (!draft) return;
    setSaving(true);
    try {
      await api.scout.updateLead(lead.id, { harvest: draft });
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  function addImage() {
    const url = newImage.trim();
    if (!url.startsWith("http")) return;
    setDraft((d) =>
      d
        ? {
            ...d,
            images: d.images.includes(url) ? d.images : [...d.images, url],
            selection: {
              ...d.selection,
              images: d.selection.images.length
                ? [...d.selection.images, url]
                : [],
            },
          }
        : d
    );
    setNewImage("");
  }

  const pickedImages = allImages.filter((i) => isPicked(pick.images, i)).length;
  const pickedMenu = allMenu.filter((m) => isPicked(pick.menu, m)).length;

  return (
    <div className="mt-3 border border-gray-200 rounded-lg p-3 bg-gray-50/50">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-gray-500">
          Harvested from {draft.pages_read.length} page
          {draft.pages_read.length === 1 ? "" : "s"} · {pickedImages}/
          {allImages.length} images · {pickedMenu}/{allMenu.length} menu items
          picked
        </p>
        <button
          onClick={persist}
          disabled={saving}
          className="px-2.5 py-1 text-xs rounded bg-indigo-600 text-white font-medium hover:bg-indigo-700 disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save selection"}
        </button>
      </div>

      {draft.error && (
        <p className="mb-3 text-xs text-amber-700">{draft.error}</p>
      )}

      {/* Images — click a thumbnail to include or exclude it. */}
      {allImages.length > 0 && (
        <div className="mb-3">
          <p className="text-[11px] uppercase tracking-wide text-gray-400 mb-1.5">
            Images
          </p>
          <div className="flex flex-wrap gap-2">
            {allImages.map((url) => {
              const on = isPicked(pick.images, url);
              return (
                <button
                  key={url}
                  onClick={() =>
                    update({ images: toggle(pick.images, url, allImages) })
                  }
                  title={url}
                  className={`relative w-20 h-20 rounded overflow-hidden border-2 transition-all ${
                    on
                      ? "border-indigo-500"
                      : "border-transparent opacity-30 hover:opacity-60"
                  }`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={url}
                    alt=""
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                  {on && (
                    <span className="absolute top-0.5 right-0.5 bg-indigo-600 text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center">
                      ✓
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          <div className="mt-2 flex gap-2">
            <input
              value={newImage}
              onChange={(e) => setNewImage(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addImage()}
              placeholder="Paste an image URL — e.g. one you picked off their Instagram"
              className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded"
            />
            <button
              onClick={addImage}
              className="px-2.5 py-1 text-xs rounded border border-gray-200 text-gray-600 hover:bg-white"
            >
              Add
            </button>
          </div>
        </div>
      )}

      {/* Menu — untick anything you don't want on the demo. */}
      {draft.menu.length > 0 && (
        <div className="mb-3">
          <p className="text-[11px] uppercase tracking-wide text-gray-400 mb-1.5">
            Menu
          </p>
          <div className="flex flex-wrap gap-1.5">
            {draft.menu.map((item, i) => {
              const on = isPicked(pick.menu, item.name);
              return (
                <button
                  key={`${item.name}-${i}`}
                  onClick={() =>
                    update({ menu: toggle(pick.menu, item.name, allMenu) })
                  }
                  className={`px-2 py-1 rounded text-xs border transition-colors ${
                    on
                      ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                      : "border-gray-200 text-gray-300 line-through"
                  }`}
                >
                  {item.name}
                  {item.price && (
                    <span className="ml-1 opacity-60">{item.price}</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Facts */}
      <div className="space-y-1.5 text-xs">
        {draft.hours && (
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={pick.use_hours}
              onChange={(e) => update({ use_hours: e.target.checked })}
              className="mt-0.5"
            />
            <span className="text-gray-600">
              <span className="text-gray-400">Hours: </span>
              {draft.hours}
            </span>
          </label>
        )}
        {draft.about && (
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={pick.use_about}
              onChange={(e) => update({ use_about: e.target.checked })}
              className="mt-0.5"
            />
            <span className="text-gray-600">
              <span className="text-gray-400">About: </span>
              {draft.about}
            </span>
          </label>
        )}
        {(draft.address || draft.phone) && (
          <p className="text-gray-500 pl-6">
            {draft.address} {draft.phone}
          </p>
        )}
      </div>

      {/* Socials — the manual route to their Instagram photos. */}
      {Object.keys(draft.socials).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-3">
          {Object.entries(draft.socials).map(([platform, handle]) => (
            <a
              key={platform}
              href={
                platform === "instagram"
                  ? `https://instagram.com/${handle}`
                  : `https://${platform}.com/${handle}`
              }
              target="_blank"
              rel="noreferrer noopener"
              className="text-xs text-indigo-600 hover:underline"
            >
              {platform}: {handle} ↗
            </a>
          ))}
        </div>
      )}

      <label className="block mt-3">
        <span className="text-[11px] uppercase tracking-wide text-gray-400">
          Lead the demo on
        </span>
        <input
          value={pick.highlight || ""}
          onChange={(e) => update({ highlight: e.target.value || null })}
          placeholder="e.g. their single-origin filter, or the courtyard"
          className="mt-1 w-full px-2 py-1 text-xs border border-gray-200 rounded"
        />
      </label>
    </div>
  );
}
