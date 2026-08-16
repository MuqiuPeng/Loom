import { NextRequest, NextResponse } from "next/server";
import { auth, PUBLIC_PROFILE_USER } from "@/lib/auth";
import { resolveActingUser } from "@/lib/acting-user";

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

async function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl;

  if (!ALLOWED_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  // The API trusts X-Loom-User because only this proxy can set it: the Bearer
  // key never leaves the server, so a browser cannot call the API directly and
  // claim to be someone else. Who that is, is decided in lib/acting-user.ts.
  const session = await auth();
  const acting = resolveActingUser(
    req.method,
    pathname,
    session?.user?.email,
    PUBLIC_PROFILE_USER,
  );
  if (acting.kind === "unauthenticated") {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }
  const actingAs = acting.userId;

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
