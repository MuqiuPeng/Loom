"use client";

import { useEffect, useMemo, useState } from "react";
import type { DemoPlan, DirectionPick } from "@/lib/types";

/** The proposal, before anything gets built.
 *
 * The recommendations arrive ticked and the rejections arrive listed but not
 * hidden — the reason a direction was ruled out is often the most useful
 * thing on screen, and disagreeing with it should cost one click, not a
 * regenerated plan.
 */
export default function DesignPlan({
  plan,
  building,
  onBuild,
}: {
  plan: DemoPlan;
  building: boolean;
  onBuild: (directions: string[]) => void;
}) {
  const recommended = useMemo(
    () => plan.picks.map((p) => p.direction),
    [plan.picks]
  );
  const [chosen, setChosen] = useState<string[]>(recommended);

  // A re-run replaces the proposal; the ticks follow it rather than lingering.
  useEffect(() => setChosen(recommended), [recommended]);

  const toggle = (direction: string) =>
    setChosen((prev) =>
      prev.includes(direction)
        ? prev.filter((d) => d !== direction)
        : [...prev, direction]
    );

  const Row = ({ pick, dim }: { pick: DirectionPick; dim?: boolean }) => {
    const on = chosen.includes(pick.direction);
    return (
      <label
        className={`flex gap-3 items-start p-2 rounded cursor-pointer transition-colors ${
          on ? "bg-indigo-50" : "hover:bg-gray-50"
        }`}
      >
        <input
          type="checkbox"
          checked={on}
          onChange={() => toggle(pick.direction)}
          className="mt-1 accent-indigo-600"
        />
        <span className="min-w-0">
          <span className="flex items-center gap-2">
            <span
              className={`text-sm font-medium ${
                dim && !on ? "text-gray-500" : "text-gray-900"
              }`}
            >
              {pick.direction.replace(/_/g, " ")}
            </span>
            <span
              className={`text-[11px] px-1.5 py-0.5 rounded ${
                pick.fit >= 70
                  ? "bg-green-100 text-green-700"
                  : pick.fit >= 45
                    ? "bg-amber-100 text-amber-700"
                    : "bg-gray-100 text-gray-500"
              }`}
            >
              fit {pick.fit}
            </span>
          </span>
          <span className="block text-xs text-gray-500 mt-0.5">{pick.why}</span>
        </span>
      </label>
    );
  };

  return (
    <div className="space-y-3">
      {plan.read && (
        <p className="text-sm text-gray-700 leading-relaxed">{plan.read}</p>
      )}

      {plan.angle && (
        <p className="text-sm">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Angle
          </span>
          <br />
          <span className="text-gray-700">{plan.angle}</span>
        </p>
      )}

      {plan.caution && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded p-2">
          {plan.caution}
        </p>
      )}

      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
          Recommended
        </p>
        <div className="space-y-0.5">
          {plan.picks.map((p) => (
            <Row key={p.direction} pick={p} />
          ))}
        </div>
      </div>

      {plan.rejected.length > 0 && (
        <details>
          <summary className="text-xs font-semibold text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-600">
            Considered and ruled out ({plan.rejected.length})
          </summary>
          <div className="space-y-0.5 mt-1">
            {plan.rejected.map((p) => (
              <Row key={p.direction} pick={p} dim />
            ))}
          </div>
        </details>
      )}

      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={() => onBuild(chosen)}
          disabled={building || chosen.length === 0}
          className="px-3 py-1.5 text-sm rounded-md bg-indigo-600 text-white font-medium hover:bg-indigo-700 disabled:opacity-40"
        >
          {building
            ? "Building…"
            : `Build ${chosen.length} design${chosen.length === 1 ? "" : "s"}`}
        </button>
        <span className="text-xs text-gray-400">
          roughly {(chosen.length * 0.3).toFixed(2)} USD · {chosen.length * 30}s
        </span>
      </div>
    </div>
  );
}
