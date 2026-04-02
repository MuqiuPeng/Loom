"use client";

import type { ProfileData } from "@/lib/types";

interface TimelineEntry {
  id: string;
  type: "experience" | "project" | "education";
  title: string;
  subtitle: string;
  start: string | null;
  end: string | null;
  bullets: number;
  projects?: number;
  color: string;
  dotColor: string;
}

interface Props {
  data: ProfileData;
}

function parseDate(s: string | null): Date | null {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function formatPeriod(start: string | null, end: string | null): string {
  if (!start) return "";
  const s = start.slice(0, 7);
  const e = end ? end.slice(0, 7) : "Present";
  return `${s} — ${e}`;
}

function sortKey(entry: TimelineEntry): number {
  const d = parseDate(entry.start);
  return d ? -d.getTime() : 0;
}

export default function Timeline({ data }: Props) {
  const entries: TimelineEntry[] = [];

  // Experiences
  for (const e of data.experiences) {
    entries.push({
      id: `exp-${e.id}`,
      type: "experience",
      title: e.company,
      subtitle: e.title,
      start: e.start_date,
      end: e.end_date,
      bullets: e.bullets.length,
      projects: (e.projects ?? []).length,
      color: "bg-indigo-50 border-indigo-200",
      dotColor: "bg-indigo-500",
    });
  }

  // Standalone projects (including education-linked)
  const eduMap = new Map(data.education.map((e) => [e.id, e.institution]));
  for (const p of data.projects) {
    const linkedEdu = p.education_id ? eduMap.get(p.education_id) : null;
    entries.push({
      id: `proj-${p.id}`,
      type: "project",
      title: p.name,
      subtitle: linkedEdu ? `@ ${linkedEdu}` : (p.role ?? "Project"),
      start: p.start_date,
      end: p.end_date,
      bullets: p.bullets.length,
      color: "bg-emerald-50 border-emerald-200",
      dotColor: "bg-emerald-500",
    });
  }

  // Linked projects (under experiences)
  for (const e of data.experiences) {
    for (const p of e.projects ?? []) {
      entries.push({
        id: `proj-${p.id}`,
        type: "project",
        title: p.name,
        subtitle: `@ ${e.company}`,
        start: p.start_date ?? e.start_date,
        end: p.end_date ?? e.end_date,
        bullets: p.bullets.length,
        color: "bg-emerald-50 border-emerald-200",
        dotColor: "bg-emerald-500",
      });
    }
  }

  // Education
  for (const e of data.education) {
    entries.push({
      id: `edu-${e.id}`,
      type: "education",
      title: e.institution,
      subtitle: [e.degree, e.field].filter(Boolean).join(" in "),
      start: e.start_date,
      end: e.end_date,
      bullets: 0,
      color: "bg-amber-50 border-amber-200",
      dotColor: "bg-amber-500",
    });
  }

  entries.sort((a, b) => sortKey(a) - sortKey(b));

  const TYPE_LABELS: Record<string, string> = {
    experience: "Work",
    project: "Project",
    education: "Education",
  };

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-[7px] top-3 bottom-3 w-px bg-gray-200" />

      <div className="space-y-4">
        {entries.map((entry) => (
          <div key={entry.id} className="relative flex items-start gap-4 pl-6">
            {/* Dot */}
            <div className={`absolute left-0 top-2.5 w-[15px] h-[15px] rounded-full border-2 border-white ${entry.dotColor} shadow-sm`} />

            {/* Card */}
            <div className={`flex-1 rounded-lg border p-4 ${entry.color}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-gray-900">{entry.title}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                      entry.type === "experience" ? "bg-indigo-100 text-indigo-700" :
                      entry.type === "project" ? "bg-emerald-100 text-emerald-700" :
                      "bg-amber-100 text-amber-700"
                    }`}>
                      {TYPE_LABELS[entry.type]}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">{entry.subtitle}</p>
                </div>
                <span className="text-xs text-gray-400 shrink-0 ml-2">
                  {formatPeriod(entry.start, entry.end)}
                </span>
              </div>

              {(entry.bullets > 0 || (entry.projects ?? 0) > 0) && (
                <div className="flex items-center gap-3 mt-2">
                  {entry.bullets > 0 && (
                    <span className="text-xs text-gray-400">{entry.bullets} bullets</span>
                  )}
                  {(entry.projects ?? 0) > 0 && (
                    <span className="text-xs text-gray-400">{entry.projects} projects</span>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {entries.length === 0 && (
        <p className="text-sm text-gray-400 italic pl-6">No entries yet.</p>
      )}
    </div>
  );
}
