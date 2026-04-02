"use client";

import type { JDRecord } from "@/lib/types";

const SCORE_COLORS: Record<string, string> = {
  high: "bg-green-100 text-green-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-orange-100 text-orange-700",
  very_low: "bg-red-100 text-red-700",
};

function scoreColor(score: number | null): string {
  if (score === null) return "bg-gray-100 text-gray-500";
  if (score >= 8) return SCORE_COLORS.high;
  if (score >= 6) return SCORE_COLORS.medium;
  if (score >= 4) return SCORE_COLORS.low;
  return SCORE_COLORS.very_low;
}

interface Props {
  jobs: JDRecord[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function JobSidebar({ jobs, selectedId, onSelect }: Props) {
  if (jobs.length === 0) {
    return (
      <p className="p-4 text-sm text-gray-400 italic">No jobs found.</p>
    );
  }

  return (
    <>
      {jobs.map((job) => (
        <button
          key={job.id}
          onClick={() => onSelect(job.id)}
          className={`w-full text-left px-4 py-3 border-b border-gray-100 transition-colors ${
            selectedId === job.id
              ? "bg-indigo-50"
              : "hover:bg-gray-50"
          }`}
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-gray-900 truncate pr-2">
              {job.title}
            </p>
            {job.match_score !== null && (
              <span
                className={`shrink-0 px-1.5 py-0.5 rounded text-xs font-medium ${scoreColor(
                  job.match_score
                )}`}
              >
                {job.match_score}
              </span>
            )}
          </div>
          {job.company && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">
              {job.company}
            </p>
          )}
          <p className="text-[10px] text-gray-400 mt-1">
            {new Date(job.created_at).toLocaleDateString()}
          </p>
        </button>
      ))}
    </>
  );
}
