import { NextRequest, NextResponse } from "next/server";
import { auth, PUBLIC_PROFILE_USER } from "@/lib/auth";

const API_URL = process.env.LOOM_API_URL || "http://localhost:8001";
const API_KEY = process.env.LOOM_API_KEY || "";

const ALLOWED_PREFIXES = [
  "/api/profile",
  "/api/resumes",
  "/api/jobs",
  "/api/workflow",
  "/api/workflows",
  "/api/tasks",
  "/api/scout",
  "/api/logs",
  "/api/health",
];

/** The one thing a stranger may fetch: the profile behind /expo, read-only.
 *
 * middleware.ts excludes /expo so the showcase page opens without an account,
 * and that page is a client component calling /api/profile — so the carve-out
 * has to live here too. It is deliberately narrow: GET only, that exact path,
 * and always resolved to PUBLIC_PROFILE_USER regardless of what the caller
 * asks for. Every other route, and every write, needs a session. */
function isPublicRead(req: NextRequest): boolean {
  return req.method === "GET" && req.nextUrl.pathname === "/api/profile";
}

async function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl;

  if (!ALLOWED_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  // The API trusts X-Loom-User because only this proxy can set it: the Bearer
  // key never leaves the server, so a browser cannot call the API directly and
  // claim to be someone else.
  let actingAs: string;
  if (isPublicRead(req)) {
    actingAs = PUBLIC_PROFILE_USER;
  } else {
    const session = await auth();
    const email = session?.user?.email;
    if (!email) {
      return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    }
    actingAs = email;
  }

  const upstream = `${API_URL}${pathname}${search}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${API_KEY}`,
    "X-Loom-User": actingAs,
  };

  const contentType = req.headers.get("content-type");
  if (contentType) {
    headers["Content-Type"] = contentType;
  }

  const body =
    req.method !== "GET" && req.method !== "HEAD"
      ? await req.arrayBuffer()
      : undefined;

  const res = await fetch(upstream, {
    method: req.method,
    headers,
    body,
  });

  const data = await res.arrayBuffer();

  const responseHeaders = new Headers();
  // Only content-type used to survive the hop, which silently defeated any
  // caching policy the API set: a `no-store` preview arrived header-less and
  // the browser cached it heuristically, so re-selecting a design appeared to
  // do nothing at all.
  for (const header of ["content-type", "cache-control", "content-disposition"]) {
    const value = res.headers.get(header);
    if (value) responseHeaders.set(header, value);
  }

  return new NextResponse(data, {
    status: res.status,
    statusText: res.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
