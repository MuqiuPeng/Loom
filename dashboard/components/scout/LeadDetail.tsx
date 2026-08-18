"use client";

import { useState } from "react";

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

/** "3h ago" — coarse on purpose; the question is staleness, not the clock. */
function ago(iso: string | null | undefined): string {
  if (!iso) return "";
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  for (const [limit, size, unit] of [
    [90, 1, "s"],
    [5400, 60, "m"],
    [172800, 3600, "h"],
  ] as const) {
    if (seconds < limit) return `${Math.round(seconds / size)}${unit} ago`;
  }
  return `${Math.round(seconds / 86400)}d ago`;
}

/** A panel section.
 *
 * Two weights, because the panel holds two kinds of thing and used to give
 * them the same one: everything sat under identical grey capitals, so nine
 * sections read as nine equals and the eye had nowhere to land.
 *
 * `stage` is work — material harvested, designs built, an email drafted. It
 * gets a rule across the panel and a heading dark enough to scan for, plus
 * the time it ran, which the panel held and never showed. `quiet` is
 * reference you read once.
 */
function Section({
  title,
  meta,
  tone = "quiet",
  children,
}: {
  title: string;
  meta?: string;
  tone?: "stage" | "quiet";
  children: React.ReactNode;
}) {
  const stage = tone === "stage";
  return (
    <section className={stage ? "pt-5 border-t border-gray-200" : ""}>
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <h3
          className={
            stage
              ? "text-[13px] font-semibold text-gray-900"
              : "text-xs font-semibold text-gray-400 uppercase tracking-wider"
          }
        >
          {title}
        </h3>
        {meta && <span className="text-[11px] text-gray-400 shrink-0">{meta}</span>}
      </div>
      {children}
    </section>
  );
}

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
  // The findings list is the longest thing on the panel and the least often
  // re-read; left open it pushed the pipeline — the reason anyone opens a
  // lead — below the fold. Two are enough to recognise the lead by.
  const [allFindings, setAllFindings] = useState(false);

  // Sending is the one action here that cannot be undone, so it is the one
  // with its own confirmation and its own error line rather than sharing the
  // pipeline's.
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");

  async function onSend() {
    setSending(true);
    setSendError("");
    try {
      const result = await api.scout.send(lead.id);
      if (!result.sent && result.redirected_to) {
        setSendError(
          `Diverted to ${result.redirected_to} — OUTREACH_REDIRECT_TO is still set, so the business was not written to.`
        );
      } else {
        setConfirming(false);
      }
      onRefresh();
    } catch (e) {
      setSendError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }
  const findings = lead.audit?.findings ?? [];
  const shown = allFindings ? findings : findings.slice(0, 2);

  return (
    <div className="h-full flex flex-col">
      <header className="px-6 py-4 border-b border-gray-200 shrink-0">
        <div className="flex items-start justify-between gap-4">
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
        </div>

        {/* Status belongs to identity, not to the scroll: which pile a lead is
            in should not move when the body below it grows. */}
        <div className="flex flex-wrap gap-1 mt-3">
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
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
        {/* Why this lead is worth anything: what is wrong, and how to reach
            them. Read once, so it stays quiet and short. */}
        {findings.length > 0 && (
          <Section title="Findings" meta={`score ${lead.score}`}>
            <ul className="space-y-1.5">
              {shown.map((f) => (
                <li key={f.code} className="text-sm leading-snug">
                  <span className="text-gray-900 font-medium">{f.label}</span>
                  {f.detail && (
                    <span className="block text-xs text-gray-500 mt-0.5">
                      {f.detail}
                    </span>
                  )}
                </li>
              ))}
            </ul>
            {findings.length > 2 && (
              <button
                onClick={() => setAllFindings((v) => !v)}
                className="mt-1.5 text-xs text-indigo-600 hover:underline"
              >
                {allFindings
                  ? "Show fewer"
                  : `${findings.length - 2} more`}
              </button>
            )}
          </Section>
        )}

        <Section title="Contact">
          <dl className="text-sm space-y-1">
            {lead.site_url && (
              <div className="flex gap-2">
                <dt className="text-gray-400 w-12 shrink-0">Site</dt>
                <dd className="min-w-0">
                  <a
                    href={lead.site_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-indigo-600 hover:underline block truncate"
                  >
                    {lead.site_title || lead.site_url}
                  </a>
                </dd>
              </div>
            )}
            {lead.emails.length > 0 && (
              <div className="flex gap-2">
                <dt className="text-gray-400 w-12 shrink-0">Email</dt>
                <dd className="text-gray-700 break-all">{lead.emails.join(", ")}</dd>
              </div>
            )}
            {lead.google_phone && (
              <div className="flex gap-2">
                <dt className="text-gray-400 w-12 shrink-0">Phone</dt>
                <dd className="text-gray-700">{lead.google_phone}</dd>
              </div>
            )}
            {!lead.site_url && lead.emails.length === 0 && !lead.google_phone && (
              <p className="text-sm text-gray-400">
                No website, address or number found — check their socials by hand.
              </p>
            )}
          </dl>
        </Section>

        {/* Commercial work, and only freelance leads get it. The API answers
            409 for a job lead; not rendering the buttons means you never have
            to find that out by clicking. */}
        {lead.kind === "freelance" && (
          <Section title="Pipeline" tone="stage">
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
            {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
          </Section>
        )}

        {/* Stage output, in the order the stages run. The harvest used to sit
            below the designs it was the material for. */}
        {lead.harvest && (
          <Section title="Harvested" meta={ago(lead.harvested_at)} tone="stage">
            <HarvestPanel lead={lead} onSaved={onRefresh} />
          </Section>
        )}

        {lead.demo_plan && (
          <Section title="Design plan" meta={ago(lead.planned_at)} tone="stage">
            <DesignPlan
              plan={lead.demo_plan}
              building={busy === "demo"}
              onBuild={(directions) => onBuild(lead, directions)}
            />
          </Section>
        )}

        {lead.demo_options.length > 0 && (
          <Section title="Designs" meta={ago(lead.demo_built_at)} tone="stage">
            <p className="text-xs text-gray-500 mb-2">
              The selected one is what preview and the link show.
            </p>
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

            {/* Sharing is a decision about a built design, so it lives with
                them rather than under the pipeline buttons. */}
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
          </Section>
        )}

        {lead.draft_body && (
          <Section title="Draft email" meta={ago(lead.drafted_at)} tone="stage">
            <p className="text-sm text-gray-900 font-medium mb-1.5">
              {lead.draft_subject}
            </p>
            <pre className="bg-gray-50 border border-gray-100 rounded p-3 text-xs text-gray-700 whitespace-pre-wrap">
              {lead.draft_body}
            </pre>
            <div className="mt-1.5 flex items-center gap-2">
              <button
                onClick={() =>
                  navigator.clipboard.writeText(
                    `Subject: ${lead.draft_subject}\n\n${lead.draft_body}`
                  )
                }
                className="text-xs text-indigo-600 hover:underline"
              >
                copy
              </button>
            </div>

            {/* Sending, in two clicks rather than one.
                The first opens the confirmation; the second sends. What sits
                between them is the recipient's address, because that is the
                thing worth reading twice — the draft above is already visible,
                and who it is addressed to is not. */}
            <div className="mt-3 pt-3 border-t border-gray-100">
              {lead.contacted_at ? (
                <p className="text-xs text-gray-500">
                  Sent {new Date(lead.contacted_at).toLocaleDateString()}. A lead
                  is only written to once from here.
                </p>
              ) : confirming ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
                  <p className="text-sm text-gray-800">
                    Send to{" "}
                    <span className="font-medium">{lead.emails[0]}</span>?
                  </p>
                  <p className="mt-1 text-xs text-gray-600">
                    It goes now, from your own address. Nothing recalls it.
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      onClick={onSend}
                      disabled={sending}
                      className="px-3 py-1.5 rounded-md bg-gray-900 text-white text-sm font-medium hover:bg-black disabled:opacity-40"
                    >
                      {sending ? "Sending…" : "Send it"}
                    </button>
                    <button
                      onClick={() => setConfirming(false)}
                      disabled={sending}
                      className="text-xs text-gray-500 hover:underline"
                    >
                      cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setConfirming(true)}
                  disabled={lead.emails.length === 0}
                  title={
                    lead.emails.length === 0
                      ? "No address that may be written to"
                      : undefined
                  }
                  className="px-3 py-1.5 rounded-md border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Send this email
                </button>
              )}
              {sendError && (
                <p className="mt-2 text-xs text-red-600">{sendError}</p>
              )}
            </div>
          </Section>
        )}

        <Section title="Notes" tone="stage">
          <textarea
            defaultValue={lead.notes || ""}
            onBlur={(e) => onNotes(lead, e.target.value)}
            placeholder="What happened?"
            rows={3}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </Section>
      </div>
    </div>
  );
}
