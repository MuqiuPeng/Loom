"use client";

import { useState, useEffect, useRef } from "react";
import useSWR from "swr";
import Header from "@/components/layout/Header";
import JobSidebar from "@/components/resume-tailor/jobs/JobSidebar";
import JobDetail from "@/components/resume-tailor/jobs/JobDetail";
import ResumePanel from "@/components/resume-tailor/jobs/ResumePanel";
import { api } from "@/lib/api";
import type { JDRecord, AnalyzeJDOutput } from "@/lib/types";

export default function JobsPage() {
  const { data: jobs, error, mutate } = useSWR<JDRecord[]>("/jobs", () => api.jobs.list());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inputOpen, setInputOpen] = useState(false);
  const [jdText, setJdText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [analyzeTaskId, setAnalyzeTaskId] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeJDOutput | null>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const selectedJob = jobs?.find((j) => j.id === selectedId) ?? null;

  useEffect(() => { if (inputOpen && textareaRef.current) textareaRef.current.focus(); }, [inputOpen]);

  const handleAnalyze = async () => {
    if (!jdText.trim()) return;
    setIsAnalyzing(true);
    setAnalyzeError(null);
    setAnalyzeResult(null);
    setInputOpen(false);
    try {
      const { task_id } = await api.tasks.analyzeJD(jdText);
      setAnalyzeTaskId(task_id);
    } catch (e: unknown) {
      setAnalyzeError(e instanceof Error ? e.message : "Failed");
      setIsAnalyzing(false);
      setInputOpen(true);
    }
  };

  useEffect(() => {
    if (!analyzeTaskId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const task = await api.tasks.get(analyzeTaskId);
        if (cancelled) return;
        if (task.status === "completed") {
          const output = task.output_data as unknown as AnalyzeJDOutput;
          setAnalyzeResult(output);
          setAnalyzeTaskId(null);
          setIsAnalyzing(false);
          setJdText("");
          await mutate();
          if (output.jd_record_id) setSelectedId(output.jd_record_id);
          return;
        }
        if (task.status === "failed") {
          setAnalyzeError(task.error || "Analysis failed");
          setAnalyzeTaskId(null);
          setIsAnalyzing(false);
          return;
        }
        pollingRef.current = setTimeout(poll, 2000);
      } catch { if (!cancelled) pollingRef.current = setTimeout(poll, 2000); }
    };
    pollingRef.current = setTimeout(poll, 2000);
    return () => { cancelled = true; if (pollingRef.current) clearTimeout(pollingRef.current); };
  }, [analyzeTaskId, mutate]);

  const handleSelect = (id: string) => { setSelectedId(id); setAnalyzeResult(null); setInputOpen(false); };
  const handleCancelInput = () => { setInputOpen(false); setJdText(""); };

  return (
    <div className="max-w-[90rem]">
      <Header title="Jobs" />

      {(error || analyzeError) && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-4 mb-6 text-sm flex items-center justify-between">
          <span>{analyzeError || "Failed to load jobs."}</span>
          {analyzeError && <button onClick={() => setAnalyzeError(null)} className="text-red-500 hover:text-red-700 ml-2">&#x2715;</button>}
        </div>
      )}

      {!jobs && !error && <div className="bg-white rounded-lg border border-gray-200 h-96 animate-pulse" />}

      {jobs && inputOpen && (
        <div className="bg-white rounded-lg border border-gray-200 h-[calc(100vh-10rem)] flex flex-col p-4 md:p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Paste Job Description</h2>
            <button onClick={handleCancelInput} className="text-sm text-gray-400 hover:text-gray-600">Cancel</button>
          </div>
          <textarea ref={textareaRef}
            className="flex-1 w-full px-4 py-3 border border-gray-300 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 placeholder-gray-400"
            placeholder="Paste the full job description here..."
            value={jdText} onChange={(e) => setJdText(e.target.value)} />
          <button onClick={handleAnalyze} disabled={!jdText.trim()}
            className="mt-4 self-end px-8 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed">
            Analyze
          </button>
        </div>
      )}

      {jobs && !inputOpen && (
        <div className="flex flex-col md:flex-row bg-white rounded-lg border border-gray-200 h-[calc(100vh-10rem)]">
          {/* Left: JD list */}
          <div className="w-full md:w-64 shrink-0 border-b md:border-b-0 md:border-r border-gray-200 flex flex-col overflow-hidden">
            <div className="px-3 py-2.5 border-b border-gray-200 shrink-0">
              {isAnalyzing ? (
                <div className="flex items-center gap-2 px-1">
                  <svg className="animate-spin h-3.5 w-3.5 text-indigo-600" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="text-sm text-indigo-700 font-medium">Analyzing...</span>
                </div>
              ) : (
                <button onClick={() => setInputOpen(true)}
                  className="w-full px-3 py-1.5 text-sm font-medium text-indigo-600 border border-dashed border-indigo-300 rounded-lg hover:bg-indigo-50 flex items-center justify-center gap-1.5">
                  <span className="text-lg leading-none">+</span> Add JD
                </button>
              )}
            </div>
            <div className="max-h-60 md:max-h-none flex-1 overflow-y-auto">
              <JobSidebar jobs={jobs} selectedId={selectedId} onSelect={handleSelect} />
            </div>
          </div>

          {/* Middle: JD detail */}
          <div className="flex-1 min-w-0 border-b md:border-b-0 md:border-r border-gray-200">
            {selectedJob ? (
              <JobDetail
                job={selectedJob}
                analyzeResult={analyzeResult && selectedId === analyzeResult.jd_record_id ? analyzeResult : null}
                onDelete={() => { setSelectedId(null); setAnalyzeResult(null); mutate(); }}
                onGenerated={() => mutate()}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                {jobs.length > 0 ? "Select a job to view details" : "No jobs yet \u2014 click \"+ Add JD\" to get started."}
              </div>
            )}
          </div>

          {/* Right: Resume panel (only when JD selected) */}
          {selectedJob && (
            <div className="w-full md:w-80 shrink-0 overflow-hidden flex flex-col">
              <ResumePanel jobId={selectedJob.id} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
