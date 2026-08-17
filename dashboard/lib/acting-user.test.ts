import { describe, expect, it } from "vitest";

import { resolveActingUser } from "./acting-user";

const OWNER = "owner@example.com";
const OTHER = "other@example.com";

describe("resolveActingUser", () => {
  // The regression this file exists for. The public /expo carve-out was
  // tested before the session, so every GET /api/profile resolved to the
  // owner — a signed-in user opening the profile page was shown the owner's
  // name, email and career history. Nothing else caught it: the request
  // succeeded, the page rendered, and the data was simply the wrong person's.
  it("serves a signed-in user their own profile, not the public one", () => {
    const acting = resolveActingUser("GET", "/api/profile", OTHER, OWNER);
    expect(acting).toEqual({ kind: "session", userId: OTHER });
  });

  it("serves the public profile only when there is no session", () => {
    const acting = resolveActingUser("GET", "/api/profile", null, OWNER);
    expect(acting).toEqual({ kind: "public", userId: OWNER });
  });

  it("lets the owner's own session through as a session, not as the carve-out", () => {
    const acting = resolveActingUser("GET", "/api/profile", OWNER, OWNER);
    expect(acting.kind).toBe("session");
  });

  it.each([
    ["POST", "/api/profile"],
    ["PATCH", "/api/profile/basic"],
    ["DELETE", "/api/profile/experience/abc"],
  ])("refuses %s %s without a session", (method, path) => {
    expect(resolveActingUser(method, path, null, OWNER)).toEqual({
      kind: "unauthenticated",
    });
  });

  it.each([
    "/api/jobs",
    "/api/resumes",
    "/api/scout/leads",
    "/api/logs",
    "/api/profile/experience",
  ])("refuses an unauthenticated GET of %s", (path) => {
    expect(resolveActingUser("GET", path, null, OWNER)).toEqual({
      kind: "unauthenticated",
    });
  });

  it("does not widen the carve-out to paths that merely start with it", () => {
    // `/api/profile/experience` shares a prefix with the public path; only the
    // exact path is public.
    expect(resolveActingUser("GET", "/api/profile/experience", null, OWNER).kind)
      .toBe("unauthenticated");
  });

  it("treats an empty-string email as no session rather than as a user", () => {
    expect(resolveActingUser("GET", "/api/jobs", "", OWNER).kind).toBe(
      "unauthenticated",
    );
  });
});
