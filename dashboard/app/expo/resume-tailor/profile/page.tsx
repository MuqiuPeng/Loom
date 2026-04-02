"use client";

import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import useSWR from "swr";
import Markdown from "react-markdown";
import { api } from "@/lib/api";
import Timeline from "@/components/resume-tailor/profile/Timeline";
import type {
  Lang,
  ProfileData,
  Skill,
  ExperienceWithBullets,
  ProjectData,
  EducationData,
  BulletData,
} from "@/lib/types";

type Tab = "profile" | "timeline";

// ── Bullet type styling ──────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  business_impact: "bg-green-100 text-green-700",
  technical_design: "bg-blue-100 text-blue-700",
  scale: "bg-orange-100 text-orange-700",
  implementation: "bg-gray-100 text-gray-600",
  collaboration: "bg-purple-100 text-purple-700",
  problem_solving: "bg-red-100 text-red-700",
};

const TYPE_LABELS: Record<string, string> = {
  business_impact: "Impact",
  technical_design: "Design",
  scale: "Scale",
  implementation: "Impl",
  collaboration: "Collab",
  problem_solving: "Debug",
};

const LEVEL_COLORS: Record<string, string> = {
  expert: "bg-green-100 text-green-800",
  proficient: "bg-blue-100 text-blue-800",
  familiar: "bg-gray-100 text-gray-600",
};

const MD_CLASSES =
  "[&_strong]:font-semibold [&_em]:italic [&_em]:text-gray-600 [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs [&_p]:inline";

// ── Sub-components ───────────────────────────────────────────

function BulletLine({ content, type }: { content: string; type: string }) {
  const colorClass = TYPE_COLORS[type] ?? TYPE_COLORS.implementation;
  const label = TYPE_LABELS[type] ?? type;
  return (
    <div className="flex items-start gap-2 py-1.5">
      <span className="mt-0.5 shrink-0 w-12 text-center">
        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${colorClass}`}>
          {label}
        </span>
      </span>
      <span className={`text-sm text-gray-800 leading-snug ${MD_CLASSES}`}>
        <Markdown>{content}</Markdown>
      </span>
    </div>
  );
}

function BasicInfo({ profile }: { profile: NonNullable<ProfileData["profile"]> }) {
  return (
    <div id="basic-info" className="bg-white rounded-lg border border-gray-200 p-6 scroll-mt-4">
      <h1 className="text-xl font-bold text-gray-900">{profile.name}</h1>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-sm text-gray-500">
        {profile.email && <span>{profile.email}</span>}
        {profile.phone && <span>{profile.phone}</span>}
        {profile.location && <span>{profile.location}</span>}
      </div>
      {profile.summary && (
        <p className="mt-3 text-sm text-gray-700 leading-relaxed">{profile.summary}</p>
      )}
    </div>
  );
}

function SkillsSection({ skills }: { skills: Skill[] }) {
  if (skills.length === 0) return null;

  const grouped: Record<string, Skill[]> = {};
  for (const s of skills) {
    const cat = s.category || "Other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(s);
  }
  const categories = Object.keys(grouped).sort((a, b) => {
    if (a === "Other") return 1;
    if (b === "Other") return -1;
    return a.localeCompare(b);
  });

  return (
    <div id="skills" className="bg-white rounded-lg border border-gray-200 p-6 scroll-mt-4">
      <h2 className="text-lg font-semibold mb-3">Skills</h2>
      <div className="space-y-2">
        {categories.map((cat) => (
          <div key={cat} className="flex items-baseline gap-2">
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wider w-24 shrink-0 text-right">
              {cat}
            </span>
            <div className="flex flex-wrap gap-1">
              {grouped[cat].map((s) => (
                <span key={s.id ?? s.name}
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs ${LEVEL_COLORS[s.level] ?? LEVEL_COLORS.familiar}`}
                  title={s.context ?? undefined}>
                  {s.name}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ExperienceSection({ experience }: { experience: ExperienceWithBullets }) {
  const period = (() => {
    if (!experience.start_date) return "";
    const s = experience.start_date.slice(0, 7);
    const e = experience.end_date ? experience.end_date.slice(0, 7) : "Present";
    return `${s} - ${e}`;
  })();

  return (
    <div id={`exp-${experience.id}`} className="bg-white rounded-lg border border-gray-200 p-6 scroll-mt-4">
      <div className="flex items-start justify-between mb-1">
        <div>
          <h3 className="font-semibold text-gray-900">{experience.company}</h3>
          <p className="text-sm text-gray-600">{experience.title}</p>
        </div>
      </div>
      {(period || experience.location) && (
        <p className="text-xs text-gray-400 mb-2">
          {[period, experience.location].filter(Boolean).join(" · ")}
        </p>
      )}
      {experience.projects && experience.projects.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {experience.projects.map((p) => (
            <a key={p.id} href={`#project-${p.id}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded text-[10px] font-medium hover:bg-indigo-100 transition-colors">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              {p.name}
            </a>
          ))}
        </div>
      )}
      <div className="divide-y divide-gray-50">
        {experience.bullets.map((b) => (
          <BulletLine key={b.id} content={b.content ?? b.raw_text} type={b.type} />
        ))}
      </div>
    </div>
  );
}

function ProjectSection({ project, linkedName }: { project: ProjectData; linkedName?: string }) {
  const period = (() => {
    if (!project.start_date) return "";
    const s = project.start_date.slice(0, 7);
    const e = project.end_date ? project.end_date.slice(0, 7) : "Present";
    return `${s} - ${e}`;
  })();
  const isOngoing = !project.end_date;

  return (
    <div id={`project-${project.id}`} className="bg-white rounded-lg border border-gray-200 p-6 scroll-mt-4">
      <div className="flex items-start justify-between mb-1">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-gray-900">{project.name}</h3>
          {linkedName && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded text-[10px] font-medium">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              {linkedName}
            </span>
          )}
          {isOngoing && (
            <span className="px-2 py-0.5 bg-green-50 text-green-600 rounded text-[10px] font-medium">Ongoing</span>
          )}
        </div>
        {project.role && (
          <span className="text-xs text-gray-500 bg-gray-50 px-2 py-0.5 rounded">{project.role}</span>
        )}
      </div>
      {(project.description || period) && (
        <div className="mb-3">
          {project.description && <p className="text-sm text-gray-600">{project.description}</p>}
          {period && <p className="text-xs text-gray-400 mt-0.5">{period}</p>}
        </div>
      )}
      {project.tech_stack.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {project.tech_stack.map((t) => (
            <span key={t.name} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">{t.name}</span>
          ))}
        </div>
      )}
      {project.bullets.length > 0 && (
        <div className="divide-y divide-gray-50 border-t border-gray-100 pt-2">
          {project.bullets.map((b, i) => (
            <BulletLine key={i} content={(b.content as string) ?? ""} type={(b.type as string) || "implementation"} />
          ))}
        </div>
      )}
    </div>
  );
}

function EducationSection({ education, linkedProjects }: { education: EducationData; linkedProjects?: { id: string; name: string }[] }) {
  const period = (() => {
    if (!education.start_date) return "";
    const s = education.start_date.slice(0, 7);
    const e = education.end_date ? education.end_date.slice(0, 7) : "Present";
    return `${s} - ${e}`;
  })();

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <h3 className="font-semibold text-gray-900">{education.institution}</h3>
      <p className="text-sm text-gray-600">
        {[education.degree, education.field].filter(Boolean).join(" in ")}
      </p>
      {period && <p className="text-xs text-gray-400 mt-1">{period}</p>}
      {linkedProjects && linkedProjects.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {linkedProjects.map((p) => (
            <a key={p.id} href={`#project-${p.id}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded text-[10px] font-medium hover:bg-indigo-100 transition-colors">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              {p.name}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function CertificationsSection({ certifications }: { certifications: { year: string; name: string }[] }) {
  if (!certifications || certifications.length === 0) return null;
  return (
    <div id="certifications" className="bg-white rounded-lg border border-gray-200 p-6 scroll-mt-4">
      <h2 className="text-lg font-semibold mb-3">Certifications</h2>
      <div className="space-y-2">
        {certifications.map((cert, i) => (
          <div key={i} className="flex items-center gap-3">
            <span className="text-xs text-gray-400 font-mono w-12">{cert.year}</span>
            <span className="text-sm text-gray-800">{cert.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────

function ExpoProfileContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const lang = (searchParams.get("lang") as Lang) || "en";
  const [tab, setTab] = useState<Tab>("profile");

  const { data, error } = useSWR<ProfileData>(
    `/expo/profile?lang=${lang}`,
    () => api.profile.get(lang)
  );

  const setLang = (newLang: Lang) => {
    router.push(`/expo/resume-tailor/profile?lang=${newLang}`);
  };

  const allProjects = data
    ? [...data.experiences.flatMap((e) => e.projects ?? []), ...data.projects]
    : [];

  const tocItems = data ? [
    { id: "basic-info", label: "Basic Info" },
    { id: "skills", label: "Skills" },
    { id: "experience", label: "Experience" },
    ...data.experiences.map((e) => ({ id: `exp-${e.id}`, label: e.company, indent: true })),
    { id: "projects", label: "Projects" },
    ...allProjects.map((p) => ({ id: `project-${p.id}`, label: p.name, indent: true })),
    { id: "education", label: "Education" },
    { id: "certifications", label: "Certifications" },
  ] : [];

  return (
    <div className="flex gap-8 max-w-6xl mx-auto px-4 py-8">
      <div className="flex-1 min-w-0 max-w-4xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Profile</h1>
          <div className="flex items-center gap-3">
            <div className="flex bg-gray-100 rounded-md p-0.5">
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
            </div>
            <div className="flex bg-gray-100 rounded-md p-0.5">
              <button onClick={() => setLang("en")}
                className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                  lang === "en" ? "bg-white text-gray-900 shadow-sm font-medium" : "text-gray-500 hover:text-gray-700"
                }`}>EN</button>
              <button onClick={() => setLang("zh")}
                className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                  lang === "zh" ? "bg-white text-gray-900 shadow-sm font-medium" : "text-gray-500 hover:text-gray-700"
                }`}>中文</button>
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-4 mb-6 text-sm">
            Failed to load profile.
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
            {data.profile && <BasicInfo profile={data.profile} />}

            <SkillsSection skills={data.skills} />

            <div id="experience" className="scroll-mt-4">
              <h2 className="text-lg font-semibold mb-3">Experience</h2>
              <div className="space-y-4">
                {data.experiences.length > 0 ? (
                  data.experiences.map((exp) => (
                    <ExperienceSection key={exp.id} experience={exp} />
                  ))
                ) : (
                  <p className="text-sm text-gray-400 italic">No experiences.</p>
                )}
              </div>
            </div>

            {(() => {
              const expMap = new Map(data.experiences.map((e) => [e.id, e.company]));
              const eduMap = new Map(data.education.map((e) => [e.id, e.institution]));
              const projsByEdu = new Map<string, { id: string; name: string }[]>();
              for (const p of allProjects) {
                if (p.education_id) {
                  const list = projsByEdu.get(p.education_id) || [];
                  list.push({ id: p.id, name: p.name });
                  projsByEdu.set(p.education_id, list);
                }
              }
              const getLinkedName = (p: typeof allProjects[0]) => {
                if (p.experience_id && expMap.has(p.experience_id)) return expMap.get(p.experience_id)!;
                if (p.education_id && eduMap.has(p.education_id)) return eduMap.get(p.education_id)!;
                return undefined;
              };

              return (<>
            <div id="projects" className="scroll-mt-4">
              <h2 className="text-lg font-semibold mb-3">Projects</h2>
              <div className="space-y-4">
                {allProjects.length > 0 ? (
                  allProjects.map((p) => (
                    <ProjectSection key={p.id} project={p} linkedName={getLinkedName(p)} />
                  ))
                ) : (
                  <p className="text-sm text-gray-400 italic">No projects.</p>
                )}
              </div>
            </div>

            <div id="education" className="scroll-mt-4">
              <h2 className="text-lg font-semibold mb-3">Education</h2>
              <div className="space-y-4">
                {data.education.length > 0 ? (
                  data.education.map((e) => (
                    <EducationSection key={e.id} education={e} linkedProjects={projsByEdu.get(e.id)} />
                  ))
                ) : (
                  <p className="text-sm text-gray-400 italic">No education.</p>
                )}
              </div>
            </div>
              </>);
            })()}

            {data.profile?.certifications && data.profile.certifications.length > 0 && (
              <CertificationsSection certifications={data.profile.certifications} />
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
                  <a href={`#${item.id}`}
                    className={`block text-sm hover:text-indigo-600 transition-colors truncate ${
                      "indent" in item && item.indent
                        ? "pl-3 text-gray-400 text-xs"
                        : "text-gray-600 font-medium"
                    }`}>
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

export default function ExpoProfilePage() {
  return (
    <Suspense fallback={
      <div className="max-w-4xl mx-auto px-4 py-8 space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-lg border border-gray-200 p-6 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/4 mb-4" />
            <div className="h-3 bg-gray-100 rounded w-3/4" />
          </div>
        ))}
      </div>
    }>
      <ExpoProfileContent />
    </Suspense>
  );
}
