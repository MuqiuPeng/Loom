"use client";

import { useState, useEffect, useRef } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { ResumeArtifact } from "@/lib/types";

interface Props {
  jobId: string;
}

export default function ResumePanel({ jobId }: Props) {
  const { data: resumes, mutate } = useSWR<ResumeArtifact[]>(
    `resumes-job-${jobId}`,
    () => api.resumes.list(jobId),
  );
  const [genLanguage, setGenLanguage] = useState<"en" | "zh">("en");
  const [starting, setStarting] = useState(false);

  const generate = async () => {
    setStarting(true);
    try {
      await api.tasks.generateResume({
        jd_record_id: jobId,
        language: genLanguage,
        format: "pdf",
      });
      // Placeholder artifact now exists in DB — refresh list
      // Small delay to ensure DB write is committed before fetch
      await new Promise((r) => setTimeout(r, 500));
      await mutate();
      // Second mutate after another delay as safety net
      setTimeout(() => mutate(), 2000);
    } catch {
      // ignore
    } finally {
      setStarting(false);
    }
  };

  // Auto-poll while any resume is generating or we just started one
  useEffect(() => {
    if (!hasGenerating(resumes) && !starting) return;
    const interval = setInterval(() => mutate(), 2000);
    return () => clearInterval(interval);
  }, [resumes, mutate, starting]);

  const toggleStar = async (id: string) => {
    await api.resumes.toggleStar(id);
    mutate();
  };

  const deleteResume = async (id: string) => {
    await api.resumes.delete(id);
    mutate();
  };

  const download = (content: string, ext: string, mime: string, id: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `resume_${id.slice(0, 8)}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Sort: in-progress first, then starred, then by date desc
  const sorted = [...(resumes || [])].sort((a, b) => {
    const aGen = isInProgress(a.status);
    const bGen = isInProgress(b.status);
    if (aGen && !bGen) return -1;
    if (bGen && !aGen) return 1;
    if (a.starred !== b.starred) return a.starred ? -1 : 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 shrink-0">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-900">Resumes</h3>
          <span className="text-[10px] text-gray-400">
            {(resumes || []).filter((r) => r.status === "completed").length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-0.5">
            {(["en", "zh"] as const).map((lang) => (
              <button key={lang}
                className={`px-2 py-0.5 text-[10px] rounded ${
                  genLanguage === lang ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-500"
                }`}
                onClick={() => setGenLanguage(lang)}
              >{lang === "en" ? "EN" : "\u4E2D\u6587"}</button>
            ))}
          </div>
          <button onClick={generate} disabled={starting}
            className="flex-1 px-3 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded-md hover:bg-indigo-700 disabled:opacity-50">
            + Generate
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {sorted.map((r) =>
          isInProgress(r.status) ? (
            <GeneratingItem key={r.id} resume={r} />
          ) : r.status === "failed" ? (
            <FailedItem key={r.id} resume={r} onDelete={() => deleteResume(r.id)} />
          ) : (
            <ResumeItem key={r.id} resume={r}
              onStar={() => toggleStar(r.id)}
              onDelete={() => deleteResume(r.id)}
              onDownload={download} />
          )
        )}
        {sorted.length === 0 && (
          <p className="text-xs text-gray-400 italic text-center py-6">No resumes yet</p>
        )}
      </div>
    </div>
  );
}

const STATUS_LABELS: Record<string, string> = {
  matching: "Matching profile...",
  selecting: "Selecting bullets...",
  generating: "Generating bullets...",
  reviewing: "Reviewing content...",
  scrutiny: "Quality check...",
  compiling: "Compiling PDF...",
};

const STATUS_PERCENT: Record<string, number> = {
  matching: 10, selecting: 20, generating: 40,
  reviewing: 60, scrutiny: 75, compiling: 90,
};

function isInProgress(status: string): boolean {
  return !["completed", "failed"].includes(status);
}

function hasGenerating(resumes: ResumeArtifact[] | undefined): boolean {
  return (resumes || []).some((r) => isInProgress(r.status));
}

function GeneratingItem({ resume }: { resume: ResumeArtifact }) {
  const label = STATUS_LABELS[resume.status] || "Processing...";
  const percent = STATUS_PERCENT[resume.status] || 5;
  return (
    <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-1.5">
        <svg className="animate-spin h-3.5 w-3.5 text-indigo-600" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="text-xs font-medium text-indigo-700">{label}</span>
        <span className="text-[10px] text-indigo-400 ml-auto">{percent}%</span>
      </div>
      <div className="w-full bg-indigo-100 rounded-full h-1">
        <div className="bg-indigo-600 h-1 rounded-full transition-all duration-700"
          style={{ width: `${percent}%` }} />
      </div>
      <p className="text-[10px] text-indigo-400 mt-1.5">
        {resume.language === "en" ? "English" : "Chinese"}
      </p>
    </div>
  );
}

function FailedItem({ resume, onDelete }: { resume: ResumeArtifact; onDelete: () => void }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-red-700">Generation failed</p>
        <button onClick={onDelete} className="text-[10px] text-red-400 hover:text-red-600">&#x2715;</button>
      </div>
    </div>
  );
}

function ResumeItem({ resume, onStar, onDelete, onDownload }: {
  resume: ResumeArtifact;
  onStar: () => void;
  onDelete: () => void;
  onDownload: (content: string, ext: string, mime: string, id: string) => void;
}) {
  const [confirmDel, setConfirmDel] = useState(false);
  return (
    <div className={`border rounded-lg p-2.5 transition-colors ${
      resume.starred ? "border-yellow-300 bg-yellow-50/50" : "border-gray-200 bg-white"
    }`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <button onClick={onStar}
              className={`text-sm transition-colors ${resume.starred ? "text-yellow-500" : "text-gray-300 hover:text-yellow-400"}`}>
              {resume.starred ? "\u2605" : "\u2606"}
            </button>
            <span className={`px-1.5 py-0.5 text-[9px] rounded font-medium ${
              resume.language === "en" ? "bg-blue-50 text-blue-600" : "bg-orange-50 text-orange-600"
            }`}>{resume.language === "en" ? "EN" : "ZH"}</span>
            {resume.has_pdf && <span className="text-[9px] text-green-600">PDF</span>}
          </div>
          <p className="text-[10px] text-gray-400 mt-1">{new Date(resume.created_at).toLocaleString()}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {resume.has_pdf && (
            <button onClick={() => window.open(`/api/resumes/${resume.id}/pdf`, "_blank")}
              className="px-1.5 py-0.5 text-[10px] bg-indigo-600 text-white rounded hover:bg-indigo-700">PDF</button>
          )}
          <button onClick={() => resume.content_md && onDownload(resume.content_md, "md", "text/markdown", resume.id)}
            disabled={!resume.content_md}
            className="px-1.5 py-0.5 text-[10px] bg-gray-100 text-gray-500 rounded hover:bg-gray-200 disabled:opacity-40">.md</button>
          <button onClick={() => resume.content_tex && onDownload(resume.content_tex, "tex", "application/x-tex", resume.id)}
            disabled={!resume.content_tex}
            className="px-1.5 py-0.5 text-[10px] bg-gray-100 text-gray-500 rounded hover:bg-gray-200 disabled:opacity-40">.tex</button>
          {confirmDel ? (
            <button onClick={onDelete} className="px-1.5 py-0.5 text-[10px] text-red-600">OK</button>
          ) : (
            <button onClick={() => setConfirmDel(true)}
              onBlur={() => setTimeout(() => setConfirmDel(false), 200)}
              className="px-1.5 py-0.5 text-[10px] text-gray-300 hover:text-red-500">&#x2715;</button>
          )}
        </div>
      </div>
    </div>
  );
}
