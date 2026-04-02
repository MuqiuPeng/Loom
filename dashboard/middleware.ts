import { auth } from "@/lib/auth";

export default auth((req) => {
  if (!req.auth && req.nextUrl.pathname !== "/login") {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    return Response.redirect(loginUrl);
  }
});

export const config = {
  matcher: ["/((?!api/auth|api/profile|api/resumes|api/jobs|api/workflow|api/health|login|expo|_next/static|_next/image|favicon.ico).*)"],
};
