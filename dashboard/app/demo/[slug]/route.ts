import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { withPreviewNotice } from "@/lib/demo-banner";

/** A demo, served to whoever has the link — but only once it has been made
 * shareable for that lead.
 *
 * `demo_public` is part of the WHERE clause rather than a check afterwards:
 * a private demo is indistinguishable from one that does not exist, so a
 * guessed slug reveals nothing about who is being approached.
 *
 * Reads Supabase directly. This is the one page a stranger opens at an
 * unpredictable time, so it must not depend on the API box being awake.
 * Unauthenticated by design — middleware.ts excludes /demo. */
export const runtime = "nodejs";

export async function GET(
  _req: NextRequest,
  { params }: { params: { slug: string } }
) {
  let rows: { demo_html: string | null; google_name: string | null }[];
  try {
    rows = await sql<{ demo_html: string | null; google_name: string | null }[]>`
      select demo_html, google_name
      from scout_leads
      where demo_slug = ${params.slug}
        and demo_public = true
      limit 1
    `;
  } catch {
    return new NextResponse("This preview is temporarily unavailable.", {
      status: 503,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }

  const html = rows[0]?.demo_html;
  if (!html) {
    return new NextResponse("Not found", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }

  // Stamped here rather than in the page: the document is model-written and
  // a model can drop a line, but the response is ours.
  return new NextResponse(withPreviewNotice(html, rows[0]?.google_name), {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      // Model-written from a scraped site; it needs no JavaScript, so none
      // is allowed to run.
      "content-security-policy":
        "default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; font-src data:",
      // Carries a real business's name — it must never compete with them in
      // search results.
      "x-robots-tag": "noindex, nofollow",
      // Short: a design switched after the link was sent should not serve
      // the previous one for long.
      "cache-control": "public, max-age=60, s-maxage=60",
    },
  });
}
