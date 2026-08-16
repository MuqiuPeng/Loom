/** Which account an incoming API request acts as.
 *
 * Pulled out of the proxy route so it can be reasoned about and tested on its
 * own. It decides who sees whose data, and it got that wrong once already:
 * checking the public carve-out before the session resolved every
 * `GET /api/profile` to the public owner, so a signed-in user opening the
 * profile page was served the owner's name, email and career history.
 */

export type ActingUser =
  | { kind: "session"; userId: string }
  | { kind: "public"; userId: string }
  | { kind: "unauthenticated" };

/** The one request a reader with no account may make.
 *
 * `/expo/...` is a public profile showcase excluded from the auth middleware,
 * and it is a client component that fetches `/api/profile`. Deliberately
 * narrow: GET only, that exact path, nothing else and no writes.
 */
export function isPublicRead(method: string, pathname: string): boolean {
  return method === "GET" && pathname === "/api/profile";
}

/**
 * A present session always wins. The carve-out is a fallback for requests
 * that have no account attached — never an override of one that does.
 */
export function resolveActingUser(
  method: string,
  pathname: string,
  sessionEmail: string | null | undefined,
  publicProfileUser: string,
): ActingUser {
  if (sessionEmail) {
    return { kind: "session", userId: sessionEmail };
  }
  if (isPublicRead(method, pathname)) {
    return { kind: "public", userId: publicProfileUser };
  }
  return { kind: "unauthenticated" };
}
