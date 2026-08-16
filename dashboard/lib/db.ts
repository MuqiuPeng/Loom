import postgres from "postgres";

/** Direct Postgres access from the dashboard.
 *
 * Used by the public demo route, which is the one page a stranger opens at an
 * unpredictable time. Reading Supabase straight from Vercel keeps that link
 * alive when the API box is asleep — going through the API would tie a link
 * you emailed a shop owner to a laptop being awake.
 *
 * Not the Supabase JS client: PostgREST would need an RLS policy per table to
 * be safe, and access control already lives in NextAuth. These tables are
 * locked to the owner role instead — `anon` has no grants at all.
 *
 * Requires SUPABASE_DB_URL, the transaction-pooler string (port 6543). */
declare global {
  // eslint-disable-next-line no-var
  var __loomSql: ReturnType<typeof postgres> | undefined;
}

function connect() {
  const url = process.env.SUPABASE_DB_URL;
  if (!url) throw new Error("SUPABASE_DB_URL is not set");

  return postgres(url, {
    // The transaction pooler hands out a different backend per statement, so
    // server-side prepared statements can't be reused — pgbouncer errors on
    // them. Mandatory here, not a tuning knob.
    prepare: false,
    max: 2,
    idle_timeout: 20,
    connect_timeout: 10,
  });
}

/** One client per warm lambda, not one per request. */
export const sql = globalThis.__loomSql ?? connect();
if (process.env.NODE_ENV !== "production") globalThis.__loomSql = sql;
