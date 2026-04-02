"use client";

import useSWR from "swr";
import Header from "@/components/layout/Header";
import WorkflowRunCard from "@/components/resume-tailor/workflows/WorkflowRunCard";
import { api } from "@/lib/api";
import type { WorkflowRun } from "@/lib/types";

export default function WorkflowsPage() {
  const { data, error, mutate } = useSWR<WorkflowRun[]>(
    "/workflows",
    () => api.workflows.list()
  );

  return (
    <div className="max-w-4xl">
      <Header title="Workflows" />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-4 mb-6 text-sm">
          Failed to load workflow runs.
        </div>
      )}

      {!data && !error && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 p-5 animate-pulse h-20" />
          ))}
        </div>
      )}

      {data && data.length === 0 && (
        <div className="text-center py-16">
          <p className="text-gray-400">No workflow runs yet.</p>
          <p className="text-sm text-gray-300 mt-1">
            Generate a resume from the Jobs page to create one.
          </p>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="space-y-3">
          {data.map((run) => (
            <WorkflowRunCard key={run.id} run={run} onRetry={() => mutate()} />
          ))}
        </div>
      )}
    </div>
  );
}
