"use client";

import { useState } from "react";
import type { WorkflowRun, StepRun } from "@/lib/types";
import { api } from "@/lib/api";

const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  completed: { bg: "bg-green-50", text: "text-green-700", dot: "bg-green-500" },
  running: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
  failed: { bg: "bg-red-50", text: "text-red-700", dot: "bg-red-500" },
  pending: { bg: "bg-gray-50", text: "text-gray-500", dot: "bg-gray-400" },
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${style.bg} ${style.text}`}>
      {status === "running" ? (
        <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      ) : (
        <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
      )}
      {status}
    </span>
  );
}

function StepRow({ step }: { step: StepRun }) {
  const elapsed = (() => {
    if (!step.started_at || !step.completed_at) return null;
    const ms = new Date(step.completed_at).getTime() - new Date(step.started_at).getTime();
    return `${(ms / 1000).toFixed(1)}s`;
  })();

  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <div className="flex items-center gap-2">
        <StatusBadge status={step.status} />
        <span className="text-gray-700">{step.step_name}</span>
      </div>
      <div className="flex items-center gap-3 text-xs text-gray-400">
        {elapsed && <span>{elapsed}</span>}
        {step.error && (
          <span className="text-red-500 max-w-xs truncate" title={step.error}>
            {step.error}
          </span>
        )}
      </div>
    </div>
  );
}

interface Props {
  run: WorkflowRun;
  onRetry: () => void;
}

export default function WorkflowRunCard({ run, onRetry }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const createdAt = new Date(run.created_at).toLocaleString();

  const totalElapsed = (() => {
    const start = new Date(run.created_at).getTime();
    const end = new Date(run.updated_at).getTime();
    const ms = end - start;
    if (ms < 1000) return null;
    return `${(ms / 1000).toFixed(1)}s`;
  })();

  const handleRetry = async () => {
    setRetrying(true);
    try {
      await api.workflows.retry(run.id);
      onRetry();
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-medium text-gray-900">{run.workflow_name}</h3>
            <StatusBadge status={run.status} />
          </div>
          <p className="text-xs text-gray-400">
            {createdAt}
            {totalElapsed && ` · ${totalElapsed}`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {run.status === "failed" && (
            <button
              onClick={handleRetry}
              disabled={retrying}
              className="px-3 py-1 text-sm bg-red-50 text-red-600 rounded hover:bg-red-100 disabled:opacity-50"
            >
              {retrying ? "..." : "Retry"}
            </button>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            {expanded ? "Collapse" : "Details"}
          </button>
        </div>
      </div>

      {expanded && run.step_runs.length > 0 && (
        <div className="mt-4 pt-3 border-t border-gray-100 space-y-0.5">
          {run.step_runs
            .sort((a, b) => a.order - b.order)
            .map((step) => (
              <StepRow key={step.id} step={step} />
            ))}
        </div>
      )}
    </div>
  );
}
