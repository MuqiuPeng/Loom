"use client";

import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import useSWR from "swr";
import Header from "@/components/layout/Header";
import BasicInfoCard from "@/components/resume-tailor/profile/BasicInfoCard";
import SkillsCard from "@/components/resume-tailor/profile/SkillsCard";
import ExperienceCard from "@/components/resume-tailor/profile/ExperienceCard";
import ProjectCard from "@/components/resume-tailor/profile/ProjectCard";
import EducationCard from "@/components/resume-tailor/profile/EducationCard";
import CertificationsCard from "@/components/resume-tailor/profile/CertificationsCard";
import Timeline from "@/components/resume-tailor/profile/Timeline";
import { api } from "@/lib/api";
import type { Lang, ProfileData } from "@/lib/types";

type Tab = "profile" | "timeline";

function AddForm({ fields, onSave, onCancel, saving }: {
  fields: { key: string; label: string; wide?: boolean }[];
  onSave: (data: Record<string, string>) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  return (
    <div className="bg-white rounded-lg border border-dashed border-indigo-300 p-6 space-y-3">
      {fields.map((f) => (
        <input key={f.key} value={draft[f.key] ?? ""} onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
          placeholder={f.label}
          className={`border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${f.wide ? "w-full" : "w-full"}`} />
      ))}
      <div className="flex gap-2">
        <button onClick={() => onSave(draft)} disabled={saving}
          className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-md hover:bg-indigo-700 disabled:opacity-50">
          {saving ? "Saving..." : "Save"}
        </button>
        <button onClick={onCancel} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
      </div>
    </div>
  );
}

function ProfileContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const lang = (searchParams.get("lang") as Lang) || "en";

  const { data, error, mutate } = useSWR<ProfileData>(
    `/profile?lang=${lang}`,
    () => api.profile.get(lang)
  );

  const [tab, setTab] = useState<Tab>("profile");
  const [addingExp, setAddingExp] = useState(false);
  const [addingProj, setAddingProj] = useState(false);
  const [addingEdu, setAddingEdu] = useState(false);
  const [saving, setSaving] = useState(false);

  const setLang = (newLang: Lang) => {
    router.push(`/resume-tailor/profile?lang=${newLang}`);
  };

  const addExperience = async (d: Record<string, string>) => {
    setSaving(true);
    try {
      await api.profile.addExperience({
        company_en: d.company || "Untitled",
        title_en: d.title || "Untitled",
        start_date: d.start_date || null,
        end_date: d.end_date || null,
        location_en: d.location || null,
      });
      setAddingExp(false);
      mutate();
    } finally { setSaving(false); }
  };

  const addProject = async (d: Record<string, string>) => {
    setSaving(true);
    try {
      await api.profile.addProject({
        name_en: d.name || "Untitled",
        description_en: d.description || null,
        role_en: d.role || null,
      });
      setAddingProj(false);
      mutate();
    } finally { setSaving(false); }
  };

  const addEducation = async (d: Record<string, string>) => {
    setSaving(true);
    try {
      await api.profile.addEducation({
        institution_en: d.institution || "Untitled",
        degree_en: d.degree || null,
        field_en: d.field || null,
        start_date: d.start_date || null,
        end_date: d.end_date || null,
      });
      setAddingEdu(false);
      mutate();
    } finally { setSaving(false); }
  };

  const tocItems = data ? [
    { id: "basic-info", label: "Basic Info" },
    { id: "skills", label: `Skills (${data.skills.length})` },
    { id: "experience", label: `Experience (${data.experiences.length})` },
    ...data.experiences.map((e) => ({ id: `exp-${e.id}`, label: e.company, indent: true })),
    { id: "projects", label: `Projects (${data.experiences.flatMap(e => e.projects ?? []).length + data.projects.length})` },
    ...data.experiences.flatMap(e => e.projects ?? []).map((p) => ({ id: `project-${p.id}`, label: p.name, indent: true })),
    ...data.projects.map((p) => ({ id: `project-${p.id}`, label: p.name, indent: true })),
    { id: "education", label: `Education (${data.education.length})` },
    { id: "certifications", label: `Certifications (${data.profile?.certifications?.length || 0})` },
  ] : [];

  return (
    <div className="flex gap-8">
      <div className="flex-1 min-w-0 max-w-4xl">
      <Header title="Profile">
        <div className="flex items-center gap-3">
          <div className="flex items-center bg-gray-100 rounded-md p-0.5">
            {(["profile", "timeline"] as Tab[]).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                  tab === t
                    ? "bg-white text-gray-900 shadow-sm font-medium"
                    : "text-gray-500 hover:text-gray-700"
                }`}>
                {t === "profile" ? "Profile" : "Timeline"}
              </button>
            ))}
            <a href={`/expo/resume-tailor/profile?lang=${lang}`}
              target="_blank" rel="noopener noreferrer"
              className="ml-1 p-1.5 text-gray-400 hover:text-indigo-600 transition-colors rounded-md hover:bg-white"
              title="Open public view">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
              </svg>
            </a>
          </div>
          <div className="flex bg-gray-100 rounded-md p-0.5">
            <button onClick={() => setLang("en")}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                lang === "en"
                  ? "bg-white text-gray-900 shadow-sm font-medium"
                  : "text-gray-500 hover:text-gray-700"
              }`}>EN</button>
            <button onClick={() => setLang("zh")}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                lang === "zh"
                  ? "bg-white text-gray-900 shadow-sm font-medium"
                  : "text-gray-500 hover:text-gray-700"
              }`}>中文</button>
          </div>
        </div>
      </Header>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-4 mb-6 text-sm">
          Failed to load profile. Is the API server running?
        </div>
      )}

      {!data && !error && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 p-6 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/4 mb-4" />
              <div className="h-3 bg-gray-100 rounded w-3/4" />
            </div>
          ))}
        </div>
      )}

      {data && tab === "timeline" && (
        <Timeline data={data} />
      )}

      {data && tab === "profile" && (
        <div className="space-y-6">
          <div id="basic-info" className="scroll-mt-4">
          {data.profile ? (
            <BasicInfoCard profile={data.profile} lang={lang} onUpdate={() => mutate()} />
          ) : (
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <p className="text-gray-400 italic text-sm">
                No profile found. Use the chat or /setup-profile to create one.
              </p>
            </div>
          )}
          </div>

          <div id="skills" className="scroll-mt-4">
          <SkillsCard skills={data.skills} onUpdate={() => mutate()} />
          </div>

          {/* Build project link maps */}
          {(() => {
            const allProjs = [
              ...data.experiences.flatMap((e) => e.projects ?? []),
              ...data.projects,
            ];
            // experience_id → linked projects
            const projsByExp = new Map<string, { id: string; name: string }[]>();
            // education_id → linked projects
            const projsByEdu = new Map<string, { id: string; name: string }[]>();
            for (const p of allProjs) {
              if (p.experience_id) {
                const list = projsByExp.get(p.experience_id) || [];
                list.push({ id: p.id, name: p.name });
                projsByExp.set(p.experience_id, list);
              }
              if (p.education_id) {
                const list = projsByEdu.get(p.education_id) || [];
                list.push({ id: p.id, name: p.name });
                projsByEdu.set(p.education_id, list);
              }
            }

            return (<>
          {/* Experience */}
          <div id="experience" className="scroll-mt-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold">Experience</h2>
              {!addingExp && (
                <button onClick={() => setAddingExp(true)}
                  className="text-sm text-indigo-600 hover:text-indigo-800">+ Add</button>
              )}
            </div>
            <div className="space-y-4">
              {addingExp && (
                <AddForm
                  fields={[
                    { key: "company", label: "Company" },
                    { key: "title", label: "Title" },
                    { key: "start_date", label: "Start (YYYY-MM)" },
                    { key: "end_date", label: "End (YYYY-MM, leave empty for current)" },
                    { key: "location", label: "Location" },
                  ]}
                  onSave={addExperience} onCancel={() => setAddingExp(false)} saving={saving}
                />
              )}
              {data.experiences.length > 0 ? (
                data.experiences.map((exp) => (
                  <div key={exp.id} id={`exp-${exp.id}`} className="scroll-mt-4">
                    <ExperienceCard experience={exp} lang={lang} onUpdate={() => mutate()}
                      linkedProjects={projsByExp.get(exp.id)} />
                  </div>
                ))
              ) : !addingExp && (
                <p className="text-sm text-gray-400 italic">No experiences added yet.</p>
              )}
            </div>
          </div>

          {/* Projects — all projects (linked + standalone) */}
          {(() => {
            const linkedProjects = data.experiences.flatMap((e) => e.projects ?? []);
            const allProjects = [...linkedProjects, ...data.projects];

            // Build lookup maps for linked names
            const expMap = new Map(data.experiences.map((e) => [e.id, e.company]));
            const eduMap = new Map(data.education.map((e) => [e.id, e.institution]));

            const getLinked = (p: typeof allProjects[0]) => {
              if (p.experience_id && expMap.has(p.experience_id))
                return { name: expMap.get(p.experience_id)!, href: `#exp-${p.experience_id}` };
              if (p.education_id) {
                const eduName = eduMap.get(p.education_id);
                if (eduName) return { name: eduName, href: "#education" };
              }
              return null;
            };

            // Build link options for dropdown
            const linkOpts = [
              ...data.experiences.map((e) => ({ id: e.id, label: e.company, type: "experience" as const })),
              ...data.education.map((e) => ({ id: e.id, label: e.institution, type: "education" as const })),
            ];

            return (
              <div id="projects" className="scroll-mt-4">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-lg font-semibold">Projects</h2>
                  {!addingProj && (
                    <button onClick={() => setAddingProj(true)}
                      className="text-sm text-indigo-600 hover:text-indigo-800">+ Add</button>
                  )}
                </div>
                <div className="space-y-4">
                  {addingProj && (
                    <AddForm
                      fields={[
                        { key: "name", label: "Project name" },
                        { key: "role", label: "Role" },
                        { key: "description", label: "Description", wide: true },
                      ]}
                      onSave={addProject} onCancel={() => setAddingProj(false)} saving={saving}
                    />
                  )}
                  {allProjects.length > 0 ? (
                    allProjects.map((p) => {
                      const linked = getLinked(p);
                      return (
                        <ProjectCard key={p.id} project={p} lang={lang} onUpdate={() => mutate()}
                          linkedName={linked?.name} linkedHref={linked?.href}
                          linkOptions={linkOpts} />
                      );
                    })
                  ) : !addingProj && (
                    <p className="text-sm text-gray-400 italic">No projects added yet.</p>
                  )}
                </div>
              </div>
            );
          })()}

          {/* Education */}
          <div id="education" className="scroll-mt-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold">Education</h2>
              {!addingEdu && (
                <button onClick={() => setAddingEdu(true)}
                  className="text-sm text-indigo-600 hover:text-indigo-800">+ Add</button>
              )}
            </div>
            <div className="space-y-4">
              {addingEdu && (
                <AddForm
                  fields={[
                    { key: "institution", label: "Institution" },
                    { key: "degree", label: "Degree" },
                    { key: "field", label: "Field of study" },
                    { key: "start_date", label: "Start (YYYY-MM)" },
                    { key: "end_date", label: "End (YYYY-MM)" },
                  ]}
                  onSave={addEducation} onCancel={() => setAddingEdu(false)} saving={saving}
                />
              )}
              {data.education.length > 0 ? (
                data.education.map((e) => (
                  <EducationCard key={e.id} education={e} lang={lang} onUpdate={() => mutate()}
                    linkedProjects={projsByEdu.get(e.id)} />
                ))
              ) : !addingEdu && (
                <p className="text-sm text-gray-400 italic">No education added yet.</p>
              )}
            </div>
          </div>
          </>); })()}

          {/* Certifications */}
          {data.profile && (
            <div id="certifications" className="scroll-mt-4">
              <CertificationsCard
                certifications={data.profile.certifications || []}
                onUpdate={() => mutate()}
              />
            </div>
          )}
        </div>
      )}
    </div>

      {/* TOC sidebar — profile tab only */}
      {data && tab === "profile" && tocItems.length > 0 && (
        <nav className="hidden xl:block w-48 shrink-0">
          <div className="sticky top-6">
            <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">On this page</h3>
            <ul className="space-y-1">
              {tocItems.map((item) => (
                <li key={item.id}>
                  <a
                    href={`#${item.id}`}
                    className={`block text-sm hover:text-indigo-600 transition-colors truncate ${
                      "indent" in item && item.indent
                        ? "pl-3 text-gray-400 text-xs"
                        : "text-gray-600 font-medium"
                    }`}
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </nav>
      )}
    </div>
  );
}

export default function ProfilePage() {
  return (
    <Suspense fallback={
      <div className="max-w-4xl space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-lg border border-gray-200 p-6 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/4 mb-4" />
            <div className="h-3 bg-gray-100 rounded w-3/4" />
          </div>
        ))}
      </div>
    }>
      <ProfileContent />
    </Suspense>
  );
}
