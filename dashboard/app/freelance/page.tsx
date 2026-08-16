"use client";

import ScoutWorkspace from "@/components/scout/ScoutWorkspace";

/** Businesses whose site has something demonstrably wrong with it.
 *
 * This is the side with a pipeline: harvest → design plan → demo → draft →
 * send. All of it is commercial, which is why it is fenced off from the job
 * hunt at /scout rather than being a filter over the same list. */
export default function FreelancePage() {
  return <ScoutWorkspace kind="freelance" />;
}
