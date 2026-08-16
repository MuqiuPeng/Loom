export interface ProfileData {
  profile: {
    id: string;
    name: string;
    email: string | null;
    phone: string | null;
    location: string | null;
    github: string | null;
    linkedin: string | null;
    summary: string | null;
    certifications: CertificationData[];
  } | null;
  skills: Skill[];
  experiences: ExperienceWithBullets[];
  projects: ProjectData[];
  education: EducationData[];
}

export interface CertificationData {
  year: string;
  name: string;
}

export interface Skill {
  id: string;
  name: string;
  level: string;
  category: string | null;
  context: string | null;
}

export interface BulletData {
  id: string;
  content: string | null;
  raw_text: string;
  star_data: Record<string, string>;
  type: BulletType;
  tech_stack: TechItem[];
}

export interface ExperienceWithBullets {
  id: string;
  company: string;
  title: string;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  is_visible: boolean;
  bullets: BulletData[];
  projects: ProjectData[];
}

export interface ProjectBullet {
  content: string | null;
  content_en?: string;
  content_zh?: string;
  type?: string;
  priority?: number;
  star_data?: Record<string, string>;
}

export interface ProjectData {
  id: string;
  experience_id: string | null;
  education_id: string | null;
  name: string;
  description: string | null;
  role: string | null;
  start_date: string | null;
  end_date: string | null;
  tech_stack: TechItem[];
  bullets: ProjectBullet[];
  local_repo_path: string | null;
  last_analyzed_at: string | null;
  has_local_repo: boolean;
  is_visible: boolean;
}

export interface EducationData {
  id: string;
  institution: string;
  degree: string | null;
  field: string | null;
  start_date: string | null;
  end_date: string | null;
}

export interface TechItem {
  name: string;
  role?: string;
  ecosystem_group?: string;
}

export type BulletType =
  | "business_impact"
  | "technical_design"
  | "implementation"
  | "scale"
  | "collaboration"
  | "problem_solving";

export interface JDRecord {
  id: string;
  company: string | null;
  title: string;
  raw_text: string;
  required_skills: string[];
  preferred_skills: string[];
  key_requirements: string[];
  match_score: number | null;
  created_at: string;
}

export interface ResumeArtifact {
  id: string;
  jd_record_id: string | null;
  language: string;
  content_md: string | null;
  content_tex: string | null;
  has_pdf: boolean;
  starred: boolean;
  status: string; // matching/selecting/generating/reviewing/scrutiny/compiling/completed/failed
  created_at: string;
  jd_title?: string;
  jd_company?: string;
}

export interface WorkflowRun {
  id: string;
  workflow_name: string;
  status: "pending" | "running" | "completed" | "failed";
  trigger_data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  step_runs: StepRun[];
}

export interface StepRun {
  id: string;
  step_name: string;
  order: number;
  status: "pending" | "running" | "completed" | "failed";
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface TaskStatus {
  task_id: string;
  type: string;
  status: "pending" | "running" | "completed" | "failed";
  output_data: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnalyzeJDOutput {
  jd_record_id: string;
  company: string | null;
  title: string;
  required_skills: string[];
  preferred_skills: string[];
  match_score: number;
  matched: Array<{ requirement: string; evidence: string }>;
  hard_skill_gaps: string[];
  reasoning: string;
}

export interface GenerateResumeOutput {
  resume_artifact_id: string;
  download_url?: string;
}

export interface LogEntry {
  id: string;
  level: "info" | "warning" | "error";
  service: string;
  category: string;
  action: string;
  message: string;
  workflow_run_id: string | null;
  step_name: string | null;
  data: Record<string, unknown>;
  error: string | null;
  traceback: string | null;
  created_at: string;
}

export interface LogStats {
  total_entries: number;
  by_category: Record<string, number>;
  by_level: Record<string, number>;
  total_tokens_used: number;
  oldest_entry: string | null;
  newest_entry: string | null;
}

/** One company from Company Scout.
 *
 * The google_* fields come from Places and are display-only — Maps Platform
 * ToS forbids storing them. Everything below them was read from the company's
 * own site and is yours to keep, alongside place_id. */
export interface SiteFinding {
  code: string;
  weight: number;
  label: string;
  detail: string;
}

/** One page fetch's verdict on a business's web presence.
 * Derived from their own site, so it's safe to store. */
export interface SiteAudit {
  url: string | null;
  reachable: boolean;
  status_code: number | null;
  load_ms: number | null;
  findings: SiteFinding[];
  score: number;
}

export interface ScoutCandidate {
  place_id: string;
  google_name: string;
  google_address: string;
  google_website: string | null;
  google_phone: string | null;
  primary_type: string | null;
  google_rating: number | null;
  google_rating_count: number | null;
  google_price_level: string | null;
  google_hours: string[];
  google_maps_uri: string | null;
  google_types: string[];
  site_url: string | null;
  site_title: string | null;
  careers_url: string | null;
  emails: string[];
  audit: SiteAudit | null;
  fetch_error: string | null;
  checked_at: string;
}

export type LeadStatus = "new" | "contacted" | "replied" | "won" | "dead";

/** A saved lead. google_* fields are blanked once the 30-day Maps Platform
 * caching window lapses, so treat them as possibly absent. */
export interface ScoutLead {
  id: string;
  place_id: string;
  status: LeadStatus;
  notes: string | null;
  site_url: string | null;
  site_title: string | null;
  careers_url: string | null;
  emails: string[];
  audit: SiteAudit | null;
  score: number;
  google_name: string | null;
  google_address: string | null;
  google_phone: string | null;
  harvest: Harvest | null;
  harvested_at: string | null;
  demo_slug: string | null;
  demo_url: string | null;
  demo_built_at: string | null;
  demo_active: string | null;
  demo_public: boolean;
  demo_options: DemoOption[];
  demo_plan: DemoPlan | null;
  planned_at: string | null;
  draft_subject: string | null;
  draft_body: string | null;
  contacted_at: string | null;
  created_at: string | null;
  checked_at: string | null;
}

/** One generated design. The full HTML and screenshot stay server-side —
 * the list only carries what's needed to compare and choose. */
/** One direction the analysis proposed, with its reasoning. */
export interface DirectionPick {
  direction: string;
  fit: number;
  why: string;
}

/** The proposal that precedes generation — reviewed and adjusted before
 * anything expensive runs. */
export interface DemoPlan {
  read: string;
  picks: DirectionPick[];
  rejected: DirectionPick[];
  angle: string;
  caution: string;
  error: string | null;
}

/** A curated place to prospect, with the reason to be there. */
export interface AreaSuggestion {
  area: string;
  note: string;
  region: string;
}

/** What one area looks like once scanned — the answer to 'work here?'. */
export interface AreaResult {
  area: string;
  note: string;
  total: number;
  no_website: number;
  broken_site: number;
  workable: number;
  contactable: number;
  avg_signal: number;
  hit_rate: number;
  top: string[];
  error: string | null;
}

export interface DemoOption {
  direction: string;
  rounds: number | null;
  /** "template" when rendered deterministically, "model" when generated. */
  engine: string;
  remaining: { code: string; detail: string }[];
  has_thumb: boolean;
}

export interface MenuItem {
  name: string;
  price: string | null;
  description: string | null;
  section: string | null;
}

/** What was read off the business's own pages — the material a demo is
 * built from. All self-sourced, so no caching restriction. */
/** What the user picked to build with. Empty arrays mean "use everything". */
export interface HarvestSelection {
  images: string[];
  menu: string[];
  use_hours: boolean;
  use_about: boolean;
  highlight: string | null;
}

export interface Harvest {
  pages_read: string[];
  menu: MenuItem[];
  hours: string | null;
  address: string | null;
  phone: string | null;
  about: string | null;
  images: string[];
  socials: Record<string, string>;
  selection: HarvestSelection;
  error: string | null;
}

export interface ScoutStats {
  total: number;
  with_website: number;
  without_website: number;
  pct_without_website: number;
  by_type: Record<string, number>;
  by_finding: Record<string, number>;
}

export type Lang = "en" | "zh";
