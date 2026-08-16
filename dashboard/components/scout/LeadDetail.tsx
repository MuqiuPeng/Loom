"use client";

import DesignPlan from "@/components/scout/DesignPlan";
import HarvestPanel from "@/components/scout/HarvestPanel";
import { api } from "@/lib/api";
import type { LeadStatus, ScoutLead } from "@/lib/types";

/** Absolute so it can be pasted into an email as-is. */
const shareUrl = (slug: string) =>
  typeof window === "undefined" ? `/demo/${slug}` : `${window.location.origin}/demo/${slug}`;

export type Stage = "harvest" | "plan" | "demo" | "draft" | "select";

export const STATUSES: { value: LeadStatus; label: string; tone: string }[] = [
  { value: "new", label: "New", tone: "bg-gray-100 text-gray-600" },
  { value: "contacted", label: "Contacted", tone: "bg-blue-50 text-blue-700" },
  { value: "replied", label: "Replied", tone: "bg-amber-50 text-amber-700" },
  { value: "won", label: "Won", tone: "bg-green-50 text-green-700" },
  { value: "dead", label: "Dead", tone: "bg-gray-100 text-gray-400" },
];

function Step({
  label,
  done,
  disabled,
  busy,
  onClick,
}: {
  label: string;
  done: boolean;
  disabled?: boolean;
  busy?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || busy}
      title={disabled ? "Finish the previous step first" : undefined}
      className={`px-2.5 py-1 rounded text-xs font-medium border transition-colors ${
        done
          ? "border-green-200 bg-green-50 text-green-700 hover:bg-green-100"
          : disabled
            ? "border-gray-100 text-gray-300 cursor-not-allowed"
            : "border-gray-200 text-gray-600 hover:bg-gray-50"
      }`}
    >
      {busy ? "…" : done ? `✓ ${label}` : label}
    </button>
  );
}

export default function LeadDetail({
  lead,
  busy,
  error,
  onClose,
  onAct,
  onBuild,
  onShare,
  onChoose,
  onStatus,
  onNotes,
  onRefresh,
}: {
  lead: ScoutLead;
  busy?: Stage;
  error?: string;
  onClose: () => void;
  onAct: (lead: ScoutLead, stage: Stage) => void;
  onBuild: (lead: ScoutLead, directions: string[]) => void;
  onShare: (lead: ScoutLead, isPublic: boolean) => void;
  onChoose: (lead: ScoutLead, direction: string) => void;
  onStatus: (lead: ScoutLead, status: LeadStatus) => void;
  onNotes: (lead: ScoutLead, notes: string) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="h-full flex flex-col">
      <header className="px-6 py-4 border-b border-gray-200 flex items-start justify-between gap-4 shrink-0">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-gray-900 truncate">
            {lead.google_name || lead.site_title || lead.place_id}
          </h2>
          {lead.google_address && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">
              {lead.google_address}
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-700 text-xl leading-none shrink-0"
          aria-label="Close"
        >
          ×
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
        {/* Outreach status */}
        <div className="flex flex-wrap gap-1">
          {STATUSES.map((s) => (
            <button
              key={s.value}
              onClick={() => onStatus(lead, s.value)}
              className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
                lead.status === s.value ? s.tone : "text-gray-400 hover:bg-gray-50"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* What's wrong with their current site — the pitch */}
        {lead.audit && lead.audit.findings.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Findings · score {lead.score}
            </h3>
            <ul className="space-y-1">
              {lead.audit.findings.map((f) => (
                <li key={f.code} className="text-sm">
                  <span className="text-amber-500">•</span>{" "}
                  <span className="text-gray-800 font-medium">{f.label}</span>
                  {f.detail && (
                    <span className="text-gray-500"> — {f.detail}</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Contact */}
        <section className="text-sm space-y-1">
          {lead.site_url && (
            <a
              href={lead.site_url}
              target="_blank"
              rel="noreferrer noopener"
              className="block text-indigo-600 hover:underline truncate"
            >
              {lead.site_title || lead.site_url}
            </a>
          )}
          {lead.emails.length > 0 && (
            <p className="text-gray-700 break-all">{lead.emails.join(", ")}</p>
          )}
          {lead.google_phone && <p className="text-gray-700">{lead.google_phone}</p>}
        </section>

        {/* Pipeline */}
        {/* Commercial work, and only freelance leads get it. The API answers
            409 for a job lead; not rendering the buttons means you never have
            to find that out by clicking. */}
        {lead.kind === "freelance" && (
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
            Pipeline
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            <Step
              label="Harvest"
              done={!!lead.harvested_at}
              busy={busy === "harvest"}
              onClick={() => onAct(lead, "harvest")}
            />
            <span className="text-gray-300">→</span>
            <Step
              label={lead.demo_plan ? "Re-analyse" : "Analyse"}
              done={!!lead.planned_at}
              disabled={!lead.harvested_at}
              busy={busy === "plan"}
              onClick={() => onAct(lead, "plan")}
            />
            <span className="text-gray-300">→</span>
            <Step
              label="Draft email"
              done={!!lead.draft_body}
              disabled={!lead.demo_built_at}
              busy={busy === "draft"}
              onClick={() => onAct(lead, "draft")}
            />
            {lead.demo_built_at && (
              <a
                href={`/api/scout/leads/${lead.id}/demo`}
                target="_blank"
                rel="noreferrer noopener"
                className="text-xs text-indigo-600 hover:underline ml-1"
              >
                preview ↗
              </a>
            )}
          </div>

          {/* Sharing is a decision, not a by-product of building. */}
          {lead.demo_built_at && (
            <div className="mt-3 p-2.5 rounded-md border border-gray-200 bg-gray-50">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={lead.demo_public}
                  onChange={(e) => onShare(lead, e.target.checked)}
                  className="accent-indigo-600"
                />
                <span className="text-sm text-gray-700">
                  Anyone with the link can open this
                </span>
              </label>
              {lead.demo_public && lead.demo_slug ? (
                <div className="mt-2 flex items-center gap-2">
                  <code className="text-xs text-gray-600 bg-white border border-gray-200 rounded px-2 py-1 truncate flex-1">
                    {shareUrl(lead.demo_slug)}
                  </code>
                  <button
                    onClick={() =>
                      navigator.clipboard.writeText(shareUrl(lead.demo_slug!))
                    }
                    className="text-xs text-indigo-600 hover:underline shrink-0"
                  >
                    copy
                  </button>
                </div>
              ) : (
                <p className="mt-1 text-xs text-gray-400">
                  Off — the link 404s for everyone, including you when logged out.
                </p>
              )}
            </div>
          )}
          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        </section>
        )}

        {/* The proposal — reviewed before anything expensive runs */}
        {lead.demo_plan && (
          <section>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Design plan
            </h3>
            <DesignPlan
              plan={lead.demo_plan}
              building={busy === "demo"}
              onBuild={(directions) => onBuild(lead, directions)}
            />
          </section>
        )}

        {/* Designs */}
        {lead.demo_options.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Designs — the selected one is what preview shows
            </h3>
            <div className="flex gap-3 overflow-x-auto pb-1">
              {lead.demo_options.map((option) => {
                const active = option.direction === lead.demo_active;
                return (
                  <button
                    key={option.direction}
                    onClick={() => onChoose(lead, option.direction)}
                    disabled={busy === "select"}
                    className={`shrink-0 text-left rounded-lg border-2 transition-colors ${
                      active
                        ? "border-indigo-500"
                        : "border-transparent hover:border-gray-300"
                    }`}
                  >
                    {option.has_thumb ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={api.scout.thumbUrl(lead.id, option.direction)}
                        alt={`${option.direction} design`}
                        className="w-36 h-64 object-cover object-top rounded-t-md bg-gray-100"
                      />
                    ) : (
                      <div className="w-36 h-64 rounded-t-md bg-gray-100 flex items-center justify-center text-xs text-gray-400">
                        no preview
                      </div>
                    )}
                    <span
                      className={`block px-2 py-1 text-[11px] rounded-b-md ${
                        active
                          ? "bg-indigo-500 text-white font-medium"
                          : "bg-gray-50 text-gray-600"
                      }`}
                    >
                      {active ? "✓ " : ""}
                      {option.direction.replace(/_/g, " ")}
                      {option.engine === "model" && (
                        <span
                          className="opacity-60"
                          title="Generated by the model — no template for this direction"
                        >
                          {" "}· ai
                        </span>
                      )}
                      {option.remaining.length > 0 && (
                        <span className="text-amber-600">
                          {" "}
                          · {option.remaining.length} issue
                        </span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {/* Harvested material, with the pick-what-to-use controls */}
        {lead.harvest && (
          <section>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Harvested
            </h3>
            <HarvestPanel lead={lead} onSaved={onRefresh} />
          </section>
        )}

        {/* Draft */}
        {lead.draft_body && (
          <section>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Draft — {lead.draft_subject}
            </h3>
            <pre className="bg-gray-50 border border-gray-100 rounded p-3 text-xs text-gray-700 whitespace-pre-wrap">
              {lead.draft_body}
            </pre>
            <button
              onClick={() =>
                navigator.clipboard.writeText(
                  `Subject: ${lead.draft_subject}\n\n${lead.draft_body}`
                )
              }
              className="mt-1 text-xs text-indigo-600 hover:underline"
            >
              copy
            </button>
            <span className="ml-2 text-xs text-gray-400">
              Nothing is sent for you — send it from your own mail client.
            </span>
          </section>
        )}

        {/* Notes */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
            Notes
          </h3>
          <textarea
            defaultValue={lead.notes || ""}
            onBlur={(e) => onNotes(lead, e.target.value)}
            placeholder="What happened?"
            rows={3}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </section>
      </div>
    </div>
  );
}
