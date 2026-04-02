"use client";

import { useState } from "react";
import type { ResumeArtifact } from "@/lib/types";
import { api } from "@/lib/api";

interface Props {
  resume: ResumeArtifact;
  onDelete: () => void;
}

export default function ResumeCard({ resume, onDelete }: Props) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [preview, setPreview] = useState<"md" | "tex" | null>(null);

  const createdDate = new Date(resume.created_at).toLocaleDateString();

  const download = (content: string, ext: string, mime: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `resume_${resume.id.slice(0, 8)}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.resumes.delete(resume.id);
      onDelete();
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  return (
    <>
      <div className="bg-white rounded-lg border border-gray-200 p-5 flex flex-col">
        {/* Header */}
        <div className="mb-3">
          <h3 className="font-semibold text-gray-900">
            {resume.jd_title || "Resume"}
          </h3>
          {resume.jd_company && (
            <p className="text-sm text-gray-500">{resume.jd_company}</p>
          )}
        </div>

        {/* Meta */}
        <div className="text-xs text-gray-400 space-y-1 mb-4">
          <p>{createdDate}</p>
          <div className="flex items-center gap-2">
            <span>{resume.language === "en" ? "English" : "Chinese"}</span>
            {resume.has_pdf && (
              <span className="text-green-600 font-medium">PDF ready</span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="mt-auto space-y-2">
          {/* Download row */}
          <div className="flex items-center gap-1.5">
            {resume.has_pdf && (
              <button
                onClick={() =>
                  window.open(`/api/resumes/${resume.id}/pdf`, "_blank")
                }
                className="px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
              >
                View PDF
              </button>
            )}
            <button
              onClick={() =>
                resume.content_md &&
                download(resume.content_md, "md", "text/markdown")
              }
              disabled={!resume.content_md}
              className="px-3 py-1.5 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 disabled:opacity-40"
            >
              .md
            </button>
            <button
              onClick={() =>
                resume.content_tex &&
                download(
                  resume.content_tex,
                  "tex",
                  "application/x-tex"
                )
              }
              disabled={!resume.content_tex}
              className="px-3 py-1.5 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 disabled:opacity-40"
            >
              .tex
            </button>
          </div>

          {/* Preview + Delete row */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPreview(preview ? null : "md")}
              disabled={!resume.content_md}
              className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-40"
            >
              {preview ? "Close Preview" : "Preview"}
            </button>
            <span className="text-gray-200">|</span>
            {confirmDelete ? (
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
              >
                {deleting ? "..." : "Confirm Delete"}
              </button>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                onBlur={() =>
                  setTimeout(() => setConfirmDelete(false), 200)
                }
                className="text-xs text-red-500 hover:text-red-700"
              >
                Delete
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Preview Modal */}
      {preview && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-2 md:p-8">
          <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[85vh] flex flex-col">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-gray-900">
                  {resume.jd_title || "Resume"} — Preview
                </h3>
                <div className="flex gap-1 ml-3">
                  <button
                    onClick={() => setPreview("md")}
                    className={`px-2 py-0.5 text-xs rounded ${
                      preview === "md"
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-100 text-gray-600"
                    }`}
                  >
                    Markdown
                  </button>
                  <button
                    onClick={() => setPreview("tex")}
                    disabled={!resume.content_tex}
                    className={`px-2 py-0.5 text-xs rounded disabled:opacity-40 ${
                      preview === "tex"
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-100 text-gray-600"
                    }`}
                  >
                    LaTeX
                  </button>
                </div>
              </div>
              <button
                onClick={() => setPreview(null)}
                className="text-gray-400 hover:text-gray-600 text-lg"
              >
                &#x2715;
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
              <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">
                {preview === "tex"
                  ? resume.content_tex || "No LaTeX content"
                  : resume.content_md || "No Markdown content"}
              </pre>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
