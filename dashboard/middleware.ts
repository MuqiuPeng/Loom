import { auth } from "@/lib/auth";

export default auth((req) => {
  if (!req.auth && req.nextUrl.pathname !== "/login") {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    return Response.redirect(loginUrl);
  }
});

export const config = {
  // Pages only. `/api/*` is excluded because a redirect to /login is the wrong
  // answer to a fetch() — the proxy route checks the session itself and
  // returns 401, which the caller can actually handle. It also has to, since
  // it is the component that knows which single request (the /expo profile
  // read) is allowed through without one.
  //
  // `demo` is excluded so a shop owner can open a shared link without an
  // account. The route itself still refuses anything not marked public.
  matcher: ["/((?!api|demo|login|expo|_next/static|_next/image|favicon.ico).*)"],
};
