"use client";

import type { ResumeArtifact } from "@/lib/types";

/** The resume itself, in a panel rather than an accordion.
 *
 * The inline expansion pushed every row below it down the page, so comparing
 * two resumes meant scrolling past the whole of the first. A panel keeps the
 * list still and lets one row after another be inspected in place. */
export default function ResumeDetail({
  resume,
  onClose,
  onDownload,
}: {
  resume: ResumeArtifact;
  onClose: () => void;
  onDownload: (content: string, ext: string, mime: string, id: string) => void;
}) {
  return (
    <div className="h-full flex flex-col">
      <header className="px-6 py-4 border-b border-gray-200 flex items-start justify-between gap-4 shrink-0">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-gray-900 truncate">
            {resume.jd_title || "Resume"}
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {resume.jd_company && <span>{resume.jd_company} · </span>}
            {resume.language === "en" ? "English" : "中文"} ·{" "}
            {new Date(resume.created_at).toLocaleString()}
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-700 text-xl leading-none shrink-0"
          aria-label="Close"
        >
          ×
        </button>
      </header>

      <div className="px-6 py-3 border-b border-gray-100 flex flex-wrap gap-2 shrink-0">
        {resume.has_pdf && (
          <button
            onClick={() => window.open(`/api/resumes/${resume.id}/pdf`, "_blank")}
            className="px-3 py-1.5 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700"
          >
            Open PDF
          </button>
        )}
        <button
          onClick={() =>
            resume.content_md &&
            onDownload(resume.content_md, "md", "text/markdown", resume.id)
          }
          disabled={!resume.content_md}
          className="px-3 py-1.5 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 disabled:opacity-40"
        >
          .md
        </button>
        <button
          onClick={() =>
            resume.content_tex &&
            onDownload(resume.content_tex, "tex", "application/x-tex", resume.id)
          }
          disabled={!resume.content_tex}
          className="px-3 py-1.5 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 disabled:opacity-40"
        >
          .tex
        </button>
        <button
          onClick={() =>
            navigator.clipboard.writeText(resume.content_md || "")
          }
          disabled={!resume.content_md}
          className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-800 disabled:opacity-40"
        >
          copy markdown
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        <pre className="text-[12px] text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">
          {resume.content_md || "No content"}
        </pre>
      </div>
    </div>
  );
}
