import type {
  Lang,
  ProfileData,
  ResumeArtifact,
  JDRecord,
  WorkflowRun,
  TaskStatus,
  LogEntry,
  LogStats,
  ScoutCandidate,
  AreaResult,
  AreaSuggestion,
  DemoPlan,
  Harvest,
  ScoutLead,
  ScoutStats,
  ScoutCountry,
  Industry,
  LeadKind,
} from "./types";

const API_BASE = "/api";

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export const api = {
  profile: {
    get: (lang: Lang = "en") =>
      request<ProfileData>(`/profile?lang=${lang}`),

    updateBasic: (field: string, value: unknown, lang: Lang = "en") =>
      request<{ status: string }>("/profile/basic", {
        method: "PATCH",
        body: JSON.stringify({ field, value, lang }),
      }),

    // Experience
    addExperience: (data: Record<string, unknown>) =>
      request<{ status: string; id: string }>("/profile/experience", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    updateExperience: (id: string, data: Record<string, unknown>) =>
      request<{ status: string }>(`/profile/experience/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ data }),
      }),

    deleteExperience: (id: string) =>
      request<{ status: string }>(`/profile/experience/${id}`, {
        method: "DELETE",
      }),

    // Bullet
    addBullet: (data: {
      experience_id: string;
      content_en: string;
      type?: string;
      star_data?: Record<string, string>;
      tech_stack?: { name: string }[];
    }) =>
      request<{ status: string; id: string }>("/profile/bullet", {
        method: "POST",
        body: JSON.stringify({ ...data, auto_translate: true }),
      }),

    updateBullet: (id: string, data: Record<string, unknown>) =>
      request<{ status: string }>(`/profile/bullet/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ data }),
      }),

    deleteBullet: (id: string) =>
      request<{ status: string }>(`/profile/bullet/${id}`, {
        method: "DELETE",
      }),

    // Project
    addProject: (data: Record<string, unknown>) =>
      request<{ status: string; id: string }>("/profile/project", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    updateProject: (id: string, data: Record<string, unknown>) =>
      request<{ status: string }>(`/profile/project/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ data }),
      }),

    deleteProject: (id: string) =>
      request<{ status: string }>(`/profile/project/${id}`, {
        method: "DELETE",
      }),

    // Education
    addEducation: (data: Record<string, unknown>) =>
      request<{ status: string; id: string }>("/profile/education", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    updateEducation: (id: string, data: Record<string, unknown>) =>
      request<{ status: string }>(`/profile/education/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ data }),
      }),

    deleteEducation: (id: string) =>
      request<{ status: string }>(`/profile/education/${id}`, {
        method: "DELETE",
      }),

    // Skill
    addSkill: (data: Record<string, unknown>) =>
      request<{ status: string; id: string }>("/profile/skill", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    updateSkill: (id: string, data: Record<string, unknown>) =>
      request<{ status: string }>(`/profile/skill/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ data }),
      }),

    deleteSkill: (id: string) =>
      request<{ status: string }>(`/profile/skill/${id}`, {
        method: "DELETE",
      }),
  },

  resumes: {
    list: (jdRecordId?: string) => {
      const qs = jdRecordId ? `?jd_record_id=${jdRecordId}` : "";
      return request<ResumeArtifact[]>(`/resumes${qs}`);
    },
    delete: (id: string) =>
      request<{ status: string }>(`/resumes/${id}`, { method: "DELETE" }),
    toggleStar: (id: string) =>
      request<{ starred: boolean }>(`/resumes/${id}/star`, { method: "PATCH" }),
  },

  jobs: {
    list: () => request<JDRecord[]>("/jobs"),
    get: (id: string) => request<JDRecord>(`/jobs/${id}`),
    delete: (id: string) =>
      request<{ status: string }>(`/jobs/${id}`, { method: "DELETE" }),
  },

  tasks: {
    analyzeJD: (jdText: string) =>
      request<{ task_id: string }>("/tasks/analyze-jd", {
        method: "POST",
        body: JSON.stringify({ jd_text: jdText }),
      }),

    generateResume: (data: {
      jd_record_id: string;
      language: string;
      format: string;
    }) =>
      request<{ task_id: string }>("/tasks/generate-resume", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    generateGenericResume: (data?: {
      language?: string;
      format?: string;
      focus?: string;
    }) =>
      request<{ task_id: string }>("/tasks/generate-resume-generic", {
        method: "POST",
        body: JSON.stringify(data ?? {}),
      }),

    get: (taskId: string) =>
      request<TaskStatus>(`/tasks/${taskId}`),
  },

  workflows: {
    list: () => request<WorkflowRun[]>("/workflows"),
    run: (data: { workflow: string; data: Record<string, unknown> }) =>
      request<{ workflow_run_id: string; status: string }>(
        "/workflow/run",
        { method: "POST", body: JSON.stringify(data) }
      ),
    retry: (runId: string) =>
      request<{ status: string }>(`/workflows/${runId}/retry`, {
        method: "POST",
      }),
  },

  scout: {
    search: (data: {
      query?: string;
      industries?: string[];
      near?: string;
      country?: string;
      radius_m?: number;
      limit?: number;
      enrich?: boolean;
    }) =>
      request<{
        stats: ScoutStats;
        queries: string[];
        country: string | null;
        candidates: ScoutCandidate[];
      }>("/scout/search", { method: "POST", body: JSON.stringify(data) }),

    industries: () =>
      request<{ industries: Industry[] }>("/scout/industries"),

    areas: () =>
      request<{
        areas: AreaSuggestion[];
        countries: ScoutCountry[];
        avoid: { note?: string; patterns?: string[] };
        default: string[];
      }>("/scout/areas"),

    survey: (query: string, areas: string[], limit = 20) =>
      request<{ query: string; areas: AreaResult[] }>("/scout/survey", {
        method: "POST",
        body: JSON.stringify({ query, areas, limit }),
      }),

    // `kind` is required rather than defaulted: a lead saved under the wrong
    // campaign is the one that later receives the wrong kind of email.
    saveLeads: (candidates: Record<string, unknown>[], kind: LeadKind) =>
      request<{ created: number; updated: number }>("/scout/leads", {
        method: "POST",
        body: JSON.stringify({ candidates, kind }),
      }),

    listLeads: (kind: LeadKind, status?: string) => {
      const params = new URLSearchParams({ kind });
      if (status && status !== "all") params.set("status", status);
      return request<{ total: number; leads: ScoutLead[] }>(
        `/scout/leads?${params}`
      );
    },

    updateLead: (
      id: string,
      data: {
        status?: string;
        notes?: string;
        harvest?: Harvest;
        demo_public?: boolean;
      }
    ) =>
      request<{ status: string }>(`/scout/leads/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    deleteLead: (id: string) =>
      request<{ status: string }>(`/scout/leads/${id}`, { method: "DELETE" }),

    // Pipeline: harvest → demo → publish → draft. Each is a separate call so
    // a slow or failed stage never takes the others down with it.
    harvest: (id: string) =>
      request<{ harvest: Harvest; usable: boolean }>(
        `/scout/leads/${id}/harvest`,
        { method: "POST" }
      ),

    plan: (id: string) =>
      request<DemoPlan>(`/scout/leads/${id}/plan`, { method: "POST" }),

    buildDemo: (id: string, directions: string[] = []) =>
      request<{
        slug: string;
        active: string;
        variants: { direction: string; rounds: number; bytes: number }[];
        failed: string[];
      }>(
        `/scout/leads/${id}/demo?directions=${encodeURIComponent(directions.join(","))}`,
        { method: "POST" }
      ),

    selectDemo: (id: string, direction: string) =>
      request<{ active: string }>(
        `/scout/leads/${id}/demo/${direction}/select`,
        { method: "POST" }
      ),

    /** Server-rendered screenshot; used directly as an <img src>. */
    thumbUrl: (id: string, direction: string) =>
      `/api/scout/leads/${id}/demo/${direction}/thumb`,

    draft: (id: string) =>
      request<{ subject: string; body: string; to: string | null }>(
        `/scout/leads/${id}/draft`,
        { method: "POST" }
      ),
  },

  logs: {
    list: (params?: { category?: string; level?: string; search?: string; service?: string; limit?: number; offset?: number }) => {
      const qs = new URLSearchParams();
      if (params?.category) qs.set("category", params.category);
      if (params?.level) qs.set("level", params.level);
      if (params?.search) qs.set("search", params.search);
      if (params?.service) qs.set("service", params.service);
      if (params?.limit) qs.set("limit", String(params.limit));
      if (params?.offset) qs.set("offset", String(params.offset));
      const q = qs.toString();
      return request<{ total: number; entries: LogEntry[] }>(`/logs${q ? `?${q}` : ""}`);
    },
    stats: () => request<LogStats>("/logs/stats"),
    clear: (olderThanDays: number) =>
      request<{ deleted: number }>(`/logs/clear?older_than_days=${olderThanDays}`, {
        method: "DELETE",
      }),
  },
};

/** SWR fetcher for profile endpoint */
export const profileFetcher = (key: string) => {
  const url = new URL(key, "http://localhost");
  const lang = url.searchParams.get("lang") || "en";
  return api.profile.get(lang as Lang);
};
