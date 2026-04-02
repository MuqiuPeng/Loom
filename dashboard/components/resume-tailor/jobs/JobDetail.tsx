"use client";

import { useState, useEffect } from "react";
import type { JDRecord, AnalyzeJDOutput } from "@/lib/types";
import { api } from "@/lib/api";

interface Props {
  job: JDRecord;
  analyzeResult: AnalyzeJDOutput | null;
  onDelete: () => void;
  onGenerated: () => void;
}

export default function JobDetail({ job, analyzeResult, onDelete, onGenerated }: Props) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  const scoreColor = (() => {
    if (job.match_score === null) return "bg-gray-100 text-gray-600";
    if (job.match_score >= 8) return "bg-green-100 text-green-700";
    if (job.match_score >= 6) return "bg-yellow-100 text-yellow-700";
    if (job.match_score >= 4) return "bg-orange-100 text-orange-700";
    return "bg-red-100 text-red-700";
  })();

  const handleDelete = async () => {
    await api.jobs.delete(job.id);
    setConfirmDelete(false);
    onDelete();
  };

  return (
    <div className="flex-1 p-4 md:p-6 overflow-y-auto">
      {/* Title & Score */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-gray-900">{job.title}</h2>
          {job.company && <p className="text-gray-500 text-sm mt-0.5">{job.company}</p>}
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${scoreColor}`}>
            {job.match_score !== null ? `${job.match_score}/10` : "N/A"}
          </span>
          {confirmDelete ? (
            <button onClick={handleDelete} className="text-xs text-red-600 hover:text-red-800">Confirm</button>
          ) : (
            <button onClick={() => setConfirmDelete(true)}
              onBlur={() => setTimeout(() => setConfirmDelete(false), 200)}
              className="text-xs text-gray-400 hover:text-red-600">Delete</button>
          )}
        </div>
      </div>

      {/* Skills */}
      {job.required_skills.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-semibold text-gray-500 mb-1.5">Required Skills</h3>
          <div className="flex flex-wrap gap-1">
            {job.required_skills.map((s) => (
              <span key={s} className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-[11px]">{s}</span>
            ))}
          </div>
        </div>
      )}
      {job.preferred_skills.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-semibold text-gray-500 mb-1.5">Preferred</h3>
          <div className="flex flex-wrap gap-1">
            {job.preferred_skills.map((s) => (
              <span key={s} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-[11px]">{s}</span>
            ))}
          </div>
        </div>
      )}

      {/* Analyze result */}
      {analyzeResult && analyzeResult.matched.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-semibold text-gray-500 mb-1.5">Matched</h3>
          {analyzeResult.matched.map((m, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs mb-0.5">
              <span className="text-green-600 mt-0.5">&#10003;</span>
              <span className="text-gray-700">{m.requirement}</span>
            </div>
          ))}
        </div>
      )}
      {analyzeResult && analyzeResult.hard_skill_gaps.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-semibold text-gray-500 mb-1.5">Gaps</h3>
          {analyzeResult.hard_skill_gaps.map((gap, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs mb-0.5">
              <span className="text-red-500 mt-0.5">&#10007;</span>
              <span className="text-gray-700">{gap}</span>
            </div>
          ))}
        </div>
      )}
      {analyzeResult?.reasoning && (
        <div className="mb-4 p-2.5 bg-gray-50 rounded-lg">
          <p className="text-[10px] text-gray-500 mb-0.5">Analysis</p>
          <p className="text-xs text-gray-700">{analyzeResult.reasoning}</p>
        </div>
      )}
      {!analyzeResult && job.key_requirements.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-semibold text-gray-500 mb-1.5">Key Requirements</h3>
          <ul className="list-disc list-inside text-xs text-gray-600 space-y-0.5">
            {job.key_requirements.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      {/* JD Text */}
      <details className="mb-4">
        <summary className="text-xs font-semibold text-gray-500 cursor-pointer hover:text-indigo-600">
          Full Job Description
        </summary>
        <div className="bg-gray-50 rounded-md p-3 text-xs text-gray-600 whitespace-pre-wrap max-h-60 overflow-y-auto mt-1.5">
          {job.raw_text}
        </div>
      </details>
    </div>
  );
}
