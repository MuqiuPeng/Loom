"use client";

import ScoutWorkspace from "@/components/scout/ScoutWorkspace";

/** The hidden job market: companies worth asking about work.
 *
 * Split from /freelance rather than sharing a toggle, because the difference
 * outlives the search. A lead saved here never enters the outreach pipeline —
 * an employment enquiry is not a commercial electronic message, and a pitch
 * signed with your business name is. */
export default function ScoutPage() {
  return <ScoutWorkspace kind="job" />;
}
